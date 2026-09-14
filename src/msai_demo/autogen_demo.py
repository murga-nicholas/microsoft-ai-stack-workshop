"""AutoGen: the legacy multi-agent lane, with real process recovery.

AutoGen supplies group chat and portable team state. The application
persists a pending approval, starts a new process, and gates the
simulated business action. Both resume attempts load the same saved
team; a durable store prevents the second action from executing.

Offline replies are explicitly synthetic. Team execution, state
serialization, process creation, approval and deduplication are real.

Run it:

    uv sync --group legacy
    uv run msai-demo autogen --format json
    uv run msai-demo autogen --execution live
"""

from __future__ import annotations

import hashlib
import json
import os
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from tempfile import mkdtemp
from typing import TYPE_CHECKING, Any, Protocol, cast

from msai_demo import scenario
from msai_demo.contracts import (
    DemoResult,
    Mode,
    Status,
    evidence,
    missing_configuration,
    result,
)
from msai_demo.resume_worker import (
    ResumeError,
    SubprocessResumePort,
    execution_checks,
    model_failure,
    read_json,
    recovery_summary,
    write_json,
)
from msai_demo.runtime import REPO_ROOT, env_is_present

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from autogen_core.models import ChatCompletionClient

    from msai_demo.resume_worker import ResumePort, ResumeResult
    from msai_demo.scenario import ProposalRun, ProposalTurn

DEMO_NAME = "autogen"
TECHNOLOGY = "AutoGen (autogen-agentchat)"
ARCHITECT = "SolutionArchitect"
REVIEWER = "RiskReviewer"
FIXTURE_ID = "autogen-approval-recovery-v2"

ARCHITECT_BRIEF = (
    "You are a solution architect. Return a JSON proposal with scope, "
    "milestones, cost and cited_sections. Use the supplied JSON example "
    "as its exact shape. Always call price_support_pilot before "
    "quoting a number. Ground the proposal in the supplied notes."
)
REVIEWER_BRIEF = (
    "You are a delivery risk reviewer. Challenge commitments that are "
    "uncosted, ungrounded or over budget. End with APPROVE or REJECT. "
    "APPROVE requests human approval; it never authorizes an action."
)


class TeamPort(Protocol):
    """The AutoGen team operations used by the application."""

    async def run(self, *, task: str) -> Any:
        """Run until the team's configured termination condition."""

    async def save_state(self) -> Mapping[str, Any]:
        """Return the SDK's portable state dictionary."""

    async def load_state(self, state: Mapping[str, Any]) -> None:
        """Restore the SDK's portable state dictionary."""


class AutoGenPort(Protocol):
    """Inject team construction without patching SDK internals."""

    mode: Mode
    sdk_invoked: bool

    def build_team(self, *, max_turns: int) -> TeamPort:
        """Construct a fresh team and its model clients."""

    async def close(self) -> None:
        """Release clients created by this port."""


class SDKPort:
    """Build actual AutoGen teams for an explicit execution mode."""

    sdk_invoked = True

    def __init__(self, execution: str) -> None:
        """Select live clients only when explicitly requested."""
        self.mode: Mode = (
            "live_model" if execution == "live" else "local_contract"
        )
        self._clients: tuple[ChatCompletionClient, ...] = ()

    def build_team(self, *, max_turns: int) -> TeamPort:
        """Construct the two participants and their round-robin team."""
        live = self.mode == "live_model"
        self._clients = (
            build_live_clients(
                openai_model="gpt-5.4-mini",
                anthropic_model="claude-haiku-4-5",
            )
            if live
            else build_offline_clients()
        )
        return build_autogen_team(
            architect_client=self._clients[0],
            reviewer_client=self._clients[1],
            max_turns=max_turns,
            with_tools=live,
        )

    async def close(self) -> None:
        """Close every client this port constructed."""
        for client in self._clients:
            await client.close()


def autogen_version(*, reader: Callable[[str], str] = version) -> str:
    """Return the distribution version through an injectable reader."""
    try:
        return reader("autogen-agentchat")
    except PackageNotFoundError:
        return "not installed"


def build_pricing_tool() -> Callable[[int], str]:
    """Expose the shared rate card as an AutoGen callable tool."""

    def price_support_pilot(weeks: int = scenario.PILOT_WEEKS) -> str:
        """Cost the pilot from the rate card and check the budget."""
        return json.dumps(scenario.price_pilot(weeks=weeks))

    return price_support_pilot


def build_autogen_team(
    *,
    architect_client: ChatCompletionClient,
    reviewer_client: ChatCompletionClient,
    max_turns: int = 4,
    with_tools: bool = True,
) -> TeamPort:
    """Build a team that stops for the application's approval gate.

    Args:
        architect_client: Client for drafting the proposal.
        reviewer_client: Client for reviewing the proposal.
        max_turns: Cap on speaking turns.
        with_tools: Attach pricing only to tool-capable clients.

    Returns:
        A real ``RoundRobinGroupChat`` behind a narrow protocol.
    """
    from autogen_agentchat.agents import AssistantAgent
    from autogen_agentchat.conditions import (
        MaxMessageTermination,
        TextMentionTermination,
    )
    from autogen_agentchat.teams import RoundRobinGroupChat

    architect = AssistantAgent(
        name=ARCHITECT,
        model_client=architect_client,
        system_message=ARCHITECT_BRIEF,
        tools=[build_pricing_tool()] if with_tools else None,
    )
    reviewer = AssistantAgent(
        name=REVIEWER,
        model_client=reviewer_client,
        system_message=REVIEWER_BRIEF,
    )
    termination = TextMentionTermination("APPROVE") | MaxMessageTermination(
        max_turns
    )
    return cast(
        "TeamPort",
        RoundRobinGroupChat(
            participants=[architect, reviewer],
            termination_condition=termination,
            max_turns=max_turns,
        ),
    )


def offline_script() -> tuple[str, str]:
    """Return a complete proposal and the reviewer's gate signal."""
    return (
        json.dumps(scenario.pilot_proposal()),
        "The deterministic cost and cited section are checked. APPROVE.",
    )


def build_offline_clients() -> tuple[
    ChatCompletionClient, ChatCompletionClient
]:
    """Return the same first-party replay clients in both processes."""
    from autogen_core.models import ModelInfo
    from autogen_ext.models.replay import ReplayChatCompletionClient

    info = ModelInfo(
        vision=False,
        function_calling=False,
        json_output=False,
        family="unknown",
        structured_output=False,
        multiple_system_messages=True,
    )
    script = offline_script()
    return (
        ReplayChatCompletionClient([script[0]], model_info=info),
        ReplayChatCompletionClient([script[1]], model_info=info),
    )


def build_live_clients(
    *, openai_model: str, anthropic_model: str
) -> tuple[ChatCompletionClient, ChatCompletionClient]:
    """Construct first-party clients for the two configured vendors."""
    from autogen_core.models import ModelInfo
    from autogen_ext.models.anthropic import AnthropicChatCompletionClient
    from autogen_ext.models.openai import OpenAIChatCompletionClient

    # AutoGen's 2025 model catalogue predates these model names. Enable
    # only the text/tool surface this application actually requests.
    info = ModelInfo(
        vision=False,
        function_calling=True,
        json_output=False,
        family="unknown",
        structured_output=False,
    )
    return (
        OpenAIChatCompletionClient(model=openai_model, model_info=info),
        AnthropicChatCompletionClient(model=anthropic_model, model_info=info),
    )


async def collect_turns(
    team: TeamPort,
    task: str,
    *,
    openai_model: str,
    anthropic_model: str,
    provider_architect: str = "openai",
    provider_reviewer: str = "anthropic",
) -> tuple[list[ProposalTurn], str]:
    """Convert native team messages into the shared transcript shape."""
    task_result = await team.run(task=task)
    stop_reason = str(getattr(task_result, "stop_reason", "unknown"))
    turns: list[ProposalTurn] = []
    for message in getattr(task_result, "messages", []):
        source = str(getattr(message, "source", ""))
        if source in {"", "user"}:
            continue
        to_text = getattr(message, "to_text", None)
        turns.append(
            {
                "index": len(turns),
                "speaker": source,
                "provider": (
                    provider_architect
                    if source == ARCHITECT
                    else provider_reviewer
                ),
                "model": (
                    openai_model if source == ARCHITECT else anthropic_model
                ),
                # Validation needs the complete JSON actually produced.
                "text": to_text() if callable(to_text) else str(message),
                "source_event": type(message).__name__,
                "usage": _usage_of(message),
            }
        )
    return turns, stop_reason


def _usage_of(message: Any) -> dict[str, int] | None:
    """Read reported token counts without filling missing values."""
    usage = getattr(message, "models_usage", None)
    input_tokens = getattr(usage, "prompt_tokens", None)
    output_tokens = getattr(usage, "completion_tokens", None)
    if not isinstance(input_tokens, int) or not isinstance(output_tokens, int):
        return None
    return {"input_tokens": input_tokens, "output_tokens": output_tokens}


def _proposal_from_turns(turns: list[ProposalTurn]) -> dict[str, object]:
    """Decode the architect's complete JSON response, failing closed."""
    for turn in turns:
        if turn["speaker"] != ARCHITECT:
            continue
        try:
            proposal: object = json.loads(turn["text"])
        except json.JSONDecodeError:
            continue
        if isinstance(proposal, dict):
            return cast("dict[str, object]", proposal)
    return {}


async def save_team_state(team: TeamPort, directory: Path) -> str:
    """Persist real SDK state and return its measured content hash."""
    path = directory / "team-state.json"
    write_json(path, await team.save_state())
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save_pending_approval(
    directory: Path, proposal: Mapping[str, object], checkpoint_id: str
) -> None:
    """Store the application's approval record beside the team state."""
    write_json(
        directory / "pending-approval.json",
        {
            "request_id": f"approval::{scenario.SCENARIO_ID}",
            "checkpoint_id": checkpoint_id,
            "proposal": dict(proposal),
        },
    )


def apply_approval(
    directory: Path,
    proposal: Mapping[str, object],
    approve: bool,
    *,
    files_read: list[str],
) -> list[dict[str, object]]:
    """Apply the human decision before the durable simulated action."""
    store = scenario.EventStore(directory, files_read=files_read)
    store.append("approval_recorded", approved=approve)
    if not approve:
        return []
    valid = scenario.proposal_checks(proposal)
    if valid["schema_valid"]:
        files_read.append(str(REPO_ROOT / "data/microsoft_ai_stack_notes.md"))
    if not all(valid.values()):
        return []
    action = store.execute_action(scenario.SCENARIO_ID)
    return [] if action is None else [action]


async def resume_autogen(
    directory: Path,
    approve: bool,
    execution: str,
    *,
    port: AutoGenPort | None = None,
) -> ResumeResult:
    """Rebuild a team from disk in the worker and apply the decision.

    Args:
        directory: The run's only source of persisted state.
        approve: Human decision supplied to the worker.
        execution: Explicit selection of scripted or live clients.
        port: Optional team-construction seam for tests.

    Returns:
        Measured process, disk-read and action evidence.
    """
    files_read: list[str] = []
    manifest = read_json(directory / "run.json", files_read)
    state = read_json(directory / "team-state.json", files_read)
    pending = read_json(directory / "pending-approval.json", files_read)
    proposal = pending.get("proposal")
    if not isinstance(proposal, dict):
        message = "The pending approval does not contain a proposal."
        raise TypeError(message)
    checkpoint_id = hashlib.sha256(
        (directory / "team-state.json").read_bytes()
    ).hexdigest()
    if checkpoint_id != pending.get("checkpoint_id"):
        message = "The pending approval does not match the saved team."
        raise ValueError(message)
    selected_port = port or SDKPort(execution)
    try:
        team = selected_port.build_team(
            max_turns=int(str(manifest["max_turns"]))
        )
        await team.load_state(state)
        restored = dict(await team.save_state()) == state
        if not restored:
            message = "The rebuilt team did not restore the saved state."
            raise ValueError(message)
        actions = apply_approval(
            directory, proposal, approve, files_read=files_read
        )
    finally:
        await selected_port.close()
    return {
        "pid": os.getpid(),
        "files_read": files_read,
        "checkpoint_id": checkpoint_id,
        "actions": actions,
        "restored": restored,
    }


async def run_autogen_demo(
    *,
    execution: str = "offline",
    max_turns: int = 4,
    approve: bool = True,
    port: AutoGenPort | None = None,
    resume_port: ResumePort | None = None,
    checkpoint_dir: Path | None = None,
) -> DemoResult:
    """Run the team, persist its gate and resume in two new processes.

    Args:
        execution: ``offline`` for replay clients or ``live``.
        max_turns: Hard cap on speaking turns.
        approve: Human decision supplied to both resume attempts.
        port: Optional injected team implementation.
        resume_port: Optional injected process boundary for tests.
        checkpoint_dir: Parent directory for retained run evidence.

    Returns:
        The shared envelope with measured recovery and action checks.
    """
    if execution == "live" and port is None:
        missing = [
            name
            for name in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY")
            if not env_is_present(name)
        ]
        if missing:
            return missing_configuration(
                demo=DEMO_NAME,
                technology=TECHNOLOGY,
                lane="legacy",
                provider="openai+anthropic",
                missing=missing,
                next_steps=[f"Set {name} in the shell." for name in missing],
            )
    selected_port = port or SDKPort(execution)
    try:
        return await _run_with_port(
            selected_port,
            resume_port or SubprocessResumePort(),
            approve=approve,
            max_turns=max_turns,
            checkpoint_dir=checkpoint_dir,
        )
    except ImportError:
        return _unavailable_sdk_result()
    except ResumeError as error:
        live = selected_port.mode == "live_model"
        return result(
            demo=DEMO_NAME,
            technology=TECHNOLOGY,
            lane="legacy",
            mode=selected_port.mode,
            status="error",
            headline="The AutoGen resume process did not complete.",
            evidence=evidence(
                provider="openai+anthropic" if live else "autogen-replay",
                sdk_invoked=selected_port.sdk_invoked,
                network_attempted=live,
                service_executed=live,
                fixture_id=None if live else FIXTURE_ID,
            ),
            error={"code": error.code, "message": "Resume failed safely."},
        )
    except Exception as error:
        failure = model_failure(error)
        if failure is None:
            raise
        status, details = failure
        live = selected_port.mode == "live_model"
        return result(
            demo=DEMO_NAME,
            technology=TECHNOLOGY,
            lane="legacy",
            mode=selected_port.mode,
            status=status,
            headline="The AutoGen model call did not complete.",
            evidence=evidence(
                provider="openai+anthropic" if live else "autogen-replay",
                sdk_invoked=selected_port.sdk_invoked,
                network_attempted=live,
                fixture_id=None if live else FIXTURE_ID,
            ),
            error=details,
        )
    finally:
        await selected_port.close()


async def _run_with_port(
    port: AutoGenPort,
    resume_port: ResumePort,
    *,
    approve: bool,
    max_turns: int,
    checkpoint_dir: Path | None,
) -> DemoResult:
    """Retain the complete run directory for inspecting the evidence."""
    live = port.mode == "live_model"
    model_a = "gpt-5.4-mini" if live else "autogen-replay"
    model_r = "claude-haiku-4-5" if live else "autogen-replay"
    team = port.build_team(max_turns=max_turns)
    turns, stop_reason = await collect_turns(
        team,
        scenario.BRIEF + "\nProposal shape: " + offline_script()[0],
        openai_model=model_a,
        anthropic_model=model_r,
        provider_architect="openai" if live else "offline",
        provider_reviewer="anthropic" if live else "offline",
    )
    model_invoked = live and bool(turns)
    parent_directory = checkpoint_dir or REPO_ROOT / ".msai_checkpoints"
    parent_directory.mkdir(parents=True, exist_ok=True)
    directory = Path(mkdtemp(prefix="autogen-", dir=parent_directory))
    run = await _finish_run(
        team,
        directory,
        resume_port,
        turns=turns,
        stop_reason=stop_reason,
        approve=approve,
        execution="live" if live else "offline",
        max_turns=max_turns,
        model_a=model_a,
        model_r=model_r,
    )
    return result(
        demo=DEMO_NAME,
        technology=TECHNOLOGY,
        lane="legacy",
        mode="local_execution" if live and not model_invoked else port.mode,
        status=_run_status(run["checks"]),
        headline=(
            f"AutoGen {autogen_version()} ran {len(turns)} turns; "
            "application code persisted and routed human approval."
        ),
        evidence=evidence(
            provider="openai+anthropic" if live else "autogen-replay",
            sdk_invoked=port.sdk_invoked,
            network_attempted=model_invoked,
            service_executed=model_invoked,
            fixture_id=None if live else FIXTURE_ID,
            requested_model=model_a,
            observed_model=model_a if turns else None,
        ),
        data=dict(run),
    )


def _run_status(checks: Mapping[str, bool]) -> Status:
    """Distinguish a stopped conversation from a rejected proposal."""
    if not checks["paused_for_approval"]:
        return "paused"
    if not checks["schema_valid"] or not checks["sources_valid"]:
        return "blocked"
    if not all(
        value for name, value in checks.items() if name != "acceptable"
    ):
        return "paused"
    return "ok"


async def _finish_run(
    team: TeamPort,
    directory: Path,
    resume_port: ResumePort,
    *,
    turns: list[ProposalTurn],
    stop_reason: str,
    approve: bool,
    execution: str,
    max_turns: int,
    model_a: str,
    model_r: str,
) -> ProposalRun:
    """Persist a stopped team before crossing the process boundary."""
    parent_pid = os.getpid()
    proposal = _proposal_from_turns(turns)
    store = scenario.EventStore(directory)
    first: ResumeResult | None = None
    second: ResumeResult | None = None
    write_json(
        directory / "run.json",
        {
            "implementation": "autogen",
            "execution": execution,
            "max_turns": max_turns,
        },
    )
    checkpoint_id = await save_team_state(team, directory)
    if "APPROVE" in stop_reason:
        save_pending_approval(directory, proposal, checkpoint_id)
        store.append("gate_reached")
        first = await resume_port.resume(
            directory, approve, execution=execution
        )
        second = await resume_port.resume(
            directory, approve, execution=execution
        )
    events = store.events()
    checks = execution_checks(
        proposal, events, parent_pid, first, second, approve=approve
    )
    checks["acceptable"] = (
        bool(first)
        and approve
        and all(
            checks[name]
            for name in (
                "schema_valid",
                "sources_valid",
                "within_budget",
                "cost_matches_pricing",
            )
        )
    )
    return {
        "implementation": "autogen",
        "framework_version": autogen_version(),
        "scenario_id": scenario.SCENARIO_ID,
        "participants": [
            {
                "name": ARCHITECT,
                "provider": "openai" if execution == "live" else "offline",
                "model": model_a,
            },
            {
                "name": REVIEWER,
                "provider": "anthropic" if execution == "live" else "offline",
                "model": model_r,
            },
        ],
        "turns": turns,
        "proposal": proposal,
        "cost": scenario.price_pilot(),
        "approval": {
            "request_id": (
                f"approval::{scenario.SCENARIO_ID}" if first else "none"
            ),
            "state": (
                "not_requested"
                if first is None
                else "approved"
                if approve
                else "rejected"
            ),
            "decided_by": "workshop-operator" if first else "none",
            "storage": "pending-approval.json",
        },
        "recovery": recovery_summary(directory, parent_pid, first, second),
        "actions": list(store.actions()),
        "events": events,
        "checks": checks,
        "application_owned": [
            "save_pending_approval",
            "save_team_state",
            "resume_autogen",
            "apply_approval",
            "scenario.EventStore.execute_action",
            "scenario.EventStore.append",
        ],
        "tool_calling": (
            "exercised"
            if any(
                turn["source_event"] == "ToolCallExecutionEvent"
                for turn in turns
            )
            else "not exercised: no ToolCallExecutionEvent was recorded"
        ),
        "stop_reason": stop_reason,
    }


def _unavailable_sdk_result() -> DemoResult:
    """Keep the deterministic proposal useful when AutoGen is absent."""
    proposal = scenario.pilot_proposal()
    return result(
        demo=DEMO_NAME,
        technology=TECHNOLOGY,
        lane="legacy",
        mode="local_contract",
        status="paused",
        headline=(
            "AutoGen is unavailable; only the fixture proposal was checked."
        ),
        evidence=evidence(provider="none", fixture_id=FIXTURE_ID),
        data={
            "proposal": proposal,
            "checks": scenario.proposal_checks(proposal),
        },
        next_steps=[
            "Run uv sync --group legacy to exercise the team and recovery."
        ],
    )

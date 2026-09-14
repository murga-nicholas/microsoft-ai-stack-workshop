"""Compare legacy AutoGen with current Microsoft Agent Framework.

Both lanes cost the same proposal, stop for approval, and resume in a
separate OS process using disk state. Replaying that resume proves the
shared application's simulated business action is idempotent.
The responsibility matrix names the APIs and application functions
that make this possible; it does not score hand-written lists.

Run it:

    uv run msai-demo group-chat --format json
    uv run msai-demo group-chat --implementation agent-framework
    uv run msai-demo group-chat --execution live
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from tempfile import mkdtemp
from typing import TYPE_CHECKING, Any, Protocol, cast

from msai_demo import scenario
from msai_demo.contracts import (
    DemoResult,
    Mode,
    batch,
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
    from collections.abc import Callable, Sequence
    from pathlib import Path

    from agent_framework import (
        Agent,
        Content,
        FileCheckpointStorage,
        Message,
        SupportsChatGetResponse,
        Workflow,
        WorkflowCheckpoint,
        WorkflowEvent,
    )
    from agent_framework.orchestrations import GroupChatState

    from msai_demo.resume_worker import ResumePort, ResumeResult
    from msai_demo.scenario import ProposalRun, ProposalTurn

DEMO_NAME = "group-chat"
TECHNOLOGY = "Agent Framework GroupChatBuilder vs AutoGen"
ARCHITECT = "SolutionArchitect"
REVIEWER = "RiskReviewer"
CHECKPOINT_DIR = REPO_ROOT / ".msai_checkpoints"

ARCHITECT_BRIEF = (
    "You are a solution architect. Call price_support_pilot before "
    "quoting costs. Return only a JSON proposal matching this example: "
)
REVIEWER_BRIEF = (
    "You are a delivery risk reviewer. Reject uncosted, ungrounded or "
    "over-budget proposals. For a sound proposal call accept_proposal. "
    "This is a simulated business action requiring human approval."
)


class GroupChatPort(Protocol):
    """Build a workflow while keeping SDK construction injectable."""

    @property
    def mode(self) -> Mode:
        """Identify whether this adapter invokes a live model."""

    def build(
        self, directory: Path, max_rounds: int, *, resuming: bool = False
    ) -> Workflow:
        """Build fresh agents and a workflow against a run directory."""


class ClientFactory(Protocol):
    """Construct a provider client at the optional SDK boundary."""

    def __call__(
        self,
        provider: str,
        *,
        replies: Sequence[str],
        tool_plan: Sequence[tuple[str, dict[str, Any]]],
    ) -> SupportsChatGetResponse[Any]:
        """Select an explicit provider and optional offline script."""


@dataclass
class FrameworkPort:
    """Build the real SDK workflow with an explicit execution mode."""

    execution: str = "offline"

    @property
    def mode(self) -> Mode:
        """Identify scripted inference as a local contract."""
        return "live_model" if self.execution == "live" else "local_contract"

    def build(
        self, directory: Path, max_rounds: int, *, resuming: bool = False
    ) -> Workflow:
        """Construct the same graph in the parent and resume worker."""
        from agent_framework import FileCheckpointStorage

        provider_a, provider_r = _providers(self.execution)
        architect, reviewer = build_participants(
            provider_architect=provider_a,
            provider_reviewer=provider_r,
            directory=directory,
            resuming=resuming,
        )
        return build_group_chat_workflow(
            architect=architect,
            reviewer=reviewer,
            storage=FileCheckpointStorage(directory / "checkpoints"),
            max_rounds=max_rounds,
        )


def _providers(execution: str) -> tuple[str, str]:
    """Route explicitly; environment credentials never select a lane."""
    return (
        ("openai", "anthropic")
        if execution == "live"
        else ("offline", "offline")
    )


def price_support_pilot(weeks: int = scenario.PILOT_WEEKS) -> str:
    """Return the real deterministic costing for the proposal tool."""
    return json.dumps(scenario.price_pilot(weeks=weeks))


def accept_proposal(scenario_id: str, *, directory: Path) -> str:
    """Execute one approved simulated business action, once per run."""
    action = scenario.EventStore(directory).execute_action(scenario_id)
    return json.dumps({"action": action, "duplicate": action is None})


def agent_framework_version() -> str:
    """Return the installed Agent Framework version."""
    from importlib.metadata import version

    return version("agent-framework-core")


def round_robin(state: GroupChatState) -> str:
    """Alternate speakers in participant registration order."""
    names = list(state.participants.keys())
    return names[state.current_round % len(names)]


def build_participants(
    *,
    provider_architect: str,
    provider_reviewer: str,
    directory: Path,
    resuming: bool = False,
    client_factory: ClientFactory | None = None,
) -> tuple[Agent[Any], Agent[Any]]:
    """Build agents with locally bound, approval-gated action tools.

    Args:
        provider_architect: Explicit architect model provider.
        provider_reviewer: Explicit reviewer model provider.
        directory: Run directory used by the idempotency store.
        resuming: Continue scripted replies after the paused tool call.
        client_factory: Injectable provider boundary for offline tests.

    Returns:
        The architect and reviewer, with identical stable names.
    """
    from agent_framework import Agent, tool

    if client_factory is None:
        from msai_demo.providers import create_chat_client

        client_factory = create_chat_client

    @tool(name="accept_proposal", approval_mode="always_require")
    def accept(scenario_id: str) -> str:
        """Record a simulated business action after human approval."""
        return accept_proposal(scenario_id, directory=directory)

    scripts = offline_scripts()
    # Client token cursors are not workflow state. Resume scripts begin
    # after the pending call, so they cannot manufacture another gate.
    architect_plan = (
        []
        if resuming
        else [("price_support_pilot", {"weeks": scenario.PILOT_WEEKS})]
    )
    reviewer_plan = (
        []
        if resuming
        else [("accept_proposal", {"scenario_id": scenario.SCENARIO_ID})]
    )
    architect = Agent(
        client=client_factory(
            provider_architect, replies=scripts[0], tool_plan=architect_plan
        ),
        name=ARCHITECT,
        description="Drafts scope, milestones and assumptions.",
        instructions=ARCHITECT_BRIEF + json.dumps(scenario.pilot_proposal()),
        tools=tool(price_support_pilot, approval_mode="never_require"),
    )
    reviewer = Agent(
        client=client_factory(
            provider_reviewer, replies=scripts[1], tool_plan=reviewer_plan
        ),
        name=REVIEWER,
        description="Challenges uncosted or ungrounded commitments.",
        instructions=REVIEWER_BRIEF,
        tools=accept,
    )
    return architect, reviewer


def build_group_chat_workflow(
    *,
    architect: Agent[Any],
    reviewer: Agent[Any],
    storage: FileCheckpointStorage,
    max_rounds: int = 4,
) -> Workflow:
    """Assemble group chat with durable checkpoints."""
    from agent_framework.orchestrations import GroupChatBuilder

    return GroupChatBuilder(
        participants=[architect, reviewer],
        selection_func=round_robin,
        termination_condition=_three_assistant_turns,
        max_rounds=max_rounds,
        checkpoint_storage=storage,
        intermediate_output_from=[architect, reviewer],
    ).build()


def _three_assistant_turns(conversation: Sequence[Message]) -> bool:
    """Stop after the proposal, review and confirmation turns."""
    return sum(message.role == "assistant" for message in conversation) >= 3


def offline_scripts() -> tuple[list[str], list[str]]:
    """Supply a schema-checkable draft through the real chat client."""
    return ([json.dumps(scenario.pilot_proposal())], ["Decision recorded."])


async def load_pending_approval(
    directory: Path, files_read: list[str]
) -> tuple[WorkflowCheckpoint, str, Content]:
    """Discover the original pending request using checkpoints alone.

    The SDK decodes its own checkpoint format. Selecting the earliest
    pending checkpoint keeps repeated resumes on the original gate,
    even after the workflow has written later completion checkpoints.
    """
    from agent_framework import Content, FileCheckpointStorage

    storage = FileCheckpointStorage(directory / "checkpoints")
    pending: list[WorkflowCheckpoint] = []
    for path in sorted((directory / "checkpoints").glob("*.json")):
        checkpoint = await storage.load(path.stem)
        files_read.append(str(path.resolve()))
        if checkpoint.pending_request_info_events:
            pending.append(checkpoint)
    if not pending:
        msg = "pending_approval_missing"
        raise ResumeError(msg)
    checkpoint = min(pending, key=lambda item: item.timestamp)
    request_id, event = next(
        iter(checkpoint.pending_request_info_events.items())
    )
    content = event.data
    if not isinstance(content, Content):
        msg = "invalid_approval_request"
        raise ResumeError(msg)
    if content.function_call is None or content.id is None:
        msg = "invalid_approval_request"
        raise ResumeError(msg)
    return checkpoint, request_id, content


async def resume_agent_framework(
    directory: Path, approve: bool, execution: str
) -> ResumeResult:
    """Rebuild the workflow and answer the checkpoint's pending event.

    Args:
        directory: The only state passed across the process boundary.
        approve: The human decision supplied to the worker.
        execution: Explicitly selects offline or live clients.

    Returns:
        Measured process, disk-read and action evidence.
    """
    from agent_framework import Content, FileCheckpointStorage

    files_read: list[str] = []
    config = read_json(directory / "run.json", files_read)
    checkpoint, request_id, content = await load_pending_approval(
        directory, files_read
    )
    store = scenario.EventStore(directory, files_read=files_read)
    before = len(store.actions())
    store.append("approval_recorded", approved=approve)
    workflow = FrameworkPort(execution).build(
        directory, cast("int", config["max_rounds"]), resuming=True
    )
    decision = Content.from_function_approval_response(
        approved=approve,
        function_call=cast("Content", content.function_call),
        id=cast("str", content.id),
    )
    stream = workflow.run(
        responses={request_id: decision},
        checkpoint_id=checkpoint.checkpoint_id,
        checkpoint_storage=FileCheckpointStorage(directory / "checkpoints"),
        stream=True,
    )
    async for _event in stream:
        pass
    await stream.get_final_response()
    actions = store.actions()[before:]
    return {
        "pid": os.getpid(),
        "files_read": files_read,
        "checkpoint_id": checkpoint.checkpoint_id,
        "actions": actions,
        "restored": True,
    }


async def run_agent_framework_lane(
    *,
    execution: str = "offline",
    approve: bool = True,
    max_rounds: int = 4,
    checkpoint_dir: Path | None = None,
    port: GroupChatPort | None = None,
    resume_port: ResumePort | None = None,
) -> ProposalRun:
    """Pause in the parent and resume twice in separate OS processes.

    Args:
        execution: Explicitly select offline scripts or live models.
        approve: Human decision applied to both resume attempts.
        max_rounds: Maximum number of group-chat speaking rounds.
        checkpoint_dir: Parent directory for a new, retained run.
        port: Optional workflow-construction seam for tests.
        resume_port: Optional process-transport seam for tests.

    Returns:
        The proposal, event log, actions and measured recovery checks.
    """
    from pathlib import Path

    root = checkpoint_dir or CHECKPOINT_DIR
    root.mkdir(parents=True, exist_ok=True)
    # Never delete a caller's prior runs to start a new demonstration.
    directory = Path(mkdtemp(prefix="agent-framework-", dir=root))
    write_json(
        directory / "run.json",
        {
            "implementation": "agent-framework",
            "max_rounds": max_rounds,
            "execution": execution,
        },
    )
    store = scenario.EventStore(directory)
    adapter = port or FrameworkPort(execution)
    workflow = adapter.build(directory, max_rounds)
    from msai_demo.providers import resolve_model_name

    provider_a, provider_r = _providers(execution)
    model_a, model_r = map(resolve_model_name, (provider_a, provider_r))
    turns: list[ProposalTurn] = []
    paused = False
    stream = workflow.run(scenario.BRIEF, stream=True)
    async for event in stream:
        if event.type == "request_info":
            paused = True
            store.append("gate_reached")
        _record_turn(
            event,
            turns,
            model_a=model_a,
            model_r=model_r,
            provider_a=provider_a,
            provider_r=provider_r,
        )
    await stream.get_final_response()
    proposal = _proposal_from_turns(turns)
    first = second = None
    if paused and all(scenario.proposal_checks(proposal).values()):
        worker = resume_port or SubprocessResumePort()
        first = await worker.resume(directory, approve, execution=execution)
        second = await worker.resume(directory, approve, execution=execution)
    checks = execution_checks(
        proposal, store.events(), os.getpid(), first, second, approve=approve
    )
    cost = scenario.price_pilot()
    acceptable, failures = scenario.proposal_is_acceptable(
        cost=cost,
        approved=approve and first is not None,
        cited_sources=cast("list[str]", proposal.get("cited_sections", [])),
    )
    checks["acceptable"] = acceptable and all(
        checks[name]
        for name in (
            "schema_valid",
            "sources_valid",
            "within_budget",
            "cost_matches_pricing",
        )
    )
    return {
        "implementation": "agent-framework",
        "framework_version": agent_framework_version(),
        "scenario_id": scenario.SCENARIO_ID,
        "participants": [
            {"name": ARCHITECT, "provider": provider_a, "model": model_a},
            {"name": REVIEWER, "provider": provider_r, "model": model_r},
        ],
        "turns": turns,
        "cost": cost,
        "proposal": proposal,
        "events": store.events(),
        "approval": {
            "state": ("approved" if approve else "rejected")
            if first
            else ("pending" if paused else "not_requested"),
            "decided_by": "workshop-operator" if first else None,
            "storage": "pending_request_info_events in workflow checkpoint",
            "acceptance_failures": failures,
        },
        "recovery": recovery_summary(directory, os.getpid(), first, second),
        "actions": store.actions(),
        "checks": checks,
        "application_owned": [
            "human decision",
            "resume process launch",
            "idempotency",
        ],
        "tool_calling": "exercised",
        "stop_reason": "resumed" if first else "not_resumed",
    }


def _proposal_from_turns(turns: list[ProposalTurn]) -> dict[str, object]:
    """Validate the emitted draft, never an unrelated fixture object."""
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


def _record_turn(
    event: WorkflowEvent[Any],
    turns: list[ProposalTurn],
    *,
    model_a: str,
    model_r: str,
    provider_a: str,
    provider_r: str,
) -> None:
    """Record participant output and retain the complete proposal."""
    if event.type not in {"intermediate", "output"}:
        return
    speaker = event.executor_id
    if speaker not in {ARCHITECT, REVIEWER}:
        return
    text = getattr(event.data, "text", "") or ""
    if not text.strip():
        return
    if turns and turns[-1]["speaker"] == speaker:
        turns[-1]["text"] += text
        return
    turns.append(
        {
            "index": len(turns),
            "speaker": speaker,
            "provider": provider_a if speaker == ARCHITECT else provider_r,
            "model": model_a if speaker == ARCHITECT else model_r,
            "text": text,
            "source_event": type(event.data).__name__,
            "usage": None,
        }
    )


async def run_group_chat_demo(
    *,
    implementation: str = "both",
    execution: str = "offline",
    approve: bool = True,
    max_rounds: int = 4,
    port: GroupChatPort | None = None,
    resume_port: ResumePort | None = None,
    checkpoint_dir: Path | None = None,
    configured: Callable[[str], bool] = env_is_present,
) -> DemoResult:
    """Run the requested lanes and report measured recovery evidence.

    Args:
        implementation: ``autogen``, ``agent-framework`` or ``both``.
        execution: Explicitly select ``offline`` or ``live`` execution.
        approve: Human decision supplied to each resume process.
        max_rounds: Maximum speaking rounds in each implementation.
        port: Optional current-lane workflow factory for tests.
        resume_port: Optional current-lane process transport for tests.
        checkpoint_dir: Parent directory for current-lane checkpoints.
        configured: Injectable credential-presence check for live runs.

    Returns:
        One lane's envelope, or both lanes and their responsibility
        matrix in a batch envelope.
    """
    if implementation not in {"both", "autogen", "agent-framework"}:
        message = "Unknown group-chat implementation."
        raise ValueError(message)
    if execution == "live":
        missing = [
            name
            for name in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY")
            if not configured(name)
        ]
        if missing:
            return missing_configuration(
                demo=DEMO_NAME,
                technology=TECHNOLOGY,
                lane="shared",
                provider="openai+anthropic",
                missing=missing,
                next_steps=[f"Set {name} in the shell." for name in missing],
            )
    children: list[DemoResult] = []
    if implementation in {"autogen", "both"}:
        from msai_demo.autogen_demo import run_autogen_demo

        children.append(
            await run_autogen_demo(
                execution=execution, max_turns=max_rounds, approve=approve
            )
        )
    if implementation in {"agent-framework", "both"}:
        children.append(
            await _agent_framework_result(
                execution=execution,
                approve=approve,
                max_rounds=max_rounds,
                port=port,
                resume_port=resume_port,
                checkpoint_dir=checkpoint_dir,
            )
        )
    if len(children) == 1:
        return children[0]
    envelope = batch(
        demo=DEMO_NAME,
        headline="Same proposal and recovery test; explicit responsibilities.",
        children=children,
    )
    envelope["data"] = {
        **(envelope["data"] or {}),
        "comparison": compare(children[0], children[1]),
    }
    return envelope


async def _agent_framework_result(
    *,
    execution: str,
    approve: bool,
    max_rounds: int,
    port: GroupChatPort | None,
    resume_port: ResumePort | None,
    checkpoint_dir: Path | None,
) -> DemoResult:
    """Wrap successful execution or a sanitized worker failure."""
    adapter = port or FrameworkPort(execution)
    try:
        run = await run_agent_framework_lane(
            execution=execution,
            approve=approve,
            max_rounds=max_rounds,
            port=adapter,
            resume_port=resume_port,
            checkpoint_dir=checkpoint_dir,
        )
    except ImportError:
        return result(
            demo="group-chat-agent-framework",
            technology=TECHNOLOGY,
            lane="current",
            mode="local_contract",
            status="paused",
            headline="Costed local proposal; install the SDK for recovery.",
            evidence=evidence(
                provider="offline", fixture_id="group-chat-script-v2"
            ),
            data={
                "implementation": "agent-framework",
                "proposal": scenario.pilot_proposal(),
                "checks": scenario.proposal_checks(scenario.pilot_proposal()),
                "recovery": {"restored": False},
            },
            error={
                "code": "sdk_missing",
                "message": "Agent Framework is unavailable.",
            },
            next_steps=[
                "Install agent-framework-core and "
                "agent-framework-orchestrations."
            ],
        )
    except ResumeError as error:
        live = adapter.mode == "live_model"
        return result(
            demo="group-chat-agent-framework",
            technology=TECHNOLOGY,
            lane="current",
            mode=adapter.mode,
            status="error",
            headline="Agent Framework recovery did not complete.",
            evidence=evidence(
                provider="openai+anthropic" if live else "offline",
                sdk_invoked=True,
                network_attempted=live,
                service_executed=live,
                fixture_id=None if live else "group-chat-script-v2",
            ),
            error={"code": error.code, "message": "Inspect local run state."},
        )
    except Exception as error:
        # SDK wrappers preserve provider failures in their cause chain.
        # Unknown failures still raise, preserving their diagnostics.
        failure = model_failure(error)
        if failure is None:
            raise
        status, details = failure
        live = adapter.mode == "live_model"
        return result(
            demo="group-chat-agent-framework",
            technology=TECHNOLOGY,
            lane="current",
            mode=adapter.mode,
            status=status,
            headline="The group-chat model call did not complete.",
            evidence=evidence(
                provider="openai+anthropic" if live else "offline",
                sdk_invoked=True,
                network_attempted=live,
                fixture_id=None if live else "group-chat-script-v2",
            ),
            error=details,
        )
    live = adapter.mode == "live_model"
    completed = all(
        value for key, value in run["checks"].items() if key != "acceptable"
    )
    return result(
        demo="group-chat-agent-framework",
        technology="Microsoft Agent Framework (GroupChatBuilder)",
        lane="current",
        mode=adapter.mode,
        status="ok" if completed else "paused",
        headline=(
            "Agent Framework resumed from a disk checkpoint in another "
            "process."
            if completed
            else "Agent Framework has not demonstrated process recovery."
        ),
        evidence=evidence(
            provider="openai+anthropic" if live else "offline",
            sdk_invoked=True,
            network_attempted=live,
            service_executed=live,
            fixture_id=None if live else "group-chat-script-v2",
            requested_model=run["participants"][0]["model"],
            observed_model=run["participants"][0]["model"],
        ),
        data=dict(run),
    )


def responsibility_matrix() -> list[dict[str, str]]:
    """Name the concrete owner of each concern in the running lanes."""
    return [
        {
            "concern": "pending approval record",
            "autogen": (
                "application: msai_demo.autogen_demo.save_pending_approval"
            ),
            "agent-framework": (
                "framework: agent_framework.WorkflowCheckpoint."
                "pending_request_info_events"
            ),
        },
        {
            "concern": "durable state",
            "autogen": "application: msai_demo.autogen_demo.save_team_state",
            "agent-framework": (
                "framework: agent_framework.FileCheckpointStorage"
            ),
        },
        {
            "concern": "restart routing",
            "autogen": "application: msai_demo.autogen_demo.resume_autogen",
            "agent-framework": (
                "application: msai_demo.group_chat_demo.resume_agent_framework"
            ),
        },
        {
            "concern": "action gate",
            "autogen": "application: msai_demo.autogen_demo.apply_approval",
            "agent-framework": (
                "framework: agent_framework.tool"
                '(approval_mode="always_require")'
            ),
        },
        {
            "concern": "idempotency",
            "autogen": (
                "application: msai_demo.scenario.EventStore.execute_action"
            ),
            "agent-framework": (
                "application: msai_demo.scenario.EventStore.execute_action"
            ),
        },
        {
            # The ordered log the checks are computed from. It is not
            # OpenTelemetry, which both SDKs can emit independently.
            "concern": "audit event log",
            "autogen": "application: msai_demo.scenario.EventStore.append",
            "agent-framework": (
                "application: msai_demo.scenario.EventStore.append"
            ),
        },
    ]


def compare(first: DemoResult, second: DemoResult) -> dict[str, object]:
    """Compare executed checks without counting authored concerns."""
    runs = {
        str((child["data"] or {}).get("implementation", child["demo"])): child[
            "data"
        ]
        or {}
        for child in (first, second)
    }
    return {
        "responsibility_matrix": responsibility_matrix(),
        "checks": {name: run.get("checks", {}) for name, run in runs.items()},
        "recovery": {
            name: run.get("recovery", {}) for name, run in runs.items()
        },
        "verdict": (
            "Agent Framework checkpoints include pending approvals and its "
            "tool API gates execution. Both lanes use application code to "
            "launch recovery, record decisions and enforce idempotency."
        ),
    }

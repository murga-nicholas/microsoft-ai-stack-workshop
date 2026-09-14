"""Harness Agent: the current runtime for work beyond one turn.

The real harness maintains a todo list, plan mode and session file
memory. Its default approval middleware stops a shared file write,
while private session memory can be updated without a prompt. No
proposal is accepted and no human decision is fabricated.

Run it:

    uv run msai-demo harness
    uv run msai-demo harness --execution live
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import TYPE_CHECKING, Protocol, TypedDict, cast

from msai_demo import scenario
from msai_demo.contracts import (
    DemoResult,
    Evidence,
    Mode,
    evidence,
    missing_configuration,
    result,
)
from msai_demo.runtime import REPO_ROOT, env_is_present

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Sequence

    from agent_framework import (
        AgentResponse,
        ChatContext,
        ChatOptions,
        Content,
        SupportsChatGetResponse,
    )

DEMO_NAME = "harness"
TECHNOLOGY = "Microsoft Agent Framework Harness Agent"
WORKSPACE_ROOT = REPO_ROOT / ".msai_workspace"
MAX_MODEL_CALLS = 12
MAX_RUN_SECONDS = 45


class TodoRecord(TypedDict):
    """A todo read back from the real harness session store."""

    title: str
    complete: bool


class HarnessRun(TypedDict):
    """Observed harness state after the approval pause."""

    operating_mode: str
    todos: list[TodoRecord]
    memory: str
    pending_tools: list[str]
    model_calls: int
    shared_write_executed: bool


class HarnessPort(Protocol):
    """Run the harness and expose evidence about its model boundary."""

    provider: str
    mode: Mode
    configured: bool
    record: Evidence

    async def run(
        self, directory: Path, *, max_iterations: int, max_model_calls: int
    ) -> HarnessRun:
        """Return observed state, or raise a known boundary failure."""


class HarnessLimitError(RuntimeError):
    """The agent used its allotted calls before reaching approval."""


class MalformedHarnessResponseError(ValueError):
    """The agent did not produce the required, verifiable state."""


@dataclass
class FrameworkHarnessPort:
    """Execute the installed harness with an injectable chat client.

    Args:
        provider: ``offline`` or ``openai`` for this workshop.
        client: Optional scripted client for deterministic variations.
        configured: Explicit readiness override for boundary tests.
    """

    provider: str = "offline"
    client: SupportsChatGetResponse[ChatOptions[None]] | None = None
    configured: bool = True
    mode: Mode = field(init=False)
    record: Evidence = field(init=False)

    def __post_init__(self) -> None:
        """Derive evidence from the selected provider."""
        self.mode = (
            "local_execution" if self.provider == "offline" else "live_model"
        )
        self.record = evidence(provider=self.provider)

    async def run(
        self, directory: Path, *, max_iterations: int, max_model_calls: int
    ) -> HarnessRun:
        """Exercise tools and read their actual persisted results."""
        from agent_framework import (
            FileSystemAgentFileStore,
            TodoProvider,
            chat_middleware,
            create_harness_agent,
            get_agent_mode,
        )

        from msai_demo.providers import create_chat_client

        client = self.client
        if client is None:
            client = cast(
                "SupportsChatGetResponse[ChatOptions[None]]",
                create_chat_client(
                    self.provider,
                    replies=["Draft saved. Human approval is still required."],
                    tool_plan=offline_tool_plan(),
                ),
            )
        model_calls = 0

        @chat_middleware
        async def limit_calls(
            context: ChatContext, call_next: Callable[[], Awaitable[None]]
        ) -> None:
            del context
            nonlocal model_calls
            if model_calls >= max_model_calls:
                message = "The harness exhausted its model-call budget."
                raise HarnessLimitError(message)
            model_calls += 1
            self.record["network_attempted"] = self.mode == "live_model"
            await call_next()
            self.record["service_executed"] = self.mode == "live_model"

        todo_provider = TodoProvider()
        memory_store = FileSystemAgentFileStore(directory / "memory")
        shared_store = FileSystemAgentFileStore(directory / "shared")
        # A virtual path is ergonomics, not a sandbox. The store checks
        # path containment; shell and external skills are absent.
        agent = create_harness_agent(
            client=client,
            name="PilotHarness",
            harness_instructions=(
                "Use plan mode. Track draft work and human approval as "
                "separate todos. Save and read pilot-plan.md in session "
                "memory using the supplied JSON. Mark only drafting "
                "complete. Request a shared "
                "file_access_write of proposal.md, then stop for approval."
            ),
            agent_instructions=scenario.BRIEF + "\n" + _plan_memory(),
            max_context_window_tokens=16_384,
            max_output_tokens=1_024,
            disable_compaction=True,
            todo_provider=todo_provider,
            file_memory_store=memory_store,
            file_access_store=shared_store,
            disable_web_search=True,
            loop_should_continue=_continue_to_approval,
            loop_max_iterations=max_iterations,
            middleware=[limit_calls],
        )
        self.record["sdk_invoked"] = True
        session = agent.create_session()
        response = await agent.run(scenario.BRIEF, session=session)
        pending_tools = [
            str(cast("Content", content.function_call).name)
            for content in response.user_input_requests
        ]
        if not pending_tools:
            message = "The harness stopped before requesting human approval."
            raise HarnessLimitError(message)
        items = await todo_provider.store.load_items(
            session, source_id=todo_provider.source_id
        )
        memory_path = f"{session.session_id}/pilot-plan.md"
        memory = await memory_store.read(memory_path)
        if memory is None:
            message = "The harness did not persist the proposal plan."
            raise MalformedHarnessResponseError(message)
        return {
            "operating_mode": get_agent_mode(session),
            "todos": [
                {"title": item.title, "complete": item.is_complete}
                for item in items
            ],
            "memory": memory,
            "pending_tools": pending_tools,
            "model_calls": model_calls,
            "shared_write_executed": await shared_store.file_exists(
                "proposal.md"
            ),
        }


def _continue_to_approval(
    *, last_result: AgentResponse, **kwargs: object
) -> bool:
    """Continue draft work until the framework returns an approval."""
    del last_result, kwargs
    # The harness loop itself exits before this callback on approval.
    # Its iteration cap also applies when the model never requests one.
    return True


def _plan_memory() -> str:
    """Persist scenario facts, including the absent human decision."""
    return json.dumps(
        {
            "scenario_id": scenario.SCENARIO_ID,
            "cost": scenario.price_pilot(),
            "milestones": scenario.plan_summary(),
            "human_approved": False,
            "source": "agent-framework-overview",
        },
        sort_keys=True,
    )


def offline_tool_plan() -> Sequence[tuple[str, dict[str, object]]]:
    """Return harness tool calls driven by scripted model tokens."""
    return [
        ("mode_get", {}),
        (
            "todos_add",
            {
                "todos": [
                    {"title": "Draft the pilot proposal"},
                    {"title": "Obtain named human approval"},
                ]
            },
        ),
        (
            "file_memory_write",
            {"file_name": "pilot-plan.md", "content": _plan_memory()},
        ),
        ("file_memory_read", {"file_name": "pilot-plan.md"}),
        (
            "todos_complete",
            {"items": [{"id": 1, "reason": "Draft persisted to memory."}]},
        ),
        (
            "file_access_write",
            {"file_name": "proposal.md", "content": _plan_memory()},
        ),
    ]


def _capabilities() -> dict[str, list[str]]:
    """Describe the capabilities selected by this constructor."""
    return {
        "enabled": [
            "todos",
            "plan_execute_modes",
            "session_file_memory",
            "per_call_history",
            "tool_approval_defaults",
            "shared_file_access",
            "bounded_loop",
        ],
        "disabled": [
            "compaction",
            "web_search",
            "shell",
            "skills",
            "background_agents",
        ],
        "experimental": ["shared_file_access", "file_store", "bounded_loop"],
    }


async def run_harness_demo(
    *,
    execution: str = "offline",
    port: HarnessPort | None = None,
    max_iterations: int = 3,
    max_model_calls: int = MAX_MODEL_CALLS,
) -> DemoResult:
    """Run the current harness with bounded, disposable file memory.

    Args:
        execution: ``offline`` or ``live`` (OpenAI).
        port: Optional boundary adapter for deterministic tests.
        max_iterations: Hard cap on harness re-invocations.
        max_model_calls: Hard cap across all model round trips.

    Returns:
        Evidence, observed state and a real pending approval request.

    Raises:
        ValueError: If execution or the call budgets are invalid.
    """
    if execution not in {"offline", "live"}:
        message = "execution must be 'offline' or 'live'."
        raise ValueError(message)
    if min(max_iterations, max_model_calls) < 1:
        message = "Harness iteration and model-call budgets must be positive."
        raise ValueError(message)
    selected = port
    if selected is None:
        live = execution == "live"
        selected = FrameworkHarnessPort(
            provider="openai" if live else "offline",
            configured=not live or env_is_present("OPENAI_API_KEY"),
        )
    if not selected.configured:
        return missing_configuration(
            demo=DEMO_NAME,
            technology=TECHNOLOGY,
            lane="current",
            provider=selected.provider,
            missing=["OPENAI_API_KEY"],
            next_steps=["Set OPENAI_API_KEY to run the live harness."],
        )

    directory = _workspace_directory()
    try:
        # TemporaryDirectory creates a unique child and cleans only that
        # child. It never removes another demo's or operator's files.
        with TemporaryDirectory(prefix="harness-", dir=directory) as path:
            async with asyncio.timeout(MAX_RUN_SECONDS):
                observed = await selected.run(
                    Path(path),
                    max_iterations=max_iterations,
                    max_model_calls=max_model_calls,
                )
        _validate_observed(observed)
    except ImportError:
        return _missing_sdk(selected.provider)
    except Exception as exc:
        # Unknown defects are re-raised by the mapper; they never become
        # a green result. SDKs may wrap HTTP and middleware failures.
        return _failure_result(selected, exc)

    return result(
        demo=DEMO_NAME,
        technology=TECHNOLOGY,
        lane="current",
        mode=selected.mode,
        status="paused",
        headline="Harness saved its plan and paused before the shared write.",
        evidence=selected.record,
        data={
            **observed,
            "scenario_id": scenario.SCENARIO_ID,
            "cost": scenario.price_pilot(),
            "accepted": False,
            "capabilities": _capabilities(),
            "approval_defaults": {
                "session_memory_and_todos": "never_require",
                "shared_file_read_and_write": "always_require",
                "standing_rules": "none granted",
            },
            "limits": {
                "harness_iterations": max_iterations,
                "model_calls": max_model_calls,
                "seconds": MAX_RUN_SECONDS,
            },
            "workspace": ".msai_workspace/harness-<temporary>",
            "workspace_cleaned": True,
            "usage": None,
        },
        next_steps=[
            "Review the draft before a named human approves any acceptance.",
            "Compaction is disabled for this short, deterministic lesson.",
        ],
    )


def _validate_observed(observed: HarnessRun) -> None:
    """Require actual memory, todos and the expected approval gate."""
    if (
        not observed["todos"]
        or observed["pending_tools"] != ["file_access_write"]
        or observed["shared_write_executed"]
    ):
        message = "Harness state did not demonstrate the required approval."
        raise MalformedHarnessResponseError(message)
    try:
        memory: object = json.loads(observed["memory"])
    except json.JSONDecodeError as exc:
        message = "The persisted plan must contain the supplied scenario JSON."
        raise MalformedHarnessResponseError(message) from exc
    if not isinstance(memory, dict):
        message = "The persisted plan must be a JSON object."
        raise MalformedHarnessResponseError(message)
    facts = cast("dict[str, object]", memory)
    if (
        facts.get("cost") != scenario.price_pilot()
        or facts.get("human_approved") is not False
    ):
        message = "The persisted plan changed its cost or invented approval."
        raise MalformedHarnessResponseError(message)


def _workspace_directory(root: Path = WORKSPACE_ROOT) -> Path:
    """Reject redirected workspace roots before creating any files."""
    directory = root.resolve()
    if directory != REPO_ROOT.resolve() / ".msai_workspace":
        message = "Harness files must remain inside .msai_workspace."
        raise ValueError(message)
    directory.mkdir(exist_ok=True)
    return directory


def _missing_sdk(provider: str) -> DemoResult:
    """Keep the arithmetic useful without claiming the harness ran."""
    return result(
        demo=DEMO_NAME,
        technology=TECHNOLOGY,
        lane="current",
        mode="local_contract",
        status="blocked",
        headline="Harness SDK unavailable; only the scenario contract ran.",
        evidence=evidence(provider=provider, fixture_id="harness-contract-v1"),
        data={"cost": scenario.price_pilot(), "capabilities": {"enabled": []}},
        error={
            "code": "missing_sdk",
            "message": "Install agent-framework-core.",
        },
        next_steps=["Run uv sync, then rerun the harness demo."],
    )


def _failure_result(port: HarnessPort, exc: Exception) -> DemoResult:
    """Report known failures without returning model or secret text."""
    code = _error_code(exc)
    return result(
        demo=DEMO_NAME,
        technology=TECHNOLOGY,
        lane="current",
        mode=port.mode,
        status="blocked" if code == "authorization_denied" else "error",
        headline="Harness stopped safely before accepting the proposal.",
        evidence=port.record,
        error={"code": code, "message": "Inspect the bounded harness run."},
        data={"accepted": False},
    )


def _error_code(exc: Exception) -> str:
    """Map known failures through SDK wrappers and re-raise defects."""
    cause: BaseException | None = exc
    while cause is not None:
        if isinstance(cause, HarnessLimitError):
            return "iteration_limit"
        if isinstance(cause, TimeoutError):
            return "timeout"
        if isinstance(cause, MalformedHarnessResponseError):
            return "malformed_response"
        # SDK wrappers retain the HTTP timeout in __cause__. Inspect
        # its bases without importing a provider on an offline path.
        bases = {
            (base.__module__, base.__name__) for base in type(cause).__mro__
        }
        if bases & {
            ("httpx", "TimeoutException"),
            ("httpx2", "TimeoutException"),
        }:
            return "timeout"
        status: object = getattr(cause, "status_code", None)
        if status in (401, 403):
            return "authorization_denied"
        if status == 429:
            return "throttled"
        cause = cause.__cause__
    raise exc

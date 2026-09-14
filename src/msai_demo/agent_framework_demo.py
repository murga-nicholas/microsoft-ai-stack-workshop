"""One current Microsoft Agent Framework agent, from tools to memory.

The offline client supplies scripted tokens. Agent Framework still
executes the tools, stores the session, streams updates and parses the
proposal. That proves the runtime plumbing, not model intelligence.
No proposal is accepted here; a named human must approve it first.

Run it:

    uv run msai-demo agent-framework
    uv run msai-demo agent-framework --execution live
"""

from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, Protocol, TypedDict, cast

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from msai_demo import scenario
from msai_demo.contracts import (
    DemoError,
    DemoResult,
    Mode,
    evidence,
    missing_configuration,
    result,
)
from msai_demo.runtime import REPO_ROOT, env_is_present

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from agent_framework import (
        Agent,
        AgentSession,
        ChatOptions,
        FunctionTool,
        SupportsChatGetResponse,
    )

DEMO_NAME = "agent-framework"
TECHNOLOGY = "Microsoft Agent Framework 1.18.0 (Agent)"
GROUNDING_QUERY = "agents workflows open-ended conversational execution order"
MEMORY_FACT = "The human approver is Morgan, the delivery manager."
RUN_TIMEOUT_SECONDS = 60


class Proposal(BaseModel):
    """A draft whose cost and citation must match local evidence.

    Attributes:
        title: Short description of the pilot.
        weeks: Duration from the shared scenario.
        total_usd: Total computed by the pricing tool.
        source: Exact Source line from the retrieved note.
        requires_human_approval: Always true for an unaccepted draft.
    """

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    title: str = Field(min_length=1)
    weeks: int = Field(gt=0)
    total_usd: int = Field(ge=0)
    source: str = Field(min_length=1)
    requires_human_approval: Literal[True]


class _MalformedProposalError(ValueError):
    """The structured draft disagrees with its local evidence."""


class _ModelResponse(Protocol):
    """The model metadata preserved in the SDK's chat response."""

    model: str | None


class Grounding(TypedDict):
    """One locally retrieved section and its attribution."""

    section: str
    text: str
    source: str
    score: int


class SessionEvidence(TypedDict):
    """Observed session history after two turns."""

    replies: list[str]
    user_messages: list[str]
    remembered_first_turn: bool
    pricing_tool_results: list[str]


class AgentPort(Protocol):
    """Configure one agent without coupling the runner to a vendor."""

    provider: str

    @property
    def mode(self) -> Mode:
        """Describe how this port executes inference."""

    def missing(self) -> list[str]:
        """Return missing prerequisites before creating a client."""

    def build(self, grounding: Grounding) -> Agent[ChatOptions]:
        """Build a real agent with this provider and local evidence."""


@dataclass
class FrameworkAgentPort:
    """Use the shared provider switch, with an injectable chat client.

    Args:
        provider: Offline by default; live runs select OpenAI.
        client: Optional real chat client, including a scripted client.
        configured: Presence check; tests can supply an empty setup.
    """

    provider: str = "offline"
    client: SupportsChatGetResponse[ChatOptions] | None = None
    configured: Callable[[str], bool] = env_is_present

    @property
    def mode(self) -> Mode:
        """Report local protocol execution or a live model call."""
        return (
            "local_execution" if self.provider == "offline" else "live_model"
        )

    def missing(self) -> list[str]:
        """Check credentials without reading them into the result."""
        if self.provider == "offline":
            return []
        return [] if self.configured("OPENAI_API_KEY") else ["OPENAI_API_KEY"]

    def build(self, grounding: Grounding) -> Agent[ChatOptions]:
        """Build the agent through the shared provider factory."""
        return build_agent(
            self.provider, client=self.client, grounding=grounding
        )


def build_agent(
    provider: str,
    *,
    client: SupportsChatGetResponse[ChatOptions] | None = None,
    grounding: Grounding | None = None,
) -> Agent[ChatOptions]:
    """Compose one agent with instructions, a client and a safe tool.

    Args:
        provider: ``offline`` or ``openai``.
        client: Optional injected client using the same SDK protocol.
        grounding: Retrieved context, or the default local note.

    Returns:
        A real Agent with an explicit local history provider.
    """
    from agent_framework import Agent, InMemoryHistoryProvider

    from msai_demo.providers import create_chat_client

    if provider not in {"offline", "openai"}:
        message = "This demo supports offline and openai providers."
        raise ValueError(message)
    note = grounding if grounding is not None else retrieve_grounding()
    proposal = Proposal(
        title="Customer-support pilot",
        weeks=scenario.PILOT_WEEKS,
        total_usd=scenario.price_pilot()["total"],
        source=note["source"],
        requires_human_approval=True,
    )
    if client is None:
        # Convert the provider's dynamic SDK boundary immediately.
        client = cast(
            "SupportsChatGetResponse[ChatOptions]",
            create_chat_client(
                provider,
                replies=[
                    "The pilot is costed. Morgan must approve it.",
                    "Morgan, the delivery manager, is the approver.",
                    "Draft ready for human review; no work accepted.",
                    proposal.model_dump_json(),
                ],
                tool_plan=[
                    ("price_support_pilot", {"weeks": scenario.PILOT_WEEKS})
                ],
            ),
        )
    return Agent(
        client=client,
        name="PilotArchitect",
        instructions=(
            f"{scenario.BRIEF} Call price_support_pilot before quoting "
            "cost. Preserve the named approver across turns. Never accept "
            "work. Ground every proposal in this local note:\n"
            f"{note['text']}\n{note['source']}"
        ),
        tools=build_pricing_tool(),
        context_providers=[InMemoryHistoryProvider()],
    )


def build_pricing_tool() -> FunctionTool:
    """Wrap deterministic pricing in a tool needing no approval."""
    from agent_framework import tool

    @tool(approval_mode="never_require")
    def price_support_pilot(weeks: int = scenario.PILOT_WEEKS) -> str:
        """Cost the pilot using the shared illustrative rate card.

        Args:
            weeks: Positive duration in weeks.

        Returns:
            JSON with costs, budget and headroom from the scenario.
        """
        return json.dumps(scenario.price_pilot(weeks=weeks), sort_keys=True)

    return price_support_pilot


async def _demonstrate_session(
    agent: Agent[ChatOptions], session: AgentSession
) -> SessionEvidence:
    """Run two turns and read the history the framework persisted."""
    from agent_framework import InMemoryHistoryProvider

    first_prompt = f"{scenario.BRIEF}\n{MEMORY_FACT} Cost the pilot."
    first = await agent.run(first_prompt, session=session)
    second = await agent.run("Who must approve this pilot?", session=session)
    history = InMemoryHistoryProvider()
    messages = await history.get_messages(
        session.session_id, state=session.state[history.source_id]
    )
    user_messages = [m.text for m in messages if m.role == "user"]
    return {
        "replies": [first.text, second.text],
        "user_messages": user_messages,
        # The script cannot demonstrate model recall. Persisted messages
        # prove the framework carries the first turn into the next run.
        "remembered_first_turn": first_prompt in user_messages,
        "pricing_tool_results": [
            str(content.result)
            for message in first.messages
            for content in message.contents
            if content.type == "function_result"
        ],
    }


async def _demonstrate_streaming(
    agent: Agent[ChatOptions], session: AgentSession
) -> list[str]:
    """Consume actual SDK updates and finalize the stream."""
    stream = agent.run(
        "Summarize the draft status.", session=session, stream=True
    )
    chunks = [update.text async for update in stream if update.text]
    await stream.get_final_response()
    return chunks


async def _demonstrate_structured_output(
    agent: Agent[ChatOptions], session: AgentSession, grounding: Grounding
) -> tuple[Proposal, str | None]:
    """Ask Agent Framework to parse and validate the proposal schema."""
    response = await agent.run(
        "Return the proposal with title, weeks, total_usd, the exact "
        "Source: line as source, and requires_human_approval=true.",
        session=session,
        # 1.18 parses response.value using this Pydantic model. Merely
        # asking for JSON in the prompt would not enforce the schema.
        options={"response_format": Proposal},
    )
    proposal = response.value
    if proposal is None:
        message = "The response contained no structured proposal."
        raise _MalformedProposalError(message)
    cost = scenario.price_pilot()
    if (proposal.weeks, proposal.total_usd, proposal.source) != (
        cost["weeks"],
        cost["total"],
        grounding["source"],
    ):
        message = "Proposal cost, duration or source differs from evidence."
        raise _MalformedProposalError(message)
    # AgentResponse keeps its ChatResponse in raw_representation;
    # the model belongs to that response, not the requested setting.
    chat_response = cast("_ModelResponse", response.raw_representation)
    return proposal, chat_response.model


def retrieve_grounding(
    query: str = GROUNDING_QUERY, *, path: Path | None = None
) -> Grounding:
    """Return the section with most query terms and its Source line.

    Args:
        query: Terms to match; ties keep corpus order.
        path: Optional local corpus; defaults to the workshop notes.

    Returns:
        The complete best section, attribution and overlap score.

    Raises:
        ValueError: If the corpus lacks sections, sources or matches.
    """
    corpus = (
        path
        if path is not None
        else (REPO_ROOT / "data" / "microsoft_ai_stack_notes.md")
    )
    terms = set(re.findall(r"[a-z0-9]+", query.lower()))
    sections: list[Grounding] = []
    # Teaching stand-in: production should use Azure AI Search.
    for block in re.split(r"(?m)^## Section: *", corpus.read_text("utf-8"))[
        1:
    ]:
        name, _, body = block.partition("\n")
        source = re.search(r"(?m)^Source: .+$", body)
        if source is None:
            message = "Every grounding section must contain a Source line."
            raise ValueError(message)
        text = body[: source.start()].strip()
        words = set(re.findall(r"[a-z0-9]+", f"{name} {text}".lower()))
        sections.append(
            {
                "section": name.strip(),
                "text": text,
                "source": source.group().strip(),
                "score": len(terms & words),
            }
        )
    if not sections:
        message = "The grounding corpus has no Section headings."
        raise ValueError(message)
    best = max(sections, key=lambda section: section["score"])
    if best["score"] == 0:
        message = "No grounding section matches the query."
        raise ValueError(message)
    return best


async def _run_examples(
    agent: Agent[ChatOptions], grounding: Grounding
) -> tuple[dict[str, object], str | None]:
    """Execute the four SDK examples inside one bounded session."""
    from agent_framework.exceptions import ChatClientException

    try:
        async with asyncio.timeout(RUN_TIMEOUT_SECONDS):
            session = agent.create_session()
            memory = await _demonstrate_session(agent, session)
            chunks = await _demonstrate_streaming(agent, session)
            proposal, observed_model = await _demonstrate_structured_output(
                agent, session, grounding
            )
    except ChatClientException as exc:
        failure = _known_provider_error(exc.__cause__)
        if failure is None:
            raise
        raise _ProviderError(failure) from exc
    data: dict[str, object] = {
        "scenario_id": scenario.SCENARIO_ID,
        "cost": scenario.price_pilot(),
        "session": memory,
        "stream_chunks": chunks,
        "structured_proposal": proposal.model_dump(),
        "grounding": grounding,
        "accepted": False,
        "usage": None,
    }
    return data, observed_model


class _ProviderError(Exception):
    """Carry only a sanitized, known failure across the SDK seam."""

    def __init__(self, error: DemoError) -> None:
        super().__init__(error["message"])
        self.error = error


def _known_provider_error(cause: BaseException | None) -> DemoError | None:
    """Recognize HTTP failures without exposing response bodies."""
    from httpx import TimeoutException
    from httpx2 import TimeoutException as ModernTimeoutException

    timeouts = (TimeoutError, TimeoutException, ModernTimeoutException)
    if isinstance(cause, timeouts) or isinstance(
        getattr(cause, "__cause__", None), timeouts
    ):
        return {
            "code": "timeout",
            "message": "The model provider timed out; no work accepted.",
        }
    code: object = getattr(cause, "status_code", None)
    if code in (401, 403):
        return {
            "code": "authorization_denied",
            "message": "The model provider denied access; check permissions.",
        }
    if code == 429:
        return {
            "code": "throttled",
            "message": "The model provider is throttling; retry later.",
        }
    return None


async def run_agent_framework_demo(
    *, execution: str = "offline", port: AgentPort | None = None
) -> DemoResult:
    """Run the current single-agent runtime with honest evidence.

    Args:
        execution: ``offline`` or ``live``; live defaults to OpenAI.
        port: Optional provider adapter, used without monkey-patching.

    Returns:
        Tools, memory, streaming and validated structured output, or
        a specific configuration, dependency or response failure.
    """
    if execution not in {"offline", "live"}:
        message = "execution must be offline or live."
        raise ValueError(message)
    selected = (
        port
        if port is not None
        else FrameworkAgentPort(
            provider="openai" if execution == "live" else "offline"
        )
    )
    missing = selected.missing()
    if missing:
        return missing_configuration(
            demo=DEMO_NAME,
            technology=TECHNOLOGY,
            lane="current",
            provider=selected.provider,
            missing=missing,
            next_steps=[
                f"Set {name} in .env or the shell." for name in missing
            ],
        )
    grounding = retrieve_grounding()
    live = selected.mode == "live_model"
    error: DemoError | None = None
    data: dict[str, object] | None = None
    requested_model: str | None = None
    observed_model: str | None = None
    try:
        from msai_demo.providers import resolve_model_name

        requested_model = resolve_model_name(selected.provider)
        agent = selected.build(grounding)
        data, observed_model = await _run_examples(agent, grounding)
    except ModuleNotFoundError:
        return result(
            demo=DEMO_NAME,
            technology=TECHNOLOGY,
            lane="current",
            mode="local_contract",
            status="blocked",
            headline="SDK unavailable; only local cost and grounding ran.",
            evidence=evidence(
                provider=selected.provider, fixture_id="agent-sdk-missing-v1"
            ),
            data={"cost": scenario.price_pilot(), "grounding": grounding},
            error={"code": "missing_sdk", "message": "Install the demo SDKs."},
            next_steps=["Run uv sync to install the pinned dependencies."],
        )
    except (ValidationError, _MalformedProposalError):
        error = {
            "code": "malformed_response",
            "message": "The proposal did not match the schema or evidence.",
        }
    except TimeoutError:
        error = {
            "code": "timeout",
            "message": "The agent exceeded its time budget; no work accepted.",
        }
    except _ProviderError as exc:
        error = exc.error
    status: Literal["ok", "error", "blocked"] = "ok"
    if error is not None:
        status = (
            "blocked" if error["code"] == "authorization_denied" else "error"
        )
    return result(
        demo=DEMO_NAME,
        technology=TECHNOLOGY,
        lane="current",
        mode=selected.mode,
        status=status,
        headline=(
            "One agent exercised tools, memory, streaming and a schema."
            if error is None
            else error["message"]
        ),
        evidence=evidence(
            provider=selected.provider,
            sdk_invoked=True,
            network_attempted=live,
            service_executed=live and error is None,
            requested_model=requested_model,
            observed_model=observed_model,
        ),
        data=data,
        error=error,
        next_steps=[
            "Review the draft with a named human before accepting work."
        ],
    )

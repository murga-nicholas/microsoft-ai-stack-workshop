"""Foundry Agent Service: the current service-owned agent runtime.

Connect to an existing named Prompt or Hosted agent and run one turn.
Foundry owns the definition, versions, hosted tools, conversations
and execution. The offline fixture validates the same application
contract without claiming that a service agent exists.

Run it:

    uv run msai-demo foundry-agent-service
    uv run msai-demo foundry-agent-service --execution live
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from dataclasses import dataclass
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
from msai_demo.foundry_models_demo import (
    FoundryCallError,
    _translate_sdk_error,
)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Callable, Mapping
    from contextlib import AbstractAsyncContextManager

DEMO_NAME = "foundry-agent-service"
TECHNOLOGY = "Foundry Agent Service / FoundryAgent"
FIXTURE_ID = "foundry-agent-service-v1"


@dataclass(frozen=True)
class AgentServiceRequest:
    """Non-secret connection and turn arguments for an existing agent.

    Attributes:
        project_endpoint: Foundry project containing the agent.
        agent_name: Existing Prompt or Hosted agent name.
        agent_version: Prompt agent version; optional for Hosted agents.
        prompt: Costed scenario supplied to the named agent.
    """

    project_endpoint: str
    agent_name: str
    agent_version: str | None
    prompt: str


class AgentServiceReply(TypedDict):
    """A service turn converted into the application contract."""

    text: str
    response_id: str | None


class AgentServicePort(Protocol):
    """One turn on an existing agent, with adapter-owned evidence."""

    mode: Mode
    record: Evidence

    async def invoke(self, request: AgentServiceRequest) -> AgentServiceReply:
        """Connect to the requested agent and return its reply."""
        raise NotImplementedError


class FixtureAgentServicePort:
    """Return the explicitly synthetic service-agent fixture."""

    mode: Mode = "local_contract"
    fixture_id = FIXTURE_ID

    def __init__(self) -> None:
        """Record the fixture without claiming network activity."""
        self.record = evidence(
            provider="foundry-agent-service", fixture_id=self.fixture_id
        )

    async def invoke(self, request: AgentServiceRequest) -> AgentServiceReply:
        """Replay one synthetic turn for the requested agent name."""
        return {
            "text": (
                f"Synthetic reply from {request.agent_name}: "
                "review the costed pilot and obtain human approval."
            ),
            "response_id": "fixture-agent-turn-1",
        }


class AgentResponse(Protocol):
    """The vendor response attributes consumed at the SDK boundary."""

    text: str
    response_id: str | None


class AgentClient(Protocol):
    """The supported FoundryAgent method used for one turn."""

    async def run(self, messages: str) -> AgentResponse:
        """Run an existing service-owned agent."""
        raise NotImplementedError


class _ClosableClient(Protocol):
    async def close(self) -> None:
        raise NotImplementedError


class _AgentResources(Protocol):
    client: _ClosableClient


@asynccontextmanager
async def _agent_client(
    request: AgentServiceRequest,
) -> AsyncIterator[AgentClient]:
    """Own the SDK's project, credential and HTTP client lifetimes."""
    from agent_framework.foundry import FoundryAgent
    from azure.ai.projects.aio import AIProjectClient
    from azure.identity.aio import DefaultAzureCredential

    async with (
        DefaultAzureCredential() as credential,
        AIProjectClient(
            endpoint=request.project_endpoint, credential=credential
        ) as project,
    ):
        agent = FoundryAgent(
            project_client=project,
            agent_name=request.agent_name,
            agent_version=request.agent_version,
        )
        try:
            yield cast("AgentClient", agent)
        finally:
            await cast("_AgentResources", agent.client).client.close()


class LiveAgentServicePort:
    """Run FoundryAgent against an existing service-owned agent.

    Args:
        client_factory: SDK session factory for transport tests.
    """

    mode: Mode = "live_service"

    def __init__(
        self,
        client_factory: Callable[
            [AgentServiceRequest], AbstractAsyncContextManager[AgentClient]
        ] = _agent_client,
    ) -> None:
        """Store the factory without creating a service agent."""
        self._client_factory = client_factory
        self.record = evidence(provider="foundry-agent-service")

    async def invoke(self, request: AgentServiceRequest) -> AgentServiceReply:
        """Run one turn and distinguish denied access from bad code."""
        from agent_framework.exceptions import ChatClientException

        self.record = evidence(provider="foundry-agent-service")
        async with self._client_factory(request) as agent:
            self.record["sdk_invoked"] = True
            try:
                response = await agent.run(request.prompt)
            except ChatClientException as error:
                # Both adapters use the same OpenAI v1 transport.
                raise _translate_sdk_error(error, self.record) from error
            self.record["network_attempted"] = True
            self.record["service_executed"] = True
            return {
                "text": response.text,
                "response_id": response.response_id,
            }


def _request(settings: Mapping[str, str]) -> AgentServiceRequest:
    """Attach verified costs to the named agent's first turn."""
    cost = scenario.price_pilot()
    return AgentServiceRequest(
        project_endpoint=settings.get("FOUNDRY_PROJECT_ENDPOINT")
        or "https://example.services.ai.azure.com/api/projects/workshop",
        agent_name=settings.get("FOUNDRY_AGENT_NAME") or "support-pilot-agent",
        agent_version=settings.get("FOUNDRY_AGENT_VERSION") or None,
        prompt=(
            f"{scenario.BRIEF}\nVerified cost: {cost['total']} USD; "
            f"budget: {cost['budget']} USD. Return a brief draft only. "
            "No human approval has been recorded."
        ),
    )


def _data(request: AgentServiceRequest) -> dict[str, object]:
    """Explain ownership and execute the shared acceptance policy."""
    cost = scenario.price_pilot()
    accepted, reasons = scenario.proposal_is_acceptable(
        cost=cost, approved=False, cited_sources=[]
    )
    return {
        "request": {
            "project_endpoint": request.project_endpoint,
            "agent_name": request.agent_name,
            "agent_version": request.agent_version,
            "auth": "Microsoft Entra / DefaultAzureCredential",
            "prompt": request.prompt,
        },
        "ownership": {
            "FoundryChatClient": "Your application owns the agent.",
            "FoundryAgent": (
                "Foundry owns definition, versions, hosted tools, "
                "conversations and server-side execution."
            ),
        },
        "connection": (
            "Set FOUNDRY_AGENT_NAME to an existing Prompt or Hosted agent. "
            "Prompt agents should set FOUNDRY_AGENT_VERSION; Hosted agents "
            "can omit it. This demo runs one turn, without creating an agent."
        ),
        "connected_agents": {
            "status": "preview",
            "purpose": "Point-to-point delegation to another agent.",
        },
        "multi_agent_workflows": {
            "status": "preview",
            "purpose": "Stateful orchestration with persistent context.",
        },
        "cost": cost,
        "accepted": accepted,
        "acceptance_failures": reasons,
        "usage": None,
    }


async def run_foundry_agent_service_demo(
    *,
    execution: str = "offline",
    port: AgentServicePort | None = None,
    environment: Mapping[str, str] | None = None,
    live_port_factory: Callable[[], AgentServicePort] = LiveAgentServicePort,
) -> DemoResult:
    """Connect to a named agent and run the costed pilot's first turn.

    Args:
        execution: ``offline`` uses a fixture; ``live`` invokes Foundry.
        port: Optional injected service adapter.
        environment: Explicit settings for deterministic configuration.
        live_port_factory: Constructor used after prerequisites pass.

    Returns:
        A result separating service access from application acceptance.
    """
    if execution not in {"offline", "live"}:
        message = "execution must be 'offline' or 'live'."
        raise ValueError(message)
    settings = os.environ if environment is None else environment
    if port is None:
        if execution == "live":
            missing = [
                name
                for name in ("FOUNDRY_PROJECT_ENDPOINT", "FOUNDRY_AGENT_NAME")
                if not settings.get(name, "").strip()
            ]
            if missing:
                return missing_configuration(
                    demo=DEMO_NAME,
                    technology=TECHNOLOGY,
                    lane="current",
                    provider="foundry-agent-service",
                    missing=missing,
                    next_steps=[f"Set {name}." for name in missing],
                )
            port = live_port_factory()
        else:
            port = FixtureAgentServicePort()
    request = _request(settings)
    data = _data(request)
    try:
        reply = await port.invoke(request)
    except ImportError:
        return result(
            demo=DEMO_NAME,
            technology=TECHNOLOGY,
            lane="current",
            mode="not_run",
            status="blocked",
            headline="The optional Foundry Agent Service SDK is unavailable.",
            evidence=evidence(provider="foundry-agent-service"),
            data=data,
            error={
                "code": "missing_sdk",
                "message": "Install the Foundry SDK.",
            },
            next_steps=["Run uv sync, or use --execution offline."],
        )
    except FoundryCallError as error:
        return result(
            demo=DEMO_NAME,
            technology=TECHNOLOGY,
            lane="current",
            mode=port.mode if port.record["network_attempted"] else "not_run",
            status="blocked",
            headline="Foundry agent access reached a prerequisite boundary.",
            evidence=port.record,
            data=data,
            error={"code": error.code, "message": str(error)},
            next_steps=[
                "Verify the named agent and its Entra role assignments."
            ],
        )
    text = reply.get("text")
    if not isinstance(text, str) or not text.strip():
        return result(
            demo=DEMO_NAME,
            technology=TECHNOLOGY,
            lane="current",
            mode=port.mode,
            status="error",
            headline="Foundry returned no usable agent reply.",
            evidence=port.record,
            data=data,
            error={"code": "malformed_response", "message": "Expected text."},
        )
    data["reply"] = reply
    return result(
        demo=DEMO_NAME,
        technology=TECHNOLOGY,
        lane="current",
        mode=port.mode,
        status="ok",
        headline="Named agent turn completed; the pilot needs approval.",
        evidence=port.record,
        data=data,
        next_steps=["Review the draft and obtain named human approval."],
    )

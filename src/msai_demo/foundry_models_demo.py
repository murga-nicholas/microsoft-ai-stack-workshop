"""Foundry Models: the current catalogue and model invocation path.

The application owns the agent when it uses FoundryChatClient. The
fixture replaces generation; request construction, deterministic
costing and the human approval gate still execute in this process.

Run it:

    uv run msai-demo foundry-models
    uv run msai-demo foundry-models --execution live
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

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Callable, Mapping
    from contextlib import AbstractAsyncContextManager

DEMO_NAME = "foundry-models"
TECHNOLOGY = "Foundry Models / FoundryChatClient"
FIXTURE_ID = "foundry-models-v1"

# Verified in agent-framework-foundry 1.13.0, _chat_client.py. The
# preview factories carry FOUNDRY_PREVIEW_TOOLS metadata in that SDK.
HOSTED_TOOL_FACTORIES: dict[str, str] = {
    "get_code_interpreter_tool": "GA",
    "get_file_search_tool": "GA",
    "get_web_search_tool": "GA",
    "get_image_generation_tool": "GA",
    "get_mcp_tool": "GA",
    "get_bing_grounding_tool": "experimental",
    "get_azure_ai_search_tool": "experimental",
    "get_bing_custom_search_tool": "preview",
    "get_sharepoint_tool": "preview",
    "get_fabric_tool": "preview",
    "get_memory_search_tool": "preview",
    "get_computer_use_tool": "preview",
    "get_browser_automation_tool": "preview",
    "get_a2a_tool": "preview",
}


@dataclass(frozen=True)
class ModelsRequest:
    """Non-secret arguments passed to the model client.

    Attributes:
        project_endpoint: Foundry project endpoint, not Azure OpenAI.
        model: Deployment name in that project.
        prompt: Shared scenario with deterministic costing attached.
    """

    project_endpoint: str
    model: str
    prompt: str


class ModelsReply(TypedDict):
    """The small response shape the application consumes."""

    text: str
    model: str | None


class ModelsPort(Protocol):
    """One model turn, with evidence owned by the adapter."""

    mode: Mode
    record: Evidence

    async def invoke(self, request: ModelsRequest) -> ModelsReply:
        """Return one reply to the costed pilot request."""
        raise NotImplementedError


class FixtureModelsPort:
    """Replay a named synthetic answer without importing an SDK."""

    mode: Mode = "local_contract"
    fixture_id = FIXTURE_ID

    def __init__(self) -> None:
        """Start with evidence that explicitly names the fixture."""
        self.record = evidence(provider="foundry", fixture_id=self.fixture_id)

    async def invoke(self, request: ModelsRequest) -> ModelsReply:
        """Return a synthetic draft; never pretend it was generated."""
        self.record["requested_model"] = request.model
        return {
            "text": "Synthetic draft: validate access, then seek approval.",
            "model": None,
        }


class ModelResponse(Protocol):
    """Typed view of the vendor response at the SDK boundary."""

    text: str
    model: str | None


class ModelsClient(Protocol):
    """The supported FoundryChatClient method used by this demo."""

    async def get_response(self, messages: str) -> ModelResponse:
        """Invoke a model with one message."""
        raise NotImplementedError


@asynccontextmanager
async def _models_client(
    request: ModelsRequest,
) -> AsyncIterator[ModelsClient]:
    """Own and close the optional SDK resources for one invocation."""
    from agent_framework.foundry import FoundryChatClient
    from azure.identity.aio import DefaultAzureCredential

    async with DefaultAzureCredential() as credential:
        client = FoundryChatClient(
            project_endpoint=request.project_endpoint,
            credential=credential,
            model=request.model,
        )
        try:
            yield cast("ModelsClient", client)
        finally:
            await client.client.close()
            await client.project_client.close()


class FoundryCallError(Exception):
    """A known boundary failure with a safe, credential-free message."""

    def __init__(self, code: str, message: str) -> None:
        """Keep safe failure details separate from SDK text."""
        super().__init__(message)
        self.code = code


def _translate_sdk_error(
    error: Exception, record: Evidence
) -> FoundryCallError:
    """Translate known SDK failures without echoing request secrets."""
    from azure.core.exceptions import ClientAuthenticationError
    from azure.identity import CredentialUnavailableError
    from openai import APIConnectionError, APIStatusError, APITimeoutError

    cause = error.__cause__ or error
    if isinstance(
        cause, (CredentialUnavailableError, ClientAuthenticationError)
    ):
        return FoundryCallError(
            "credential_unavailable",
            "Microsoft Entra credentials are unavailable.",
        )
    if isinstance(cause, APIStatusError):
        record["network_attempted"] = True
        if cause.status_code in {401, 403}:
            return FoundryCallError(
                "authorization_denied",
                "Foundry denied access to this resource.",
            )
        if cause.status_code == 429:
            return FoundryCallError(
                "throttled", "Foundry throttled this request."
            )
    if isinstance(cause, APITimeoutError):
        record["network_attempted"] = True
        return FoundryCallError("timeout", "The Foundry request timed out.")
    if isinstance(cause, APIConnectionError):
        record["network_attempted"] = True
        return FoundryCallError(
            "service_unavailable", "The Foundry endpoint could not be reached."
        )
    raise error


class LiveModelsPort:
    """Invoke FoundryChatClient and record only observed evidence.

    Args:
        client_factory: SDK session factory for transport tests.
    """

    mode: Mode = "live_model"

    def __init__(
        self,
        client_factory: Callable[
            [ModelsRequest], AbstractAsyncContextManager[ModelsClient]
        ] = _models_client,
    ) -> None:
        """Store the SDK session factory without contacting Foundry."""
        self._client_factory = client_factory
        self.record = evidence(provider="foundry")

    async def invoke(self, request: ModelsRequest) -> ModelsReply:
        """Run the model; classify only known vendor failures."""
        from agent_framework.exceptions import ChatClientException

        self.record = evidence(
            provider="foundry", requested_model=request.model
        )
        async with self._client_factory(request) as client:
            self.record["sdk_invoked"] = True
            try:
                response = await client.get_response(request.prompt)
            except ChatClientException as error:
                raise _translate_sdk_error(error, self.record) from error
            self.record["network_attempted"] = True
            self.record["service_executed"] = True
            self.record["observed_model"] = response.model
            return {"text": response.text, "model": response.model}


def _request(settings: Mapping[str, str]) -> ModelsRequest:
    """Build the same request shape for a fixture or a real model."""
    cost = scenario.price_pilot()
    return ModelsRequest(
        project_endpoint=settings.get("FOUNDRY_PROJECT_ENDPOINT")
        or "https://example.services.ai.azure.com/api/projects/workshop",
        model=settings.get("FOUNDRY_MODEL") or "workshop-model-deployment",
        prompt=(
            f"{scenario.BRIEF}\nVerified cost: {cost['total']} USD; "
            f"budget: {cost['budget']} USD. Draft a brief pilot proposal. "
            "Do not claim human approval or provision resources."
        ),
    )


def _data(request: ModelsRequest) -> dict[str, object]:
    """Explain endpoint selection and run the common approval gate."""
    cost = scenario.price_pilot()
    accepted, reasons = scenario.proposal_is_acceptable(
        cost=cost, approved=False, cited_sources=[]
    )
    return {
        "request": {
            "project_endpoint": request.project_endpoint,
            "auth": "Microsoft Entra / DefaultAzureCredential",
            "model": request.model,
            "prompt": request.prompt,
        },
        "rename_chain": ["Azure OpenAI Service", "Foundry Models"],
        "standalone_azure_openai": (
            "A standalone *.openai.azure.com resource uses "
            "agent_framework.openai OpenAIChatClient or "
            "OpenAIChatCompletionClient with azure_endpoint=."
        ),
        "agent_owner": "The application owns the agent and orchestration.",
        "hosted_tool_factories": dict(HOSTED_TOOL_FACTORIES),
        "inherited_tool_factories": {
            "get_shell_tool": {
                "sdk_status": "GA",
                "source": "Inherited from OpenAIChatClient",
                "service_support": "Foundry hosted shell support not verified",
            }
        },
        "tool_inventory_source": "agent-framework-foundry 1.13.0 source",
        "tool_execution": "Listed capabilities; no hosted tool was invoked.",
        "cost": cost,
        "accepted": accepted,
        "acceptance_failures": reasons,
        "usage": None,
    }


async def run_foundry_models_demo(
    *,
    execution: str = "offline",
    port: ModelsPort | None = None,
    environment: Mapping[str, str] | None = None,
    live_port_factory: Callable[[], ModelsPort] = LiveModelsPort,
) -> DemoResult:
    """Run a model turn and apply the shared approval policy.

    Args:
        execution: ``offline`` uses a fixture; ``live`` invokes Foundry.
        port: Optional adapter, injected without patching internals.
        environment: Explicit settings for deterministic configuration.
        live_port_factory: Constructor used after prerequisites pass.

    Returns:
        An honest envelope containing the request and model reply.
    """
    if execution not in {"offline", "live"}:
        message = "execution must be 'offline' or 'live'."
        raise ValueError(message)
    settings = os.environ if environment is None else environment
    if port is None:
        if execution == "live":
            missing = [
                name
                for name in ("FOUNDRY_PROJECT_ENDPOINT", "FOUNDRY_MODEL")
                if not settings.get(name, "").strip()
            ]
            if missing:
                return missing_configuration(
                    demo=DEMO_NAME,
                    technology=TECHNOLOGY,
                    lane="current",
                    provider="foundry",
                    missing=missing,
                    next_steps=[f"Set {name}." for name in missing],
                )
            port = live_port_factory()
        else:
            port = FixtureModelsPort()
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
            headline="The optional Foundry model SDK is unavailable.",
            evidence=evidence(provider="foundry"),
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
            headline="Foundry model access reached a prerequisite boundary.",
            evidence=port.record,
            data=data,
            error={"code": error.code, "message": str(error)},
            next_steps=[
                "Check Entra access, deployment availability and quota."
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
            headline="Foundry returned no usable model text.",
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
        headline="Model request completed; the pilot still needs approval.",
        evidence=port.record,
        data=data,
        next_steps=["Review the draft and obtain named human approval."],
    )

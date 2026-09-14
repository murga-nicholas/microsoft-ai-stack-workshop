"""Foundry Local: current models running on the operator's machine.

The offline contract builds a Chat Completions request and decodes a
named synthetic reply without a service or SDK. The live path discovers
an existing SDK web service or uses its configured endpoint, resolves a
model, and sends one real Chat Completions request.

Run it:

    uv run msai-demo foundry-local
    uv run msai-demo foundry-local --execution live
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from importlib import import_module
from typing import TYPE_CHECKING, Protocol, TypedDict, cast
from urllib.parse import urlsplit

from msai_demo import scenario
from msai_demo.contracts import DemoResult, Mode, evidence, result

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Mapping, Sequence
    from types import ModuleType

    from agent_framework import Message
    from httpx2 import AsyncBaseTransport
    from openai import AsyncOpenAI

DEMO_NAME = "foundry-local"
TECHNOLOGY = "Foundry Local (foundry-local-sdk 2.0.1)"
INTEGRATION_SOURCE = (
    "https://learn.microsoft.com/en-us/azure/foundry-local/how-to/"
    "how-to-integrate-with-inference-sdks"
)
CONNECTOR_CONSTRAINT = (
    "agent-framework-foundry-local pins foundry-local-sdk>=0.5.1,<0.5.2; "
    "the shipping SDK is 2.0.1, so this repo uses the documented "
    "OpenAI-compatible endpoint."
)
SDK_CORRECTION = (
    "Installed 2.0.1 exports foundry_local_sdk.FoundryLocalManager, "
    "not the historical from foundry_local import FoundryLocalManager. "
    "It uses Configuration, initialize(), instance.catalog.get_model(), "
    "start_web_service(), and urls. The shared provider receives the "
    "discovered base_url and skips duplicate SDK discovery."
)


@dataclass(frozen=True)
class LocalReply:
    """Text and model identity reported by an inference response.

    Attributes:
        text: Model-generated answer, never a computed acceptance.
        model: Model identity reported by the response.
        endpoint: Local OpenAI-compatible base URL.
        request: Contract request, when constructed without a service.
    """

    text: str
    model: str | None
    endpoint: str
    request: dict[str, object] | None = None


class LocalServiceError(Exception):
    """A known local failure with a safe display message."""

    def __init__(self, code: str, message: str) -> None:
        """Keep a stable error code separate from the safe message."""
        super().__init__(message)
        self.code = code


class FoundryLocalPort(Protocol):
    """Resolve a local model and request exactly one completion."""

    mode: Mode
    fixture_id: str | None
    sdk_invoked: bool
    network_attempted: bool

    async def complete(self, prompt: str, model: str) -> LocalReply:
        """Return one answer, or raise a known service failure."""
        raise NotImplementedError


class _CompletionMessage(TypedDict):
    content: str


class _CompletionChoice(TypedDict):
    message: _CompletionMessage


class _CompletionPayload(TypedDict):
    model: str
    choices: list[_CompletionChoice]


class FixtureFoundryLocalPort:
    """Build a real request shape and decode a named synthetic reply."""

    mode: Mode = "local_contract"
    fixture_id: str | None = "foundry-local-chat-completion-v1"
    sdk_invoked = False
    network_attempted = False

    async def complete(self, prompt: str, model: str) -> LocalReply:
        """Exercise the wire contract without optional SDKs."""
        endpoint = "http://localhost/v1"
        request: dict[str, object] = {
            "method": "POST",
            "url": f"{endpoint}/chat/completions",
            "body": {
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
            },
        }
        # These are the installed OpenAI ChatCompletion fields. The
        # synthetic timestamp and identity are fixture metadata only.
        response_json = json.dumps(
            {
                "id": self.fixture_id,
                "object": "chat.completion",
                "created": 0,
                "model": "synthetic-foundry-local-model",
                "choices": [
                    {
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": (
                                "Synthetic draft: use the computed pilot "
                                "cost, ground the answer, and obtain named "
                                "human approval before accepting work."
                            ),
                        },
                        "finish_reason": "stop",
                    }
                ],
            }
        )
        payload = cast("_CompletionPayload", json.loads(response_json))
        return LocalReply(
            payload["choices"][0]["message"]["content"],
            payload["model"],
            endpoint,
            request,
        )


class _Model(Protocol):
    id: str


class _Catalog(Protocol):
    def get_model(self, model_alias: str) -> _Model | None:
        raise NotImplementedError


class _Manager(Protocol):
    urls: list[str] | None
    catalog: _Catalog


class _ManagerType(Protocol):
    instance: _Manager | None


class _Response(Protocol):
    text: str
    model: str | None


class _ChatClient(Protocol):
    def get_response(
        self, messages: Sequence[Message]
    ) -> Awaitable[_Response]:
        raise NotImplementedError


class _ProviderFactory(Protocol):
    def __call__(
        self, provider: str, *, model_name: str, base_url: str
    ) -> object:
        raise NotImplementedError


def _sdk_service(
    model: str,
    loader: Callable[[str], ModuleType] = import_module,
) -> tuple[str, str]:
    """Discover an initialized 2.x manager without starting anything."""
    sdk = loader("foundry_local_sdk")
    manager_type = cast("_ManagerType", sdk.FoundryLocalManager)
    manager = manager_type.instance
    if manager is None or not manager.urls:
        message = "No running SDK web service or local endpoint was found."
        code = "service_unavailable"
        raise LocalServiceError(code, message)
    resolved = manager.catalog.get_model(model)
    if resolved is None:
        message = "The requested model alias is absent from the SDK catalog."
        code = "model_unavailable"
        raise LocalServiceError(code, message)
    return manager.urls[0], resolved.id


def _base_url(endpoint: str) -> str:
    """Require a loopback endpoint so a local demo stays local."""
    parsed = urlsplit(endpoint)
    if (
        parsed.scheme not in {"http", "https"}
        or parsed.hostname not in {"localhost", "127.0.0.1", "::1"}
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or parsed.path.rstrip("/") not in {"", "/v1"}
    ):
        message = "Use a loopback HTTP endpoint with no credentials or query."
        code = "invalid_configuration"
        raise LocalServiceError(code, message)
    return endpoint.rstrip("/").removesuffix("/v1") + "/v1"


def _provider_client(
    model: str,
    base_url: str,
    *,
    create_client: _ProviderFactory | None = None,
) -> _ChatClient:
    """Pass the discovered endpoint to the shared provider switch."""
    if create_client is None:
        from msai_demo import providers

        create_client = providers.create_chat_client

    return cast(
        "_ChatClient",
        create_client("foundry-local", model_name=model, base_url=base_url),
    )


class LiveFoundryLocalPort:
    """Use real SDK requests against an existing local web service.

    Args:
        endpoint: Observed service URL; otherwise inspect the SDK.
        transport: HTTP transport seam for deterministic SDK tests.
        service_locator: Read-only discovery seam for an SDK manager.
        provider_factory: Build a client from a model and base URL.
    """

    fixture_id: str | None = None

    def __init__(
        self,
        *,
        endpoint: str | None = None,
        transport: AsyncBaseTransport | None = None,
        service_locator: Callable[[str], tuple[str, str]] = _sdk_service,
        provider_factory: Callable[[str, str], _ChatClient] = _provider_client,
    ) -> None:
        """Record dependencies without importing or starting an SDK."""
        self.endpoint = endpoint
        self.transport = transport
        self.service_locator = service_locator
        self.provider_factory = provider_factory
        self.mode: Mode = "not_run"
        self.sdk_invoked = False
        self.network_attempted = False

    async def complete(self, prompt: str, model: str) -> LocalReply:
        """Resolve the model through the service and invoke it once."""
        from agent_framework.exceptions import ChatClientException
        from httpx2 import AsyncClient
        from openai import APIConnectionError, APIStatusError, AsyncOpenAI

        self.mode = "not_run"
        self.sdk_invoked = False
        self.network_attempted = False
        endpoint = self.endpoint
        if endpoint is None:
            endpoint, model = self.service_locator(model)
        base_url = _base_url(endpoint)
        self.sdk_invoked = True
        # Disable inherited proxies and retries: this is one local turn.
        async with AsyncOpenAI(
            base_url=base_url,
            api_key="none",
            max_retries=0,
            timeout=30.0,
            http_client=AsyncClient(transport=self.transport, trust_env=False),
        ) as api:
            try:
                return await self._complete(api, prompt, model, base_url)
            except (
                APIConnectionError,
                APIStatusError,
                ChatClientException,
            ) as error:
                cause = (
                    error.__cause__
                    if isinstance(error, ChatClientException)
                    else error
                )
                if isinstance(cause, APIConnectionError):
                    message = "The local service could not be reached in time."
                    code = "service_unavailable"
                    raise LocalServiceError(code, message) from error
                codes = {
                    401: "authorization_denied",
                    403: "authorization_denied",
                    429: "throttled",
                    503: "service_unavailable",
                }
                if (
                    not isinstance(cause, APIStatusError)
                    or cause.status_code not in codes
                ):
                    raise
                message = (
                    f"The local service returned HTTP {cause.status_code}."
                )
                raise LocalServiceError(
                    codes[cause.status_code], message
                ) from error

    async def _complete(
        self, api: AsyncOpenAI, prompt: str, model: str, base_url: str
    ) -> LocalReply:
        """Keep service discovery separate from a model invocation."""
        from agent_framework import Content, Message
        from agent_framework.openai import OpenAIChatCompletionClient

        self.mode = "live_service"
        self.network_attempted = True
        models = await api.models.list()
        available = [item.id for item in models.data]
        matches = [
            name
            for name in available
            if name.casefold().startswith(model.casefold() + "-")
        ]
        if model in available:
            resolved = model
        elif len(matches) == 1:
            resolved = matches[0]
        else:
            message = "Choose an unambiguous model ID from the local service."
            code = "model_unavailable"
            raise LocalServiceError(code, message)
        client = self.provider_factory(resolved, base_url)
        if isinstance(client, OpenAIChatCompletionClient):
            # Share transport, timeout and retry policy for both calls.
            # The outer context owns api; close the unused client first.
            await client.client.close()
            client.client = api
        self.mode = "live_model"
        response = await client.get_response(
            [Message(role="user", contents=[Content.from_text(prompt)])]
        )
        return LocalReply(response.text, response.model, base_url)


def _data(model: str) -> dict[str, object]:
    """Compute the arithmetic and enforce the approval policy."""
    cost = scenario.price_pilot()
    acceptable, failures = scenario.proposal_is_acceptable(
        cost=cost, approved=False, cited_sources=[]
    )
    return {
        "scenario_id": scenario.SCENARIO_ID,
        "requested_model": model,
        "cost": cost,
        "acceptable": acceptable,
        "acceptance_failures": failures,
        "connector_constraint": CONNECTOR_CONSTRAINT,
        "sdk_api_correction": SDK_CORRECTION,
        "sources": [INTEGRATION_SOURCE],
        "usage": None,
    }


async def run_foundry_local_demo(
    *,
    execution: str = "offline",
    port: FoundryLocalPort | None = None,
    environment: Mapping[str, str] | None = None,
) -> DemoResult:
    """Run a local model or explain the concrete missing prerequisite.

    Args:
        execution: ``offline`` fixture or ``live`` service discovery.
        port: Optional model/service seam for deterministic tests.
        environment: Environment snapshot; defaults to the process.

    Returns:
        An honest result with computed cost and pending human approval.
    """
    if execution not in {"offline", "live"}:
        message = "execution must be 'offline' or 'live'."
        raise ValueError(message)
    settings = os.environ if environment is None else environment
    model = settings.get("FOUNDRY_LOCAL_MODEL") or "phi-4-mini"
    selected = port
    if selected is None:
        selected = (
            LiveFoundryLocalPort(
                endpoint=settings.get("FOUNDRY_LOCAL_ENDPOINT") or None
            )
            if execution == "live"
            else FixtureFoundryLocalPort()
        )
    data = _data(model)
    prompt = f"{scenario.BRIEF} Computed pilot cost: {data['cost']}."
    try:
        reply = await selected.complete(prompt, model)
    except (ImportError, LocalServiceError) as error:
        code = "missing_sdk" if isinstance(error, ImportError) else error.code
        return result(
            demo=DEMO_NAME,
            technology=TECHNOLOGY,
            lane="current",
            mode=selected.mode,
            status="blocked",
            headline="Foundry Local needs a running local model service.",
            evidence=evidence(
                provider="foundry-local",
                sdk_invoked=selected.sdk_invoked,
                network_attempted=selected.network_attempted,
                fixture_id=selected.fixture_id,
                requested_model=model,
            ),
            error={
                "code": code,
                "message": (
                    "An optional local-model SDK is unavailable."
                    if isinstance(error, ImportError)
                    else str(error)
                ),
            },
            data=data,
            next_steps=[
                "Run uv sync to install foundry-local-sdk 2.0.1.",
                "Follow the linked Microsoft sample to initialize the SDK, "
                "download/load a model, and call start_web_service().",
                "Set FOUNDRY_LOCAL_ENDPOINT to manager.urls[0] and "
                "FOUNDRY_LOCAL_MODEL to model.id; rerun --execution live.",
            ],
        )
    valid = bool(reply.text.strip())
    data.update(answer=reply.text, endpoint=reply.endpoint)
    if reply.request is not None:
        data["request"] = reply.request
    success_headline = (
        "Synthetic local-model reply decoded; approval remains required."
        if selected.mode == "local_contract"
        else "One local model turn completed; approval remains required."
    )
    return result(
        demo=DEMO_NAME,
        technology=TECHNOLOGY,
        lane="current",
        mode=selected.mode,
        status="ok" if valid else "error",
        headline=(
            success_headline if valid else "The local model returned no text."
        ),
        evidence=evidence(
            provider="foundry-local",
            sdk_invoked=selected.sdk_invoked,
            network_attempted=selected.network_attempted,
            service_executed=selected.mode == "live_model",
            fixture_id=selected.fixture_id,
            requested_model=model,
            observed_model=reply.model,
        ),
        data=data,
        error=(
            None
            if valid
            else {
                "code": "malformed_response",
                "message": "The local model returned no text.",
            }
        ),
        next_steps=["Ground the answer and record a named human approval."],
    )

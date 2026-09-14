from __future__ import annotations

import asyncio
import json
import subprocess
import sys
from functools import partial
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import TYPE_CHECKING, cast

import httpx2
import pytest
from agent_framework.exceptions import ChatClientException
from openai import APIStatusError

from msai_demo import foundry_local_demo as demo
from msai_demo import scenario

if TYPE_CHECKING:
    from collections.abc import Sequence

    from agent_framework import Message
    from openai import AsyncOpenAI

    from msai_demo.contracts import DemoResult, Mode


class FakePort:
    fixture_id: str | None = "foundry-local-test-v1"
    sdk_invoked = False
    network_attempted = False
    mode: Mode = "local_contract"

    def __init__(
        self, *, error: Exception | None = None, text: str = "Draft"
    ) -> None:
        self.error = error
        self.text = text

    async def complete(self, prompt: str, model: str) -> demo.LocalReply:
        assert scenario.BRIEF in prompt
        assert str(scenario.price_pilot()["total"]) in prompt
        assert model
        if self.error is not None:
            raise self.error
        return demo.LocalReply(self.text, None, "http://localhost/v1")


def run(port: demo.FoundryLocalPort) -> DemoResult:
    return asyncio.run(demo.run_foundry_local_demo(port=port, environment={}))


def test_default_decodes_an_honest_offline_contract() -> None:
    result = asyncio.run(demo.run_foundry_local_demo())
    assert result["status"] == "ok"
    assert result["mode"] == "local_contract"
    assert result["error"] is None
    assert result["evidence"]["fixture_id"] == (
        "foundry-local-chat-completion-v1"
    )
    assert not result["evidence"]["sdk_invoked"]
    assert not result["evidence"]["network_attempted"]
    assert not result["evidence"]["service_executed"]
    assert result["evidence"]["observed_model"] == (
        "synthetic-foundry-local-model"
    )
    assert "Synthetic" in result["headline"]
    assert "Synthetic draft" in result["data"]["answer"]
    assert result["data"]["cost"] == scenario.price_pilot()
    assert not result["data"]["acceptable"]
    assert result["data"]["usage"] is None
    assert result["data"]["acceptance_failures"] == [
        "No human approval recorded.",
        "No grounding source cited.",
    ]
    assert "foundry_local_sdk" in result["data"]["sdk_api_correction"]
    assert result["next_steps"]


def test_offline_contract_contains_the_local_completion_request() -> None:
    result = asyncio.run(
        demo.run_foundry_local_demo(
            environment={"FOUNDRY_LOCAL_MODEL": "custom-local-alias"}
        )
    )
    assert result["evidence"]["requested_model"] == "custom-local-alias"
    assert result["data"]["request"] == {
        "method": "POST",
        "url": "http://localhost/v1/chat/completions",
        "body": {
            "model": "custom-local-alias",
            "messages": [
                {
                    "role": "user",
                    "content": (
                        f"{scenario.BRIEF} Computed pilot cost: "
                        f"{scenario.price_pilot()}."
                    ),
                }
            ],
            "stream": False,
        },
    }


def test_offline_contract_runs_without_optional_sdks() -> None:
    # -S removes site-packages, proving this contract needs no SDK.
    command = (
        "import asyncio, importlib.util, json, sys; "
        f"sys.path.insert(0, {str(Path(demo.__file__).parents[1])!r}); "
        "from msai_demo.foundry_local_demo import run_foundry_local_demo; "
        "assert importlib.util.find_spec('openai') is None; "
        "assert importlib.util.find_spec('foundry_local_sdk') is None; "
        "print(json.dumps(asyncio.run("
        "run_foundry_local_demo(environment={}))))"
    )
    completed = subprocess.run(  # noqa: S603 - Fixed code and interpreter.
        [sys.executable, "-I", "-S", "-c", command],
        check=True,
        capture_output=True,
        text=True,
    )
    result = json.loads(completed.stdout)
    assert result["mode"] == "local_contract"
    assert result["status"] == "ok"
    assert not result["evidence"]["sdk_invoked"]


def test_success_keeps_acceptance_pending() -> None:
    result = run(FakePort())
    assert result["status"] == "ok"
    assert not result["data"]["acceptable"]
    assert not result["evidence"]["service_executed"]
    assert result["data"]["usage"] is None
    assert (
        "No human approval recorded." in result["data"]["acceptance_failures"]
    )


def test_missing_sdk_is_safe_and_offline() -> None:
    result = run(FakePort(error=ImportError("private install path")))
    assert result["status"] == "blocked"
    assert result["error"]["code"] == "missing_sdk"
    assert "private install path" not in json.dumps(result)


def test_invalid_execution_is_rejected() -> None:
    with pytest.raises(ValueError, match="execution"):
        asyncio.run(demo.run_foundry_local_demo(execution="invalid"))


def test_empty_model_answer_is_rejected() -> None:
    result = run(FakePort(text="  "))
    assert result["status"] == "error"
    assert result["error"]["code"] == "malformed_response"


def sdk_loader(manager: object) -> ModuleType:
    module = ModuleType("test_sdk")
    module.FoundryLocalManager = SimpleNamespace(instance=manager)
    return module


@pytest.mark.parametrize("manager", [None, SimpleNamespace(urls=None)])
def test_sdk_discovery_requires_started_service(manager: object) -> None:
    with pytest.raises(demo.LocalServiceError, match="No running"):
        demo._sdk_service("phi", lambda _: sdk_loader(manager))


def test_live_missing_service_retains_the_install_instructions() -> None:
    result = asyncio.run(
        demo.run_foundry_local_demo(
            execution="live",
            environment={},
            port=demo.LiveFoundryLocalPort(
                service_locator=lambda model: demo._sdk_service(
                    model, lambda _: sdk_loader(None)
                )
            ),
        )
    )
    assert result["mode"] == "not_run"
    assert result["status"] == "blocked"
    assert result["error"] == {
        "code": "service_unavailable",
        "message": "No running SDK web service or local endpoint was found.",
    }
    assert result["evidence"]["fixture_id"] is None
    assert not result["evidence"]["network_attempted"]
    assert result["next_steps"] == [
        "Run uv sync to install foundry-local-sdk 2.0.1.",
        "Follow the linked Microsoft sample to initialize the SDK, "
        "download/load a model, and call start_web_service().",
        "Set FOUNDRY_LOCAL_ENDPOINT to manager.urls[0] and "
        "FOUNDRY_LOCAL_MODEL to model.id; rerun --execution live.",
    ]


@pytest.mark.parametrize("model", [None, SimpleNamespace(id="phi-cpu")])
def test_sdk_catalog_resolution(model: object) -> None:
    manager = SimpleNamespace(
        urls=["http://localhost:6789"],
        catalog=SimpleNamespace(get_model=lambda _: model),
    )
    if model is None:
        with pytest.raises(demo.LocalServiceError, match="alias"):
            demo._sdk_service("phi", lambda _: sdk_loader(manager))
    else:
        assert demo._sdk_service("phi", lambda _: sdk_loader(manager)) == (
            "http://localhost:6789",
            "phi-cpu",
        )


def test_live_runner_rejects_nonlocal_configuration() -> None:
    result = asyncio.run(
        demo.run_foundry_local_demo(
            execution="live",
            environment={
                "FOUNDRY_LOCAL_ENDPOINT": "http://remote.example",
            },
        )
    )
    assert result["mode"] == "not_run"
    assert result["error"]["code"] == "invalid_configuration"
    assert not result["evidence"]["network_attempted"]


@pytest.mark.parametrize(
    "endpoint",
    [
        "ftp://localhost",
        "http://example.com",
        "http://user@localhost",
        "http://user:secret@localhost",
        "http://localhost?token=secret",
        "http://localhost#fragment",
        "http://localhost/other",
    ],
)
def test_invalid_endpoint_never_leaks_credentials(endpoint: str) -> None:
    port = demo.LiveFoundryLocalPort(endpoint=endpoint)
    result = run(port)
    assert result["error"]["code"] == "invalid_configuration"
    assert result["mode"] == "not_run"
    assert "secret" not in json.dumps(result)


@pytest.mark.parametrize("path", ["", "/v1", "/v1/"])
def test_endpoint_normalization(path: str) -> None:
    assert demo._base_url("http://127.0.0.1:6543" + path) == (
        "http://127.0.0.1:6543/v1"
    )


def model_page(models: list[str]) -> dict[str, object]:
    return {
        "object": "list",
        "data": [
            {"id": model, "object": "model", "created": 1, "owned_by": "local"}
            for model in models
        ],
    }


def model_response() -> dict[str, object]:
    return {
        "id": "fixture-completion",
        "object": "chat.completion",
        "created": 1,
        "model": "phi-4-mini-cpu",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": "Draft proposal"},
                "finish_reason": "stop",
            }
        ],
    }


@pytest.mark.parametrize("alias", ["phi-4-mini", "phi-4-mini-cpu"])
def test_live_adapter_builds_real_sdk_requests(alias: str) -> None:
    requests: list[httpx2.Request] = []

    def respond(request: httpx2.Request) -> httpx2.Response:
        requests.append(request)
        payload = (
            model_page(["unrelated", "phi-4-mini-cpu"])
            if request.method == "GET"
            else model_response()
        )
        return httpx2.Response(200, json=payload)

    port = demo.LiveFoundryLocalPort(
        endpoint="http://localhost:6789",
        transport=httpx2.MockTransport(respond),
    )
    result = asyncio.run(
        demo.run_foundry_local_demo(
            port=port, environment={"FOUNDRY_LOCAL_MODEL": alias}
        )
    )
    assert result["status"] == "ok"
    assert result["mode"] == "live_model"
    assert "provider_fallback" not in result["data"]
    assert result["evidence"]["observed_model"] == "phi-4-mini-cpu"
    assert [request.url.path for request in requests] == [
        "/v1/models",
        "/v1/chat/completions",
    ]
    assert all(
        str(request.url).startswith("http://localhost:6789/v1/")
        for request in requests
    )
    request_body = json.loads(requests[1].content)
    assert request_body["model"] == "phi-4-mini-cpu"
    assert (
        str(scenario.price_pilot()["total"])
        in (request_body["messages"][0]["content"])
    )


@pytest.mark.parametrize("status", [200, 503])
def test_provider_http_clients_are_closed(status: int) -> None:
    from agent_framework.openai import (
        OpenAIChatCompletionClient,
        OpenAIChatCompletionOptions,
    )

    clients: list[OpenAIChatCompletionClient[OpenAIChatCompletionOptions]] = []
    original_clients: list[AsyncOpenAI] = []

    def create_client(model: str, base_url: str) -> demo._ChatClient:
        client: OpenAIChatCompletionClient[OpenAIChatCompletionOptions] = (
            OpenAIChatCompletionClient(
                model=model, base_url=base_url, api_key="none"
            )
        )
        clients.append(client)
        original_clients.append(client.client)
        return cast("demo._ChatClient", client)

    def respond(request: httpx2.Request) -> httpx2.Response:
        if request.method == "GET":
            return httpx2.Response(200, json=model_page(["phi-4-mini"]))
        assert original_clients[0].is_closed()
        assert not clients[0].client.is_closed()
        payload = (
            model_response()
            if status == 200
            else {"error": {"message": "unavailable"}}
        )
        return httpx2.Response(status, json=payload)

    result = run(
        demo.LiveFoundryLocalPort(
            endpoint="http://localhost:6789",
            transport=httpx2.MockTransport(respond),
            provider_factory=create_client,
        )
    )
    assert result["status"] == ("ok" if status == 200 else "blocked")
    assert len(clients) == 1
    assert clients[0].client is not original_clients[0]
    assert clients[0].client.is_closed()


@pytest.mark.parametrize("status", [401, 403, 429, 503])
@pytest.mark.parametrize("phase", ["list", "inference"])
def test_known_http_failures_are_blocked(status: int, phase: str) -> None:
    def respond(request: httpx2.Request) -> httpx2.Response:
        if phase == "inference" and request.method == "GET":
            return httpx2.Response(200, json=model_page(["phi-4-mini"]))
        return httpx2.Response(status, json={"error": {"message": "denied"}})

    result = run(
        demo.LiveFoundryLocalPort(
            endpoint="http://localhost:6789",
            transport=httpx2.MockTransport(respond),
        )
    )
    assert result["status"] == "blocked"
    assert result["mode"] == (
        "live_service" if phase == "list" else "live_model"
    )
    assert (
        result["error"]["code"]
        == {
            401: "authorization_denied",
            403: "authorization_denied",
            429: "throttled",
            503: "service_unavailable",
        }[status]
    )


@pytest.mark.parametrize("phase", ["list", "inference"])
def test_connection_failure_reports_unavailable(phase: str) -> None:
    def respond(request: httpx2.Request) -> httpx2.Response:
        if phase == "inference" and request.method == "GET":
            return httpx2.Response(200, json=model_page(["phi-4-mini"]))
        message = "synthetic refusal"
        raise httpx2.ConnectError(message, request=request)

    result = run(
        demo.LiveFoundryLocalPort(
            endpoint="http://localhost:6789",
            transport=httpx2.MockTransport(respond),
        )
    )
    assert result["error"]["code"] == "service_unavailable"
    assert result["evidence"]["network_attempted"]


@pytest.mark.parametrize("phase", ["list", "inference"])
def test_unexpected_http_error_propagates(phase: str) -> None:
    def respond(request: httpx2.Request) -> httpx2.Response:
        if phase == "inference" and request.method == "GET":
            return httpx2.Response(200, json=model_page(["phi-4-mini"]))
        return httpx2.Response(500, json={"error": "broken"})

    port = demo.LiveFoundryLocalPort(
        endpoint="http://localhost:6789",
        transport=httpx2.MockTransport(respond),
    )
    exception = APIStatusError if phase == "list" else ChatClientException
    with pytest.raises(exception):
        run(port)


@pytest.mark.parametrize(
    "models", [[], ["other"], ["phi-4-mini-a", "phi-4-mini-b"]]
)
def test_missing_or_ambiguous_models_are_blocked(models: list[str]) -> None:
    port = demo.LiveFoundryLocalPort(
        transport=httpx2.MockTransport(
            lambda _: httpx2.Response(200, json=model_page(models))
        ),
        service_locator=lambda model: ("http://localhost:6789", model),
    )
    result = run(port)
    assert result["error"]["code"] == "model_unavailable"
    assert result["mode"] == "live_service"


class FakeChatClient:
    async def get_response(
        self, messages: Sequence[Message]
    ) -> demo._Response:
        assert messages
        return cast(
            "demo._Response", SimpleNamespace(text="draft", model=None)
        )


def test_provider_factory_receives_discovered_endpoint() -> None:
    calls: list[tuple[str, str, str]] = []

    def create_client(
        provider: str, *, model_name: str, base_url: str
    ) -> object:
        calls.append((provider, model_name, base_url))
        return FakeChatClient()

    assert (
        demo.LiveFoundryLocalPort().provider_factory is demo._provider_client
    )
    port = demo.LiveFoundryLocalPort(
        transport=httpx2.MockTransport(
            lambda _: httpx2.Response(200, json=model_page(["phi-4-mini-cpu"]))
        ),
        service_locator=lambda _: (
            "http://localhost:6789/v1/",
            "phi-4-mini-cpu",
        ),
        provider_factory=partial(
            demo._provider_client, create_client=create_client
        ),
    )
    result = run(port)
    assert result["status"] == "ok"
    assert result["data"]["answer"] == "draft"
    assert "provider_fallback" not in result["data"]
    assert calls == [
        ("foundry-local", "phi-4-mini-cpu", "http://localhost:6789/v1")
    ]

    # Reusing a port must first clear evidence from its previous call.
    port.endpoint = "http://remote.example"
    result = run(port)
    assert result["mode"] == "not_run"
    assert not result["evidence"]["network_attempted"]
    assert len(calls) == 1


def test_unexpected_framework_failure_propagates() -> None:
    def fail(model: str, base_url: str) -> demo._ChatClient:
        del model, base_url
        message = "programming error"
        raise ChatClientException(message, inner_exception=ValueError(message))

    port = demo.LiveFoundryLocalPort(
        endpoint="http://localhost:6789",
        transport=httpx2.MockTransport(
            lambda _: httpx2.Response(200, json=model_page(["phi-4-mini"]))
        ),
        provider_factory=fail,
    )
    with pytest.raises(ChatClientException, match="programming error"):
        run(port)

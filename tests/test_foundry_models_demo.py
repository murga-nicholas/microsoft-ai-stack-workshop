from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, cast

import pytest

from msai_demo import scenario
from msai_demo.contracts import evidence, result
from msai_demo.foundry_models_demo import (
    HOSTED_TOOL_FACTORIES,
    FixtureModelsPort,
    FoundryCallError,
    LiveModelsPort,
    ModelsReply,
    ModelsRequest,
    _models_client,
    _translate_sdk_error,
    run_foundry_models_demo,
)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Callable
    from contextlib import AbstractAsyncContextManager

    from azure.ai.projects.aio import AIProjectClient
    from httpx2 import Request, Response
    from openai import AsyncOpenAI

    from msai_demo.foundry_models_demo import ModelsClient

SETTINGS = {
    "FOUNDRY_PROJECT_ENDPOINT": (
        "https://example.services.ai.azure.com/api/projects/workshop"
    ),
    "FOUNDRY_MODEL": "unit-test-deployment",
}


class PayloadPort(FixtureModelsPort):
    def __init__(self, payload: ModelsReply | Exception) -> None:
        super().__init__()
        self.payload = payload

    async def invoke(self, request: ModelsRequest) -> ModelsReply:
        del request
        if isinstance(self.payload, Exception):
            raise self.payload
        return self.payload


class ProjectClient:
    def __init__(self, client: AsyncOpenAI) -> None:
        self.client = client

    def get_openai_client(self) -> AsyncOpenAI:
        return self.client


def model_response() -> dict[str, object]:
    return {
        "id": "resp_fixture",
        "object": "response",
        "created_at": 0,
        "status": "completed",
        "model": "observed-model",
        "output": [
            {
                "id": "msg_fixture",
                "type": "message",
                "role": "assistant",
                "status": "completed",
                "content": [
                    {
                        "type": "output_text",
                        "text": "Draft awaits human approval.",
                        "annotations": [],
                    }
                ],
            }
        ],
    }


def client_factory(
    handler: Callable[[Request], Response],
) -> Callable[[ModelsRequest], AbstractAsyncContextManager[ModelsClient]]:
    @asynccontextmanager
    async def create(request: ModelsRequest) -> AsyncIterator[ModelsClient]:
        from agent_framework.foundry import FoundryChatClient
        from httpx2 import AsyncClient, MockTransport
        from openai import AsyncOpenAI

        async with (
            AsyncClient(transport=MockTransport(handler)) as http_client,
            AsyncOpenAI(
                api_key="fixture",
                base_url=f"{request.project_endpoint}/openai/v1",
                http_client=http_client,
                max_retries=0,
            ) as openai_client,
        ):
            project = ProjectClient(openai_client)
            client = FoundryChatClient(
                project_client=cast("AIProjectClient", project),
                model=request.model,
            )
            yield cast("ModelsClient", client)

    return create


def test_offline_runs_costing_and_approval_gate() -> None:
    response = asyncio.run(run_foundry_models_demo(environment={}))
    assert response["mode"] == "local_contract"
    assert response["status"] == "ok"
    assert response["evidence"] == evidence(
        provider="foundry",
        fixture_id="foundry-models-v1",
        requested_model="workshop-model-deployment",
    )
    data = response["data"]
    assert data is not None
    assert data["cost"] == scenario.price_pilot()
    assert data["accepted"] is False
    assert "No human approval recorded." in data["acceptance_failures"]
    assert data["usage"] is None
    assert "azure_endpoint=" in data["standalone_azure_openai"]
    assert str(scenario.price_pilot()["total"]) in data["request"]["prompt"]


def test_default_environment_and_injected_port() -> None:
    assert asyncio.run(run_foundry_models_demo())["status"] == "ok"
    response = asyncio.run(
        run_foundry_models_demo(port=FixtureModelsPort(), environment=SETTINGS)
    )
    assert response["evidence"]["requested_model"] == "unit-test-deployment"


@pytest.mark.parametrize(
    "settings",
    [{}, {"FOUNDRY_PROJECT_ENDPOINT": " "}, SETTINGS | {"FOUNDRY_MODEL": ""}],
)
def test_missing_configuration(settings: dict[str, str]) -> None:
    response = asyncio.run(
        run_foundry_models_demo(execution="live", environment=settings)
    )
    assert response["mode"] == "not_run"
    assert response["error"]["code"] == "missing_configuration"
    assert response["evidence"]["network_attempted"] is False


def test_configured_live_selection_uses_injected_factory() -> None:
    port = FixtureModelsPort()
    response = asyncio.run(
        run_foundry_models_demo(
            execution="live",
            environment=SETTINGS,
            live_port_factory=lambda: port,
        )
    )
    assert response["mode"] == "local_contract"


def test_invalid_execution_is_rejected() -> None:
    with pytest.raises(ValueError, match="execution must"):
        asyncio.run(run_foundry_models_demo(execution="typo"))


def test_missing_sdk_is_not_a_live_attempt() -> None:
    response = asyncio.run(
        run_foundry_models_demo(
            port=PayloadPort(ModuleNotFoundError("optional package"))
        )
    )
    assert response["mode"] == "not_run"
    assert response["error"]["code"] == "missing_sdk"
    assert response["evidence"]["sdk_invoked"] is False


@pytest.mark.parametrize("payload", [{}, {"text": None}, {"text": " "}])
def test_malformed_response(payload: dict[str, object]) -> None:
    response = asyncio.run(
        run_foundry_models_demo(port=PayloadPort(cast("ModelsReply", payload)))
    )
    assert response["status"] == "error"
    assert response["error"]["code"] == "malformed_response"


def test_unknown_failure_propagates() -> None:
    with pytest.raises(RuntimeError, match="unexpected"):
        asyncio.run(
            run_foundry_models_demo(
                port=PayloadPort(RuntimeError("unexpected"))
            )
        )


def test_installed_factory_inventory_and_default_sdk_lifecycle() -> None:
    from agent_framework.foundry import FoundryChatClient

    observed = {
        name
        for name in dir(FoundryChatClient)
        if name.startswith("get_") and name.endswith("_tool")
    }
    assert observed == set(HOSTED_TOOL_FACTORIES) | {"get_shell_tool"}
    assert (
        getattr(FoundryChatClient.get_shell_tool, "__feature_id__", None)
        is None
    )
    for name, stage in HOSTED_TOOL_FACTORIES.items():
        method = getattr(FoundryChatClient, name)
        metadata = getattr(method, "__feature_id__", None)
        if stage == "preview":
            assert metadata == "FOUNDRY_PREVIEW_TOOLS"
        elif stage == "experimental":
            assert metadata == "FOUNDRY_TOOLS"
        else:
            assert metadata is None

    async def construct() -> None:
        request = ModelsRequest(
            SETTINGS["FOUNDRY_PROJECT_ENDPOINT"], "test-deployment", "hello"
        )
        async with _models_client(request) as client:
            assert isinstance(client, FoundryChatClient)

    asyncio.run(construct())


def test_real_sdk_serializes_and_decodes_over_injected_transport() -> None:
    from httpx2 import Response

    requests: list[dict[str, object]] = []

    def handler(request: Request) -> Response:
        requests.append(json.loads(request.content))
        return Response(200, json=model_response())

    port = LiveModelsPort(client_factory(handler))
    response = asyncio.run(
        run_foundry_models_demo(port=port, environment=SETTINGS)
    )
    assert response["mode"] == "live_model"
    assert response["evidence"]["observed_model"] == "observed-model"
    assert response["evidence"]["service_executed"] is True
    assert response["data"]["reply"]["text"] == "Draft awaits human approval."
    assert requests[0]["model"] == "unit-test-deployment"
    assert str(scenario.price_pilot()["total"]) in json.dumps(requests[0])


@pytest.mark.parametrize(
    "status, code",
    [
        (401, "authorization_denied"),
        (403, "authorization_denied"),
        (429, "throttled"),
    ],
)
def test_known_http_failures(status: int, code: str) -> None:
    from httpx2 import Response

    def handler(request: Request) -> Response:
        del request
        return Response(status, json={"error": {"message": "do-not-echo"}})

    response = asyncio.run(
        run_foundry_models_demo(port=LiveModelsPort(client_factory(handler)))
    )
    assert response["mode"] == "live_model"
    assert response["status"] == "blocked"
    assert response["error"]["code"] == code
    assert response["evidence"]["service_executed"] is False
    assert "do-not-echo" not in str(response)


@pytest.mark.parametrize("timeout", [False, True])
def test_known_transport_failures(timeout: bool) -> None:
    from httpx2 import ConnectError, ReadTimeout

    def handler(request: Request) -> Response:
        exception = ReadTimeout if timeout else ConnectError
        message = "do-not-echo"
        raise exception(message, request=request)

    response = asyncio.run(
        run_foundry_models_demo(port=LiveModelsPort(client_factory(handler)))
    )
    assert response["mode"] == "live_model"
    assert response["error"]["code"] == (
        "timeout" if timeout else "service_unavailable"
    )


def test_unrecognized_http_error_propagates() -> None:
    from agent_framework.exceptions import ChatClientException
    from httpx2 import Response

    def handler(request: Request) -> Response:
        del request
        return Response(500, json={"error": {"message": "unexpected"}})

    with pytest.raises(ChatClientException):
        asyncio.run(
            run_foundry_models_demo(
                port=LiveModelsPort(client_factory(handler))
            )
        )


def test_credentials_fail_before_model_request() -> None:
    from agent_framework.exceptions import ChatClientException
    from azure.identity import CredentialUnavailableError

    class UnavailableClient:
        async def get_response(self, messages: str) -> object:
            del messages
            cause = CredentialUnavailableError("do-not-echo")
            message = "credentials unavailable"
            raise ChatClientException(message) from cause

    @asynccontextmanager
    async def create(request: ModelsRequest) -> AsyncIterator[ModelsClient]:
        del request
        yield cast("ModelsClient", UnavailableClient())

    response = asyncio.run(
        run_foundry_models_demo(port=LiveModelsPort(create))
    )
    assert response["mode"] == "not_run"
    assert response["error"]["code"] == "credential_unavailable"
    assert response["evidence"]["network_attempted"] is False


def test_bare_known_and_unknown_sdk_errors() -> None:
    from azure.core.exceptions import ClientAuthenticationError

    mapped = _translate_sdk_error(
        ClientAuthenticationError("do-not-echo"), evidence(provider="foundry")
    )
    assert isinstance(mapped, FoundryCallError)
    assert mapped.code == "credential_unavailable"
    with pytest.raises(ValueError, match="unexpected"):
        _translate_sdk_error(
            ValueError("unexpected"), evidence(provider="foundry")
        )


@pytest.mark.parametrize(
    "mode, record",
    [
        ("live_service", evidence(provider="test")),
        ("local_contract", evidence(provider="test")),
        ("local_execution", evidence(provider="test", service_executed=True)),
    ],
)
def test_contract_rejects_dishonest_evidence(
    mode: str, record: object
) -> None:
    from msai_demo.contracts import Evidence, Mode

    with pytest.raises(ValueError):
        result(
            demo="test",
            technology="test",
            lane="current",
            mode=cast("Mode", mode),
            status="ok",
            headline="test",
            evidence=cast("Evidence", record),
        )

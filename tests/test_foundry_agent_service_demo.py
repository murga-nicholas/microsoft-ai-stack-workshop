from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, cast

import pytest

from msai_demo import scenario
from msai_demo.foundry_agent_service_demo import (
    AgentServiceReply,
    AgentServiceRequest,
    FixtureAgentServicePort,
    LiveAgentServicePort,
    _agent_client,
    run_foundry_agent_service_demo,
)
from tests.test_foundry_models_demo import ProjectClient, model_response

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Callable
    from contextlib import AbstractAsyncContextManager

    from azure.ai.projects.aio import AIProjectClient
    from httpx2 import Request, Response

    from msai_demo.foundry_agent_service_demo import AgentClient

SETTINGS = {
    "FOUNDRY_PROJECT_ENDPOINT": (
        "https://example.services.ai.azure.com/api/projects/workshop"
    ),
    "FOUNDRY_AGENT_NAME": "support-pilot",
    "FOUNDRY_AGENT_VERSION": "1",
}


class PayloadPort(FixtureAgentServicePort):
    def __init__(self, payload: AgentServiceReply | Exception) -> None:
        super().__init__()
        self.payload = payload

    async def invoke(self, request: AgentServiceRequest) -> AgentServiceReply:
        del request
        if isinstance(self.payload, Exception):
            raise self.payload
        return self.payload


def client_factory(
    handler: Callable[[Request], Response],
) -> Callable[[AgentServiceRequest], AbstractAsyncContextManager[AgentClient]]:
    @asynccontextmanager
    async def create(
        request: AgentServiceRequest,
    ) -> AsyncIterator[AgentClient]:
        from agent_framework.foundry import FoundryAgent
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
            agent = FoundryAgent(
                project_client=cast("AIProjectClient", project),
                agent_name=request.agent_name,
                agent_version=request.agent_version,
            )
            yield cast("AgentClient", agent)

    return create


def test_offline_contract_and_human_gate() -> None:
    response = asyncio.run(run_foundry_agent_service_demo(environment={}))
    assert response["status"] == "ok"
    assert response["mode"] == "local_contract"
    assert response["evidence"]["fixture_id"] == "foundry-agent-service-v1"
    assert response["evidence"]["sdk_invoked"] is False
    data = response["data"]
    assert data is not None
    assert data["cost"] == scenario.price_pilot()
    assert data["accepted"] is False
    assert "No human approval recorded." in data["acceptance_failures"]
    assert data["connected_agents"]["status"] == "preview"
    assert data["multi_agent_workflows"]["status"] == "preview"
    assert data["request"]["agent_version"] is None
    assert data["usage"] is None


def test_default_environment_and_injected_port() -> None:
    assert asyncio.run(run_foundry_agent_service_demo())["status"] == "ok"
    response = asyncio.run(
        run_foundry_agent_service_demo(
            port=FixtureAgentServicePort(), environment=SETTINGS
        )
    )
    assert response["data"]["request"]["agent_version"] == "1"


@pytest.mark.parametrize(
    "settings", [{}, SETTINGS | {"FOUNDRY_AGENT_NAME": " "}]
)
def test_missing_configuration(settings: dict[str, str]) -> None:
    response = asyncio.run(
        run_foundry_agent_service_demo(execution="live", environment=settings)
    )
    assert response["mode"] == "not_run"
    assert response["error"]["code"] == "missing_configuration"


def test_live_selection_factory() -> None:
    response = asyncio.run(
        run_foundry_agent_service_demo(
            execution="live",
            environment=SETTINGS,
            live_port_factory=FixtureAgentServicePort,
        )
    )
    assert response["status"] == "ok"


def test_invalid_execution() -> None:
    with pytest.raises(ValueError, match="execution must"):
        asyncio.run(run_foundry_agent_service_demo(execution="typo"))


def test_missing_sdk_is_blocked() -> None:
    response = asyncio.run(
        run_foundry_agent_service_demo(
            port=PayloadPort(ModuleNotFoundError("optional SDK"))
        )
    )
    assert response["mode"] == "not_run"
    assert response["error"]["code"] == "missing_sdk"
    assert response["evidence"]["network_attempted"] is False


@pytest.mark.parametrize("payload", [{}, {"text": None}, {"text": " "}])
def test_malformed_response(payload: dict[str, object]) -> None:
    response = asyncio.run(
        run_foundry_agent_service_demo(
            port=PayloadPort(cast("AgentServiceReply", payload))
        )
    )
    assert response["status"] == "error"
    assert response["error"]["code"] == "malformed_response"


def test_default_sdk_lifecycle_without_network() -> None:
    from agent_framework.foundry import FoundryAgent

    async def construct() -> None:
        request = AgentServiceRequest(
            SETTINGS["FOUNDRY_PROJECT_ENDPOINT"], "test-agent", "1", "hello"
        )
        async with _agent_client(request) as agent:
            assert isinstance(agent, FoundryAgent)

    asyncio.run(construct())


@pytest.mark.parametrize("version", [None, "1"])
def test_real_sdk_named_agent_request(version: str | None) -> None:
    from httpx2 import Response

    requests: list[dict[str, object]] = []

    def handler(request: Request) -> Response:
        requests.append(json.loads(request.content))
        return Response(200, json=model_response())

    settings = SETTINGS | {"FOUNDRY_AGENT_VERSION": version or ""}
    response = asyncio.run(
        run_foundry_agent_service_demo(
            port=LiveAgentServicePort(client_factory(handler)),
            environment=settings,
        )
    )
    assert response["mode"] == "live_service"
    assert response["status"] == "ok"
    assert response["evidence"]["service_executed"] is True
    assert response["data"]["reply"]["response_id"] == "resp_fixture"
    expected = {"type": "agent_reference", "name": "support-pilot"}
    if version:
        expected["version"] = version
    assert requests[0]["agent_reference"] == expected
    assert "model" not in requests[0]
    assert str(scenario.price_pilot()["total"]) in json.dumps(requests[0])


def test_403_is_a_blocked_live_service_demonstration() -> None:
    from httpx2 import Response

    def handler(request: Request) -> Response:
        del request
        return Response(403, json={"error": {"message": "do-not-echo"}})

    response = asyncio.run(
        run_foundry_agent_service_demo(
            port=LiveAgentServicePort(client_factory(handler))
        )
    )
    assert response["mode"] == "live_service"
    assert response["status"] == "blocked"
    assert response["error"]["code"] == "authorization_denied"
    assert response["evidence"]["network_attempted"] is True
    assert response["evidence"]["service_executed"] is False
    assert "do-not-echo" not in str(response)


def test_credentials_fail_before_service_request() -> None:
    from agent_framework.exceptions import ChatClientException
    from azure.identity import CredentialUnavailableError

    class UnavailableAgent:
        async def run(self, messages: str) -> object:
            del messages
            cause = CredentialUnavailableError("do-not-echo")
            message = "credentials unavailable"
            raise ChatClientException(message) from cause

    @asynccontextmanager
    async def create(
        request: AgentServiceRequest,
    ) -> AsyncIterator[AgentClient]:
        del request
        yield cast("AgentClient", UnavailableAgent())

    response = asyncio.run(
        run_foundry_agent_service_demo(port=LiveAgentServicePort(create))
    )
    assert response["mode"] == "not_run"
    assert response["error"]["code"] == "credential_unavailable"
    assert response["evidence"]["network_attempted"] is False


def test_unexpected_failure_propagates() -> None:
    with pytest.raises(RuntimeError, match="unexpected"):
        asyncio.run(
            run_foundry_agent_service_demo(
                port=PayloadPort(RuntimeError("unexpected"))
            )
        )

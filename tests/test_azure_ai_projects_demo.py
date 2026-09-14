from __future__ import annotations

import asyncio
import json
from contextlib import contextmanager
from functools import partial
from typing import TYPE_CHECKING, Any

import pytest

from msai_demo import azure_ai_projects_demo as demo

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator, Mapping, Sequence

    from azure.core.pipeline.transport import HttpTransport

ENDPOINT = "https://fixture.services.ai.azure.com/api/projects/workshop"


class ScriptedPort(demo.FixtureProjectsPort):
    def __init__(
        self,
        rows: Sequence[Mapping[str, object]] = (),
        failure: Exception | None = None,
    ) -> None:
        self.rows = rows
        self.failure = failure

    async def list_deployments(self) -> Sequence[Mapping[str, object]]:
        if self.failure is not None:
            raise self.failure
        return self.rows


def run(**kwargs: Any) -> demo.DemoResult:
    return asyncio.run(demo.run_azure_ai_projects_demo(**kwargs))


def test_offline_and_empty_deployments() -> None:
    actual = run()
    assert actual["mode"] == "local_contract"
    assert actual["status"] == "ok"
    assert actual["evidence"]["fixture_id"] == demo.FIXTURE_ID
    assert not actual["evidence"]["network_attempted"]
    assert not actual["evidence"]["sdk_invoked"]
    assert actual["data"] is not None
    assert "azure-ai-agents 1.1.0" in actual["data"]["supersedes"]
    assert not actual["data"]["acceptable"]
    assert actual["data"]["cost"] == demo.scenario.price_pilot()
    empty = run(port=ScriptedPort())
    assert empty["data"] is not None
    assert empty["data"]["deployments"] == []


@pytest.mark.parametrize("settings", [{}, {"FOUNDRY_PROJECT_ENDPOINT": " "}])
def test_configuration(settings: dict[str, str]) -> None:
    actual = run(execution="live", environment=settings)
    assert actual["mode"] == "not_run"
    assert actual["error"] is not None
    assert actual["error"]["code"] == "missing_configuration"


def test_default_environment_and_live_factory() -> None:
    # The injected factory cannot contact Azure.
    actual = run(
        execution="live",
        live_port_factory=lambda _: demo.FixtureProjectsPort(),
    )
    assert actual["mode"] in {"not_run", "local_contract"}
    calls: list[str] = []

    def factory(endpoint: str) -> demo.ProjectsPort:
        calls.append(endpoint)
        return demo.FixtureProjectsPort()

    actual = run(
        execution="live",
        environment={"FOUNDRY_PROJECT_ENDPOINT": ENDPOINT},
        live_port_factory=factory,
    )
    assert calls == [ENDPOINT]
    assert actual["status"] == "ok"


def test_invalid_execution_and_unknown_failures() -> None:
    with pytest.raises(ValueError, match="execution"):
        run(execution="typo")
    with pytest.raises(RuntimeError, match="programming defect"):
        run(port=ScriptedPort(failure=RuntimeError("programming defect")))


@pytest.mark.parametrize("value", [None, "", " ", 42])
def test_malformed_response(value: object) -> None:
    actual = run(port=ScriptedPort(rows=[{"name": value}]))
    assert actual["status"] == "error"
    assert actual["error"] is not None
    assert actual["error"]["code"] == "malformed_response"


def test_import_failure_is_reported() -> None:
    actual = run(port=ScriptedPort(failure=ModuleNotFoundError("sdk absent")))
    assert actual["error"] is not None
    assert actual["error"]["code"] == "missing_sdk"
    assert not actual["evidence"]["sdk_invoked"]


def transport_factory(
    *, status: int = 200, failure: Exception | None = None
) -> tuple[HttpTransport, list[object]]:
    from azure.core.pipeline.transport import HttpResponse, HttpTransport

    requests: list[object] = []

    class Response(HttpResponse):
        def __init__(self, request: Any) -> None:
            super().__init__(request, None)
            self.status_code = status
            self.reason = "synthetic transport response"
            self.headers = {"content-type": "application/json"}
            self.content_type = "application/json"

        def body(self) -> bytes:
            return json.dumps(self.json()).encode()

        def json(self) -> dict[str, object]:
            if status != 200:
                return {"error": {"code": "Denied", "message": "fixture"}}
            return {
                "value": [
                    {
                        "name": "support-pilot-fixture",
                        "type": "ModelDeployment",
                        "modelName": "fixture-model",
                        "modelVersion": "fixture-version",
                        "modelPublisher": "fixture-publisher",
                    }
                ]
            }

    class Transport(HttpTransport):
        def __enter__(self) -> Transport:
            return self

        def __exit__(self, *args: object) -> None:
            self.close()

        def open(self) -> None:
            pass

        def close(self) -> None:
            pass

        def send(self, request: Any, **kwargs: Any) -> Response:
            del kwargs
            requests.append(request)
            if failure is not None:
                raise failure
            return Response(request)

    return Transport(), requests


def live_port(
    *, status: int = 200, failure: Exception | None = None
) -> tuple[demo.LiveProjectsPort, list[object]]:
    from azure.core.credentials import AccessToken

    class Credential:
        def get_token(self, *scopes: str, **kwargs: object) -> AccessToken:
            del scopes, kwargs
            return AccessToken("synthetic-test-token", 4_000_000_000)

    transport, requests = transport_factory(status=status, failure=failure)
    return (
        demo.LiveProjectsPort(
            ENDPOINT,
            open_client=partial(
                demo._open_projects,
                credential=Credential(),
                transport=transport,
            ),
        ),
        requests,
    )


def test_real_sdk_serializes_the_read_and_decodes_fixture() -> None:
    port, requests = live_port()
    actual = run(port=port)
    assert actual["mode"] == "live_service"
    assert actual["status"] == "ok"
    assert actual["evidence"]["sdk_invoked"]
    assert actual["evidence"]["service_executed"]
    assert len(requests) == 1
    request = requests[0]
    assert request.method == "GET"
    assert "/deployments?" in request.url
    assert "deploymentType=ModelDeployment" in request.url
    assert actual["data"] is not None
    assert actual["data"]["deployments"][0]["model_name"] == "fixture-model"


@pytest.mark.parametrize("status", [401, 403, 429])
def test_http_boundaries(status: int) -> None:
    port, requests = live_port(status=status)
    actual = run(port=port)
    assert actual["mode"] == "live_service"
    assert actual["status"] == "blocked"
    assert actual["error"] is not None
    expected = "throttled" if status == 429 else "authorization_denied"
    assert actual["error"]["code"] == expected
    assert actual["evidence"]["network_attempted"]
    assert not actual["evidence"]["service_executed"]
    assert len(requests) == 1


def test_unknown_http_failure_is_not_manufactured_success() -> None:
    from azure.core.exceptions import HttpResponseError

    port, _ = live_port(status=500)
    with pytest.raises(HttpResponseError):
        run(port=port)


def test_transport_failure() -> None:
    from azure.core.exceptions import ServiceRequestError

    port, requests = live_port(failure=ServiceRequestError("fixture timeout"))
    actual = run(port=port)
    assert actual["mode"] == "live_service"
    assert actual["error"] is not None
    assert actual["error"]["code"] == "service_unavailable"
    assert len(requests) == 1


def test_missing_credential_never_claims_a_request() -> None:
    from azure.core.exceptions import ClientAuthenticationError

    @contextmanager
    def unavailable(endpoint: str) -> Iterator[demo._ProjectsClient]:
        del endpoint
        message = "credentials absent"
        raise ClientAuthenticationError(message)
        yield  # pragma: no cover

    actual = run(port=demo.LiveProjectsPort(ENDPOINT, open_client=unavailable))
    assert actual["mode"] == "not_run"
    assert actual["error"] is not None
    assert actual["error"]["code"] == "authentication_unavailable"
    assert not actual["evidence"]["network_attempted"]


def test_sdk_creation_does_not_acquire_a_token() -> None:
    with demo._open_projects(ENDPOINT) as client:
        assert callable(client.deployments.list)


def test_port_reuse_resets_evidence() -> None:
    from azure.core.exceptions import ClientAuthenticationError

    attempts = 0

    class Deployments:
        def list(
            self,
            *,
            deployment_type: str,
            raw_request_hook: Callable[[object], None],
        ) -> list[Mapping[str, object]]:
            nonlocal attempts
            assert deployment_type == "ModelDeployment"
            attempts += 1
            if attempts == 1:
                raw_request_hook(object())
                return []
            message = "no credential on second request"
            raise ClientAuthenticationError(message)

    class Client:
        deployments = Deployments()

    @contextmanager
    def open_client(endpoint: str) -> Iterator[Client]:
        assert endpoint == ENDPOINT
        yield Client()

    port = demo.LiveProjectsPort(ENDPOINT, open_client=open_client)
    assert run(port=port)["status"] == "ok"
    actual = run(port=port)
    assert actual["mode"] == "not_run"
    assert not actual["evidence"]["service_executed"]

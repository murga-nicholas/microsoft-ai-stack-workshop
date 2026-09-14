"""Microsoft Foundry's current project control-plane SDK.

List model deployments with ``azure-ai-projects`` 2.6.0. A synthetic
deployment proves the application contract offline; a real 403 shows
why an Entra token alone does not grant access to a Foundry project.

Run it:

    uv run msai-demo azure-ai-projects
    uv run msai-demo azure-ai-projects --execution live
"""

from __future__ import annotations

import asyncio
import os
from contextlib import contextmanager
from typing import TYPE_CHECKING, Protocol, TypedDict, cast

from msai_demo import scenario
from msai_demo.contracts import (
    DemoResult,
    Mode,
    Status,
    evidence,
    missing_configuration,
    result,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
    from contextlib import AbstractContextManager

    from azure.core.credentials import TokenCredential
    from azure.core.pipeline.transport import HttpTransport
    from azure.core.rest import HttpRequest, HttpResponse

DEMO_NAME = "azure-ai-projects"
TECHNOLOGY = "Microsoft Foundry control plane (azure-ai-projects 2.6.0)"
FIXTURE_ID = "azure-ai-projects-deployments-v1"


class Deployment(TypedDict):
    """The non-secret fields needed to choose a model deployment."""

    name: str
    model_name: str
    model_version: str
    publisher: str


class ProjectsPort(Protocol):
    """One read operation and the evidence it actually produced."""

    mode: Mode
    fixture_id: str | None
    sdk_invoked: bool
    network_attempted: bool
    service_executed: bool

    async def list_deployments(self) -> Sequence[Mapping[str, object]]:
        """Return deployment fields using the service's JSON names."""
        raise NotImplementedError


class FixtureProjectsPort:
    """Supply a named synthetic deployment without requiring any SDK."""

    mode: Mode = "local_contract"
    fixture_id: str | None = FIXTURE_ID
    sdk_invoked = False
    network_attempted = False
    service_executed = False

    async def list_deployments(self) -> Sequence[Mapping[str, object]]:
        """Return synthetic deployment metadata."""
        return [
            {
                "name": "support-pilot-model-fixture",
                "type": "ModelDeployment",
                "modelName": "illustrative-chat-model",
                "modelVersion": "fixture-v1",
                "modelPublisher": "workshop-fixture",
            }
        ]


class ProjectsError(Exception):
    """A known service failure with safe, actionable public wording.

    Args:
        code: Stable error identifier.
        message: Credential-free explanation.
        status: Whether the request was blocked or failed.
    """

    def __init__(
        self, code: str, message: str, status: Status = "blocked"
    ) -> None:
        """Keep vendor exception details out of the public envelope."""
        super().__init__(message)
        self.code = code
        self.status = status


class _DeploymentsClient(Protocol):
    def list(
        self,
        *,
        deployment_type: str,
        raw_request_hook: Callable[[object], None],
    ) -> Iterable[Mapping[str, object]]:
        raise NotImplementedError


class _ProjectsClient(Protocol):
    deployments: _DeploymentsClient


@contextmanager
def _open_projects(
    endpoint: str,
    *,
    credential: TokenCredential | None = None,
    transport: HttpTransport[HttpRequest, HttpResponse] | None = None,
) -> Iterator[_ProjectsClient]:
    """Own SDK resources; accept a transport for offline SDK testing."""
    from azure.ai.projects import AIProjectClient
    from azure.identity import DefaultAzureCredential

    if credential is None:
        with (
            DefaultAzureCredential() as default_credential,
            _open_projects(
                endpoint, credential=default_credential, transport=transport
            ) as client,
        ):
            yield client
        return
    with AIProjectClient(
        endpoint=endpoint,
        credential=credential,
        transport=transport,
        retry_total=0,
        connection_timeout=10,
        read_timeout=30,
    ) as sdk_client:
        yield cast("_ProjectsClient", sdk_client)


class LiveProjectsPort:
    """List deployments through the real Foundry project SDK.

    Args:
        endpoint: Foundry project endpoint, without credentials.
        open_client: Resource factory with an injectable transport.
    """

    mode: Mode = "live_service"
    fixture_id: str | None = None

    def __init__(
        self,
        endpoint: str,
        *,
        open_client: Callable[
            [str], AbstractContextManager[_ProjectsClient]
        ] = _open_projects,
    ) -> None:
        """Save configuration without contacting Azure."""
        self.endpoint = endpoint
        self._open_client = open_client
        self.sdk_invoked = False
        self.network_attempted = False
        self.service_executed = False

    async def list_deployments(self) -> Sequence[Mapping[str, object]]:
        """Run synchronous paging away from the event loop."""
        return await asyncio.to_thread(self._list_deployments)

    def _record_request(self, request: object) -> None:
        """Record a request after SDK authentication."""
        del request
        self.network_attempted = True

    def _list_deployments(self) -> Sequence[Mapping[str, object]]:
        from azure.core.exceptions import (
            HttpResponseError,
            ServiceRequestError,
            ServiceResponseError,
        )

        self.sdk_invoked = False
        self.network_attempted = False
        self.service_executed = False
        try:
            with self._open_client(self.endpoint) as client:
                self.sdk_invoked = True
                rows = list(
                    client.deployments.list(
                        deployment_type="ModelDeployment",
                        raw_request_hook=self._record_request,
                    )
                )
                self.service_executed = True
                return rows
        except HttpResponseError as exc:
            if exc.status_code in {401, 403}:
                msg = "authorization_denied"
                raise ProjectsError(
                    msg,
                    "Entra identity lacks access to this Foundry project.",
                ) from exc
            if exc.status_code == 429:
                msg = "throttled"
                raise ProjectsError(
                    msg, "Foundry throttled this read; retry later."
                ) from exc
            if exc.status_code is None:
                msg = "authentication_unavailable"
                raise ProjectsError(
                    msg,
                    "Configure a usable Microsoft Entra credential.",
                ) from exc
            raise
        except (
            ServiceRequestError,
            ServiceResponseError,
            TimeoutError,
        ) as exc:
            msg = "service_unavailable"
            raise ProjectsError(
                msg,
                "The Foundry project did not answer; check connectivity.",
            ) from exc


def _decode_deployments(
    rows: Sequence[Mapping[str, object]],
) -> list[Deployment]:
    """Reject incomplete deployment metadata."""
    deployments: list[Deployment] = []
    for row in rows:
        values = [
            row.get(key)
            for key in ("name", "modelName", "modelVersion", "modelPublisher")
        ]
        if not all(
            isinstance(value, str) and value.strip() for value in values
        ):
            message = "Deployment metadata contains missing or invalid fields."
            raise ValueError(message)
        name, model, version, publisher = cast("list[str]", values)
        deployments.append(
            Deployment(
                name=name,
                model_name=model,
                model_version=version,
                publisher=publisher,
            )
        )
    return sorted(deployments, key=lambda item: item["name"])


def _envelope(
    port: ProjectsPort,
    *,
    deployments: list[Deployment] | None = None,
    failure: ProjectsError | None = None,
) -> DemoResult:
    """Keep control-plane access separate from proposal acceptance."""
    mode = port.mode
    if mode == "live_service" and not port.network_attempted:
        mode = "not_run"
    cost = scenario.price_pilot()
    acceptable, reasons = scenario.proposal_is_acceptable(
        cost=cost, approved=False, cited_sources=[]
    )
    return result(
        demo=DEMO_NAME,
        technology=TECHNOLOGY,
        lane="current",
        mode=mode,
        status=failure.status if failure else "ok",
        headline=(
            str(failure)
            if failure
            else "Deployment metadata decoded; the pilot awaits approval."
        ),
        evidence=evidence(
            provider="microsoft-foundry",
            sdk_invoked=port.sdk_invoked,
            network_attempted=port.network_attempted,
            service_executed=port.service_executed,
            fixture_id=port.fixture_id,
        ),
        data={
            "request": {
                "operation": "AIProjectClient.deployments.list",
                "endpoint": "FOUNDRY_PROJECT_ENDPOINT",
                "credential": "Microsoft Entra DefaultAzureCredential",
                "deployment_type": "ModelDeployment",
            },
            "deployments": deployments,
            "supersedes": (
                "azure-ai-agents 1.1.0 is superseded by "
                "azure-ai-projects 2.6.0 for the current Foundry runtime."
            ),
            "operation_groups": [
                "agents",
                "toolboxes",
                "deployments",
                "connections",
                "datasets",
                "indexes",
                "evaluations",
                "memory stores",
                "skills",
                "red teams",
            ],
            "operation_note": (
                "Some preview groups are accessed through client.beta; "
                "this demo uses only the deployments read operation."
            ),
            "scenario": scenario.BRIEF,
            "cost": cost,
            "acceptable": acceptable,
            "acceptance_failures": reasons,
            "usage": None,
        },
        error={"code": failure.code, "message": str(failure)}
        if failure
        else None,
        next_steps=[
            "Grant a project role that permits reading deployments.",
            "Obtain a named human approval before accepting the pilot.",
        ],
    )


async def run_azure_ai_projects_demo(
    *,
    execution: str = "offline",
    port: ProjectsPort | None = None,
    environment: Mapping[str, str] | None = None,
    live_port_factory: Callable[[str], ProjectsPort] = LiveProjectsPort,
) -> DemoResult:
    """Decode deployment metadata or demonstrate an access boundary.

    Args:
        execution: ``offline`` or ``live``.
        port: External read seam, used directly when supplied.
        environment: Configuration source; defaults to the process.
        live_port_factory: Factory for a configured live adapter.

    Returns:
        An honest envelope; a real 401/403 is a blocked live result.
    """
    if execution not in {"offline", "live"}:
        message = "execution must be 'offline' or 'live'."
        raise ValueError(message)
    if port is None:
        if execution == "live":
            settings = os.environ if environment is None else environment
            endpoint = settings.get("FOUNDRY_PROJECT_ENDPOINT", "").strip()
            if not endpoint:
                return missing_configuration(
                    demo=DEMO_NAME,
                    technology=TECHNOLOGY,
                    lane="current",
                    provider="microsoft-foundry",
                    missing=["FOUNDRY_PROJECT_ENDPOINT"],
                    next_steps=[
                        "Set FOUNDRY_PROJECT_ENDPOINT and an Entra identity."
                    ],
                )
            port = live_port_factory(endpoint)
        else:
            port = FixtureProjectsPort()
    try:
        rows = await port.list_deployments()
    except ImportError:
        return _envelope(
            port,
            failure=ProjectsError(
                "missing_sdk", "Install azure-ai-projects and azure-identity."
            ),
        )
    except ProjectsError as exc:
        return _envelope(port, failure=exc)
    try:
        deployments = _decode_deployments(rows)
    except ValueError:
        return _envelope(
            port,
            failure=ProjectsError(
                "malformed_response",
                "Foundry returned incomplete deployment metadata.",
                "error",
            ),
        )
    return _envelope(port, deployments=deployments)

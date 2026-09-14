from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import TYPE_CHECKING

import pytest
from azure.core.exceptions import (
    HttpResponseError,
    ServiceRequestTimeoutError,
    ServiceResponseTimeoutError,
)

from msai_demo import scenario
from msai_demo.content_safety_demo import (
    CATEGORIES,
    ENDPOINT_ENV,
    FIXTURE_ID,
    PROVIDER,
    SDK_MODULE,
    FixtureContentSafetyPort,
    LiveContentSafetyPort,
    MalformedClassificationError,
    SafetyServiceError,
    build_live_port,
    decide_content,
    decode_classification,
    run_content_safety_demo,
)
from msai_demo.contracts import Evidence, Mode, evidence

if TYPE_CHECKING:
    from collections.abc import Callable

    from msai_demo.content_safety_demo import ContentSafetyPort


def classification(severity: int = 0) -> dict[str, object]:
    return {
        "categoriesAnalysis": [
            {"category": category, "severity": severity}
            for category in CATEGORIES
        ]
    }


def sdk_classification() -> object:
    return SimpleNamespace(
        categories_analysis=[
            SimpleNamespace(category=category, severity=0)
            for category in CATEGORIES
        ]
    )


@dataclass
class FakePort:
    payload: object = field(default_factory=classification)
    failure: Exception | None = None
    texts: list[str] = field(default_factory=list)
    mode: Mode = "local_contract"
    record: Evidence = field(
        default_factory=lambda: evidence(
            provider=PROVIDER, fixture_id="content-safety-test-v1"
        )
    )

    async def classify(self, text: str) -> object:
        self.texts.append(text)
        if self.failure is not None:
            raise self.failure
        return self.payload


@dataclass
class FakeCredential:
    closed: bool = False

    async def close(self) -> None:
        self.closed = True


@dataclass
class FakeClient:
    payload: object = field(default_factory=sdk_classification)
    failure: Exception | None = None
    close_failure: Exception | None = None
    calls: list[dict[str, object]] = field(default_factory=list)
    closed: bool = False

    async def analyze_text(self, options: dict[str, object]) -> object:
        self.calls.append(options)
        if self.failure is not None:
            raise self.failure
        return self.payload

    async def close(self) -> None:
        self.closed = True
        if self.close_failure is not None:
            raise self.close_failure


def test_offline_runs_application_policy_without_approving_work() -> None:
    output = asyncio.run(run_content_safety_demo())
    assert output["mode"] == "local_contract"
    assert output["status"] == "ok"
    assert output["evidence"] == evidence(
        provider=PROVIDER, fixture_id=FIXTURE_ID
    )
    data = output["data"]
    assert data is not None
    assert data["classification"] == dict.fromkeys(CATEGORIES, 0)
    assert data["outcome"] == "allow"
    assert data["cost"] == scenario.price_pilot()
    assert not data["proposal_accepted"]
    assert data["acceptance_failures"] == ["No human approval recorded."]
    assert data["migration"]["intervention_points"] == [
        {"point": "user input", "preview": False},
        {"point": "tool call", "preview": True, "agents_only": True},
        {"point": "tool response", "preview": True, "agents_only": True},
        {"point": "output", "preview": False},
    ]
    assert "preview" in data["migration"]["scope"]
    assert "not claimed to be retired" in data["migration"]["scope"]


def test_injected_fixture_blocks_at_the_exact_threshold() -> None:
    port = FakePort(payload=classification(4))
    output = asyncio.run(run_content_safety_demo(port=port))
    assert port.texts == [scenario.BRIEF]
    assert output["status"] == "blocked"
    assert output["data"] is not None
    assert output["data"]["outcome"] == "block"
    assert output["data"]["policy"]["blocked_categories"] == list(CATEGORIES)
    assert not output["evidence"]["network_attempted"]


def test_each_category_has_its_own_explicit_threshold() -> None:
    decision = decide_content(
        {"Hate": 2, "SelfHarm": 1, "Sexual": 6, "Violence": 7},
        thresholds={"Hate": 3, "SelfHarm": 1, "Sexual": 7, "Violence": 7},
    )
    assert not decision["allowed"]
    assert decision["blocked_categories"] == ["SelfHarm", "Violence"]
    assert decide_content(dict.fromkeys(CATEGORIES, 3))["allowed"]


@pytest.mark.parametrize("threshold", [0, 8, True])
def test_policy_rejects_invalid_thresholds(threshold: int) -> None:
    with pytest.raises(ValueError, match="Thresholds"):
        decide_content(
            dict.fromkeys(CATEGORIES, 0),
            thresholds=dict.fromkeys(CATEGORIES, threshold),
        )


def test_policy_rejects_incomplete_thresholds() -> None:
    with pytest.raises(ValueError, match="Thresholds"):
        decide_content(dict.fromkeys(CATEGORIES, 0), thresholds={})


@pytest.mark.parametrize(
    "payload",
    [
        None,
        {},
        {"categoriesAnalysis": "not a list"},
        {"categoriesAnalysis": []},
        {"categoriesAnalysis": [None]},
        {"categoriesAnalysis": [{"category": None, "severity": 0}]},
        {"categoriesAnalysis": [{"category": "Unknown", "severity": 0}]},
        {
            "categoriesAnalysis": [
                {"category": "Hate", "severity": 0},
                {"category": "Hate", "severity": 0},
            ]
        },
        {"categoriesAnalysis": [{"category": "Hate", "severity": None}]},
        {"categoriesAnalysis": [{"category": "Hate", "severity": True}]},
        {"categoriesAnalysis": [{"category": "Hate", "severity": -1}]},
        {"categoriesAnalysis": [{"category": "Hate", "severity": 8}]},
    ],
)
def test_malformed_classifications_fail_closed(payload: object) -> None:
    with pytest.raises(MalformedClassificationError):
        decode_classification(payload)
    output = asyncio.run(run_content_safety_demo(port=FakePort(payload)))
    assert output["status"] == "error"
    assert output["error"] is not None
    assert output["error"]["code"] == "malformed_response"
    assert output["data"] is not None
    assert not output["data"]["content_allowed"]


def test_fixture_is_explicitly_synthetic() -> None:
    port = FixtureContentSafetyPort()
    assert asyncio.run(port.classify(scenario.BRIEF)) == classification()
    assert not port.record["sdk_invoked"]


@pytest.mark.parametrize("environment", [{}, {ENDPOINT_ENV: "  "}])
def test_missing_endpoint_stops_before_sdk_loading(
    environment: dict[str, str],
) -> None:
    def forbidden_factory(endpoint: str) -> ContentSafetyPort:
        pytest.fail(f"Unexpected client construction: {endpoint}")

    output = asyncio.run(
        run_content_safety_demo(
            execution="live",
            environment=environment,
            port_factory=forbidden_factory,
        )
    )
    assert output["mode"] == "not_run"
    assert output["error"] is not None
    assert output["error"]["code"] == "missing_configuration"
    assert ENDPOINT_ENV in output["headline"]
    assert not output["evidence"]["network_attempted"]


@pytest.mark.parametrize("name", ["azure.ai.contentsafety", SDK_MODULE])
def test_missing_optional_sdk_is_a_configuration_result(name: str) -> None:
    def missing_sdk(module_name: str) -> object:
        assert module_name == SDK_MODULE
        raise ModuleNotFoundError(name=name)

    def factory(endpoint: str) -> ContentSafetyPort:
        return build_live_port(endpoint, importer=missing_sdk)

    output = asyncio.run(
        run_content_safety_demo(
            execution="live",
            environment={ENDPOINT_ENV: "https://resource.example/"},
            port_factory=factory,
        )
    )
    assert output["mode"] == "not_run"
    assert "azure-ai-contentsafety" in output["headline"]
    assert not output["evidence"]["sdk_invoked"]


def test_unrelated_missing_dependency_is_not_hidden() -> None:
    def broken_factory(endpoint: str) -> ContentSafetyPort:
        del endpoint
        raise ModuleNotFoundError(name="unrelated_dependency")

    with pytest.raises(ModuleNotFoundError):
        asyncio.run(
            run_content_safety_demo(
                execution="live",
                environment={ENDPOINT_ENV: "https://resource.example/"},
                port_factory=broken_factory,
            )
        )


def test_live_selection_respects_injected_port_evidence() -> None:
    port = FakePort()
    endpoints: list[str] = []

    def factory(endpoint: str) -> ContentSafetyPort:
        endpoints.append(endpoint)
        return port

    output = asyncio.run(
        run_content_safety_demo(
            execution="live",
            environment={ENDPOINT_ENV: " https://resource.example/ "},
            port_factory=factory,
        )
    )
    assert endpoints == ["https://resource.example/"]
    assert output["mode"] == "local_contract"
    assert not output["evidence"]["service_executed"]


def test_sdk_factory_and_adapter_use_the_documented_json_overload() -> None:
    client = FakeClient()
    credential = FakeCredential()
    imports: list[str] = []

    def make_client(endpoint: str, supplied: FakeCredential) -> FakeClient:
        assert endpoint == "https://resource.example/"
        assert supplied is credential
        return client

    def importer(name: str) -> object:
        imports.append(name)
        return {
            SDK_MODULE: SimpleNamespace(ContentSafetyClient=make_client),
            "azure.identity.aio": SimpleNamespace(
                DefaultAzureCredential=lambda: credential
            ),
        }[name]

    port = build_live_port("https://resource.example/", importer=importer)
    assert imports == [SDK_MODULE, "azure.identity.aio"]
    assert not port.record["network_attempted"]
    assert asyncio.run(port.classify(scenario.BRIEF)) == classification()
    assert client.calls == [
        {"text": scenario.BRIEF, "outputType": "EightSeverityLevels"}
    ]
    assert client.closed and credential.closed
    assert port.record["service_executed"]


@pytest.mark.parametrize(
    ("status_code", "expected"),
    [
        (401, "authentication_failed"),
        (403, "authorization_denied"),
        (429, "throttled"),
    ],
)
def test_sdk_http_failures_are_sanitized_and_resources_closed(
    status_code: int, expected: str
) -> None:
    failure = HttpResponseError("sensitive-service-message")
    failure.status_code = status_code
    client = FakeClient(failure=failure)
    credential = FakeCredential()
    port = LiveContentSafetyPort(client, credential)
    with pytest.raises(SafetyServiceError) as caught:
        asyncio.run(port.classify(scenario.BRIEF))
    assert caught.value.code == expected
    assert "sensitive-service-message" not in caught.value.message
    assert port.record["network_attempted"]
    assert not port.record["service_executed"]
    assert client.closed and credential.closed

    # Presenting a replayed HTTP failure must not claim a live call.
    output = asyncio.run(
        run_content_safety_demo(port=FakePort(failure=caught.value))
    )
    assert output["status"] == "blocked"
    assert output["mode"] == "local_contract"
    assert output["error"] is not None
    assert output["error"]["code"] == expected
    assert not output["evidence"]["network_attempted"]


@pytest.mark.parametrize(
    "failure_factory",
    [TimeoutError, ServiceRequestTimeoutError, ServiceResponseTimeoutError],
)
def test_sdk_timeouts_are_structured(
    failure_factory: Callable[[str], Exception],
) -> None:
    client = FakeClient(failure=failure_factory("timeout"))
    credential = FakeCredential()
    with pytest.raises(SafetyServiceError) as caught:
        asyncio.run(
            LiveContentSafetyPort(client, credential).classify(scenario.BRIEF)
        )
    assert caught.value.code == "timeout"
    assert client.closed and credential.closed


def test_unexpected_http_errors_propagate() -> None:
    failure = HttpResponseError("unexpected failure")
    failure.status_code = 500
    client = FakeClient(failure=failure)
    credential = FakeCredential()
    with pytest.raises(HttpResponseError):
        asyncio.run(
            LiveContentSafetyPort(client, credential).classify(scenario.BRIEF)
        )
    assert client.closed and credential.closed


def test_credential_closes_even_if_client_cleanup_fails() -> None:
    client = FakeClient(close_failure=RuntimeError("cleanup"))
    credential = FakeCredential()
    with pytest.raises(RuntimeError, match="cleanup"):
        asyncio.run(
            LiveContentSafetyPort(client, credential).classify(scenario.BRIEF)
        )
    assert credential.closed


def test_unknown_port_errors_propagate() -> None:
    with pytest.raises(RuntimeError, match="unexpected"):
        asyncio.run(
            run_content_safety_demo(
                port=FakePort(failure=RuntimeError("unexpected"))
            )
        )


def test_invalid_execution_is_rejected() -> None:
    with pytest.raises(ValueError, match="execution"):
        asyncio.run(run_content_safety_demo(execution="typo"))


def test_injected_live_port_cannot_run_in_offline_mode() -> None:
    client = FakeClient()
    with pytest.raises(ValueError, match="requires execution='live'"):
        asyncio.run(
            run_content_safety_demo(
                port=LiveContentSafetyPort(client, FakeCredential())
            )
        )
    assert not client.calls


def test_injected_live_port_requires_explicit_execution() -> None:
    client = FakeClient()
    output = asyncio.run(
        run_content_safety_demo(
            execution="live",
            port=LiveContentSafetyPort(client, FakeCredential()),
        )
    )
    assert output["mode"] == "live_service"
    assert output["status"] == "ok"


@pytest.mark.parametrize(
    "payload", [None, SimpleNamespace(categories_analysis=[None])]
)
def test_sdk_malformed_responses_still_close_resources(
    payload: object,
) -> None:
    client = FakeClient(payload=payload)
    credential = FakeCredential()
    output = asyncio.run(
        run_content_safety_demo(
            execution="live", port=LiveContentSafetyPort(client, credential)
        )
    )
    assert output["status"] == "error"
    assert output["error"] is not None
    assert output["error"]["code"] == "malformed_response"
    assert client.closed and credential.closed

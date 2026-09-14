from __future__ import annotations

import asyncio
import base64
import json
from dataclasses import dataclass
from typing import TYPE_CHECKING

import pytest

from msai_demo.azure_identity_demo import (
    REQUIRED_ENV,
    SCOPES,
    SUBSCRIPTIONS_URL,
    AzureIdentityPort,
    HttpArmPort,
    IdentityError,
    OfflineIdentityPort,
    _live_port,
    run_azure_identity_demo,
)

if TYPE_CHECKING:
    from httpx import Request, Response

    from msai_demo.contracts import Mode


@dataclass
class FakeAccessToken:
    token: str
    expires_on: int = 1_800_000_000


def jwt(payload: object) -> str:
    encoded = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode()
    return "header." + encoded.rstrip("=") + ".secret-signature"


class FakeCredential:
    def __init__(
        self,
        *,
        token: str | None = None,
        error: Exception | None = None,
        fail_scope: str | None = None,
        expires_on: int = 1_800_000_000,
    ) -> None:
        self.token = token or jwt({"aud": "resource", "roles": ["Reader"]})
        self.error = error
        self.fail_scope = fail_scope
        self.expires_on = expires_on
        self.closed = False
        self.scopes: list[str] = []

    def get_token(self, scope: str) -> FakeAccessToken:
        self.scopes.append(scope)
        if self.error and (
            self.fail_scope is None or self.fail_scope == scope
        ):
            raise self.error
        return FakeAccessToken(self.token, self.expires_on)

    def close(self) -> None:
        self.closed = True


class FakeArm:
    def __init__(self, error: IdentityError | None = None) -> None:
        self.error = error
        self.called = False

    def subscriptions(self, bearer: str) -> list[str]:
        assert bearer
        self.called = True
        if self.error:
            raise self.error
        return []


class LocalIdentityPort(AzureIdentityPort):
    mode: Mode = "local_contract"
    fixture_id = "azure-identity-test-v1"
    network_attempted = False


def test_offline_and_configuration() -> None:
    outcome = asyncio.run(run_azure_identity_demo())
    assert outcome["mode"] == "local_contract"
    assert outcome["evidence"]["sdk_invoked"] is False
    assert outcome["data"] is not None
    assert all(row["acquired"] is None for row in outcome["data"]["tokens"])
    assert outcome["data"]["arm"]["subscriptions"] is None
    missing = asyncio.run(
        run_azure_identity_demo(execution="live", configured=lambda _: False)
    )
    assert missing["error"]["code"] == "missing_configuration"
    assert all(name in missing["headline"] for name in REQUIRED_ENV)
    partial = asyncio.run(
        run_azure_identity_demo(
            execution="live", configured=lambda name: name != REQUIRED_ENV[-1]
        )
    )
    assert REQUIRED_ENV[-1] in partial["headline"]
    with pytest.raises(ValueError, match="execution"):
        asyncio.run(run_azure_identity_demo(execution="typo"))


def test_missing_sdk_and_injected_factory() -> None:
    def unavailable() -> OfflineIdentityPort:
        message = "azure.identity unavailable"
        raise ModuleNotFoundError(message)

    outcome = asyncio.run(
        run_azure_identity_demo(
            execution="live",
            configured=lambda _: True,
            live_factory=unavailable,
        )
    )
    assert "azure-identity" in outcome["headline"]
    outcome = asyncio.run(
        run_azure_identity_demo(
            execution="live",
            configured=lambda _: True,
            live_factory=OfflineIdentityPort,
        )
    )
    assert outcome["mode"] == "local_contract"
    adapter = _live_port()
    assert isinstance(adapter, AzureIdentityPort)
    # Constructing an EnvironmentCredential does not request a token.
    adapter._credential.close()


def test_fake_credential_never_returns_token() -> None:
    credential = FakeCredential()
    arm = FakeArm()
    outcome = asyncio.run(
        run_azure_identity_demo(port=LocalIdentityPort(credential, arm))
    )
    assert credential.closed
    assert credential.scopes == list(SCOPES)
    assert arm.called
    assert outcome["status"] == "ok"
    assert outcome["data"] is not None
    assert outcome["data"]["arm"]["subscriptions"] == []
    assert outcome["data"]["arm"]["empty_list_observed"] is True
    assert outcome["data"]["is_agent_id"] is False
    for row in outcome["data"]["tokens"]:
        assert row["acquired"] is True
        assert row["aud"] == "resource"
        assert row["roles"] == ["Reader"]
        assert row["expires_at"] == "2027-01-15T08:00:00+00:00"
    rendered = json.dumps(outcome)
    assert credential.token not in rendered
    assert "secret-signature" not in rendered
    assert '"token":' not in rendered


@pytest.mark.parametrize(
    "payload",
    [[], {}, {"aud": 42}, {"aud": [42]}, {"aud": "x", "roles": [42]}],
)
def test_malformed_claims_are_safe(payload: object) -> None:
    credential = FakeCredential(token=jwt(payload))
    outcome = asyncio.run(
        run_azure_identity_demo(port=LocalIdentityPort(credential, FakeArm()))
    )
    assert outcome["error"]["code"] == "malformed_response"
    assert outcome["data"]["tokens"][0]["acquired"] is True
    assert credential.token not in json.dumps(outcome)


@pytest.mark.parametrize("token", ["opaque", "x.@@@.z", "x._w.z"])
def test_opaque_or_invalid_jwt(token: str) -> None:
    outcome = asyncio.run(
        run_azure_identity_demo(
            port=LocalIdentityPort(FakeCredential(token=token), FakeArm())
        )
    )
    assert outcome["error"]["code"] == "malformed_response"


def test_audience_list_missing_roles_and_invalid_expiry() -> None:
    credential = FakeCredential(token=jwt({"aud": ["resource"]}))
    outcome = asyncio.run(
        run_azure_identity_demo(port=LocalIdentityPort(credential, FakeArm()))
    )
    assert outcome["data"]["tokens"][0]["aud"] == ["resource"]
    assert outcome["data"]["tokens"][0]["roles"] is None
    credential = FakeCredential(expires_on=10**100)
    outcome = asyncio.run(
        run_azure_identity_demo(port=LocalIdentityPort(credential, FakeArm()))
    )
    assert outcome["error"]["code"] == "malformed_response"


def test_known_sdk_failures_are_redacted_and_close_credential() -> None:
    from azure.core.exceptions import (
        ClientAuthenticationError,
        HttpResponseError,
        ServiceRequestError,
        ServiceResponseError,
    )

    errors = [
        ClientAuthenticationError("secret-signature"),
        ServiceRequestError("secret-signature"),
        ServiceResponseError("secret-signature"),
        HttpResponseError("secret-signature"),
    ]
    for error in errors:
        credential = FakeCredential(error=error)
        arm = FakeArm()
        outcome = asyncio.run(
            run_azure_identity_demo(port=LocalIdentityPort(credential, arm))
        )
        assert outcome["status"] == "blocked"
        assert not arm.called
        assert credential.closed
        assert "secret-signature" not in json.dumps(outcome)
    http_error = HttpResponseError("secret-signature")
    http_error.status_code = 429
    outcome = asyncio.run(
        run_azure_identity_demo(
            port=LocalIdentityPort(FakeCredential(error=http_error), FakeArm())
        )
    )
    assert outcome["error"]["code"] == "throttled"


def test_live_evidence_logic_without_network() -> None:
    # Exercise live result routing without the production transport.
    credential = FakeCredential()
    outcome = asyncio.run(
        run_azure_identity_demo(port=AzureIdentityPort(credential, FakeArm()))
    )
    assert outcome["mode"] == "live_identity"
    assert outcome["evidence"]["service_executed"] is True
    error = IdentityError("authentication_failed", "Denied.")
    outcome = asyncio.run(
        run_azure_identity_demo(
            port=AzureIdentityPort(FakeCredential(error=error), FakeArm())
        )
    )
    assert outcome["mode"] == "live_service"
    assert outcome["evidence"]["service_executed"] is False


def test_partial_token_failure_and_arm_denial() -> None:
    from azure.core.exceptions import ClientAuthenticationError

    credential = FakeCredential(
        error=ClientAuthenticationError("redacted"), fail_scope=SCOPES[0]
    )
    arm = FakeArm(IdentityError("authorization_denied", "ARM denied access."))
    outcome = asyncio.run(
        run_azure_identity_demo(port=LocalIdentityPort(credential, arm))
    )
    assert outcome["data"]["tokens"][0]["acquired"] is False
    assert outcome["data"]["tokens"][1]["acquired"] is True
    assert outcome["data"]["arm"]["error"]["code"] == "authorization_denied"
    assert outcome["data"]["arm"]["subscriptions"] is None


def test_unknown_failure_propagates_and_closes() -> None:
    credential = FakeCredential(error=RuntimeError("programming failure"))
    with pytest.raises(RuntimeError, match="programming"):
        asyncio.run(
            run_azure_identity_demo(
                port=LocalIdentityPort(credential, FakeArm())
            )
        )
    assert credential.closed


def test_arm_empty_and_pagination() -> None:
    import httpx

    urls: list[str] = []

    def handler(request: Request) -> Response:
        assert request.headers["authorization"] == "Bearer private-value"
        urls.append(str(request.url))
        if len(urls) == 1:
            return httpx.Response(
                200,
                json={
                    "value": [{"subscriptionId": "visible-subscription"}],
                    "nextLink": SUBSCRIPTIONS_URL + "&page=2",
                },
            )
        return httpx.Response(200, json={"value": []})

    arm = HttpArmPort(transport=httpx.MockTransport(handler))
    assert arm.subscriptions("private-value") == ["visible-subscription"]
    assert len(urls) == 2


@pytest.mark.parametrize("status", [401, 403, 429, 500])
def test_arm_http_status(status: int) -> None:
    import httpx

    def handler(request: Request) -> Response:
        del request
        return httpx.Response(status, text="private-value")

    with pytest.raises(IdentityError) as caught:
        HttpArmPort(transport=httpx.MockTransport(handler)).subscriptions(
            "private-value"
        )
    assert str(status) in str(caught.value)
    assert "private-value" not in str(caught.value)


@pytest.mark.parametrize(
    "payload",
    [
        [],
        {},
        {"value": [False]},
        {"value": [{}]},
        {"value": [], "nextLink": None},
        {"value": [], "nextLink": "http://management.azure.com/subscriptions"},
        {"value": [], "nextLink": "https://evil.example/subscriptions"},
        {"value": [], "nextLink": "https://management.azure.com/other"},
        {"value": [], "nextLink": SUBSCRIPTIONS_URL},
    ],
)
def test_arm_malformed_responses(payload: object) -> None:
    import httpx

    def handler(request: Request) -> Response:
        del request
        return httpx.Response(200, json=payload)

    with pytest.raises(IdentityError, match=r"ARM|Expected"):
        HttpArmPort(transport=httpx.MockTransport(handler)).subscriptions("x")


def test_arm_invalid_json_timeout_and_connection_failure() -> None:
    import httpx

    def malformed(request: Request) -> Response:
        del request
        return httpx.Response(200, text="not-json")

    with pytest.raises(IdentityError, match="invalid JSON"):
        HttpArmPort(transport=httpx.MockTransport(malformed)).subscriptions(
            "x"
        )

    for error in (httpx.ReadTimeout("private"), httpx.ConnectError("private")):

        def handler(request: Request, failure: Exception = error) -> Response:
            del request
            raise failure

        with pytest.raises(IdentityError, match="ARM"):
            HttpArmPort(transport=httpx.MockTransport(handler)).subscriptions(
                "x"
            )

"""Azure Identity: authenticate an ordinary workload with Entra.

This current SDK acquires resource-specific tokens. ARM separately
reports which subscriptions the principal can see. Authentication is
not a role assignment, and this app registration is not an Agent ID.
The default path explains the flow without requesting any token.

Run it:

    uv run msai-demo azure-identity
    uv run msai-demo azure-identity --execution live
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Protocol, TypedDict, cast
from urllib.parse import urlsplit

from msai_demo import scenario
from msai_demo.contracts import (
    DemoError,
    DemoResult,
    Mode,
    evidence,
    missing_configuration,
    result,
)
from msai_demo.runtime import env_is_present

if TYPE_CHECKING:
    from collections.abc import Callable

    from httpx import BaseTransport

DEMO_NAME = "azure-identity"
TECHNOLOGY = "Microsoft Entra workload identity / azure-identity"
REQUIRED_ENV = ("AZURE_TENANT_ID", "AZURE_CLIENT_ID", "AZURE_CLIENT_SECRET")
SCOPES = (
    "https://ai.azure.com/.default",
    "https://cognitiveservices.azure.com/.default",
    "https://search.azure.com/.default",
    "https://management.azure.com/.default",
)
SUBSCRIPTIONS_URL = (
    "https://management.azure.com/subscriptions?api-version=2022-12-01"
)


class AccessTokenPort(Protocol):
    """The two SDK token properties used inside the adapter."""

    @property
    def token(self) -> str:
        """Return the bearer credential, never for display."""

    @property
    def expires_on(self) -> int:
        """Return the SDK expiry as Unix seconds."""


class CredentialPort(Protocol):
    """Acquire audience tokens and release the credential transport."""

    def get_token(self, scope: str) -> AccessTokenPort:
        """Acquire a token for a single resource scope."""

    def close(self) -> None:
        """Close owned HTTP resources."""


class TokenReport(TypedDict):
    """Allowlisted display fields; no bearer token is retained."""

    scope: str
    acquired: bool | None
    aud: str | list[str] | None
    expires_at: str | None
    roles: list[str] | None
    error: DemoError | None


@dataclass(frozen=True)
class IdentitySnapshot:
    """Safe outcomes from the identity and ARM calls."""

    tokens: list[TokenReport]
    subscriptions: list[str] | None
    arm_error: DemoError | None = None
    service_executed: bool = False


class IdentityPort(Protocol):
    """Return identity evidence without exposing credentials."""

    mode: Mode
    fixture_id: str | None
    sdk_invoked: bool
    network_attempted: bool

    async def inspect(self) -> IdentitySnapshot:
        """Inspect all four audiences and subscription visibility."""


class ArmPort(Protocol):
    """The one resource authorization probe this demo makes."""

    def subscriptions(self, bearer: str) -> list[str]:
        """List subscription IDs using an internal ARM bearer token."""


class IdentityError(Exception):
    """A known failure with a message that cannot contain a token."""

    def __init__(self, code: str, message: str) -> None:
        """Keep only a caller-selected safe error message."""
        super().__init__(message)
        self.error: DemoError = {"code": code, "message": message}


def _http_failure(status_code: int) -> IdentityError:
    codes = {
        401: "authentication_failed",
        403: "authorization_denied",
        429: "throttled",
    }
    return IdentityError(
        codes.get(status_code, "http_error"),
        f"The identity or ARM endpoint returned HTTP {status_code}.",
    )


def _object(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        failure = IdentityError(
            "malformed_response", "Expected a JSON object."
        )
        raise failure
    return cast("dict[str, object]", value)


def _strings(value: object) -> list[str]:
    if not isinstance(value, list):
        failure = IdentityError(
            "malformed_response", "Expected a string list."
        )
        raise failure
    values = cast("list[object]", value)
    if not all(isinstance(item, str) for item in values):
        failure = IdentityError("malformed_response", "Expected string items.")
        raise failure
    return cast("list[str]", values)


def _jwt_payload(token: str) -> dict[str, object]:
    parts = token.split(".")
    if len(parts) != 3:
        failure = IdentityError(
            "malformed_response", "Expected a three-part JWT."
        )
        raise failure
    payload = parts[1] + "=" * (-len(parts[1]) % 4)
    return _object(json.loads(base64.urlsafe_b64decode(payload)))


def _claims(access: AccessTokenPort, scope: str) -> TokenReport:
    # Decode WITHOUT verifying: display only, never authorization logic.
    # The resource validates the real token; this view cannot do that.
    try:
        claims = _jwt_payload(access.token)
        audience = claims.get("aud")
        if not isinstance(audience, str):
            audience = _strings(audience)
        roles = claims.get("roles")
        role_names = None if roles is None else _strings(roles)
        expires_at = datetime.fromtimestamp(access.expires_on, UTC).isoformat()
    except (
        ValueError,
        binascii.Error,
        UnicodeError,
        OverflowError,
        OSError,
        IdentityError,
    ):
        return _token_report(
            scope,
            acquired=True,
            error={
                "code": "malformed_response",
                "message": "Token acquired; display claims could not decode.",
            },
        )
    return {
        "scope": scope,
        "acquired": True,
        "aud": audience,
        "expires_at": expires_at,
        "roles": role_names,
        "error": None,
    }


def _token_report(
    scope: str,
    *,
    acquired: bool | None,
    error: DemoError | None = None,
) -> TokenReport:
    return {
        "scope": scope,
        "acquired": acquired,
        "aud": None,
        "expires_at": None,
        "roles": None,
        "error": error,
    }


class HttpArmPort:
    """Read ARM subscriptions with bounded, nonredirecting requests.

    Args:
        transport: Optional HTTP transport for deterministic tests.
    """

    def __init__(self, *, transport: BaseTransport | None = None) -> None:
        """Save the transport without constructing a network client."""
        self._transport = transport

    def subscriptions(self, bearer: str) -> list[str]:
        """Read all pages and expose only subscription IDs.

        Continuation URLs must stay on ARM before receiving a bearer.
        Unknown response bodies and HTTP exception strings never leave
        this adapter because they can contain request credentials.
        """
        import httpx

        subscription_ids: list[str] = []
        seen: set[str] = set()
        url = SUBSCRIPTIONS_URL
        with httpx.Client(
            transport=self._transport, timeout=20, follow_redirects=False
        ) as client:
            while url:
                parsed = urlsplit(url)
                if (
                    parsed.scheme != "https"
                    or parsed.netloc != "management.azure.com"
                    or parsed.path != "/subscriptions"
                    or url in seen
                ):
                    failure = IdentityError(
                        "malformed_response", "Unsafe ARM continuation URL."
                    )
                    raise failure
                seen.add(url)
                try:
                    response = client.get(
                        url, headers={"Authorization": f"Bearer {bearer}"}
                    )
                except httpx.TimeoutException:
                    failure = IdentityError(
                        "timeout", "The ARM request timed out."
                    )
                    raise failure from None
                except httpx.TransportError:
                    failure = IdentityError(
                        "connection_failed", "The ARM transport failed."
                    )
                    raise failure from None
                if response.status_code != 200:
                    raise _http_failure(response.status_code)
                try:
                    page = _object(response.json())
                except ValueError:
                    failure = IdentityError(
                        "malformed_response", "ARM returned invalid JSON."
                    )
                    raise failure from None
                entries = page.get("value")
                if not isinstance(entries, list):
                    failure = IdentityError(
                        "malformed_response", "ARM omitted the value list."
                    )
                    raise failure
                for item in cast("list[object]", entries):
                    subscription_id = _object(item).get("subscriptionId")
                    if not isinstance(subscription_id, str):
                        failure = IdentityError(
                            "malformed_response",
                            "ARM omitted a subscription ID.",
                        )
                        raise failure
                    subscription_ids.append(subscription_id)
                next_link = page.get("nextLink", "")
                if not isinstance(next_link, str):
                    failure = IdentityError(
                        "malformed_response",
                        "ARM returned an invalid nextLink.",
                    )
                    raise failure
                url = next_link
        return subscription_ids


class AzureIdentityPort:
    """Acquire real tokens and probe ARM using injected dependencies.

    Args:
        credential: Owned credential; closed after the inspection.
        arm: Subscription transport; the bearer stays in this adapter.
    """

    mode: Mode = "live_identity"
    fixture_id: str | None = None
    sdk_invoked = True
    network_attempted = True

    def __init__(self, credential: CredentialPort, arm: ArmPort) -> None:
        """Retain narrow ports instead of depending on SDK internals."""
        self._credential = credential
        self._arm = arm

    async def inspect(self) -> IdentitySnapshot:
        """Keep synchronous Azure Identity I/O off the event loop."""
        return await asyncio.to_thread(self._inspect)

    def _inspect(self) -> IdentitySnapshot:
        reports: list[TokenReport] = []
        arm_access: AccessTokenPort | None = None
        subscriptions: list[str] | None = None
        arm_error: DemoError | None = None
        try:
            for scope in SCOPES:
                try:
                    access = self._acquire(scope)
                except IdentityError as exc:
                    reports.append(
                        _token_report(scope, acquired=False, error=exc.error)
                    )
                    continue
                reports.append(_claims(access, scope))
                if scope == SCOPES[-1]:
                    arm_access = access
            if arm_access is not None:
                try:
                    subscriptions = self._arm.subscriptions(arm_access.token)
                except IdentityError as exc:
                    arm_error = exc.error
        finally:
            self._credential.close()
        return IdentitySnapshot(
            reports,
            subscriptions,
            arm_error,
            service_executed=self.network_attempted
            and any(row["acquired"] for row in reports),
        )

    def _acquire(self, scope: str) -> AccessTokenPort:
        from azure.core.exceptions import (
            ClientAuthenticationError,
            HttpResponseError,
            ServiceRequestError,
            ServiceResponseError,
        )

        try:
            return self._credential.get_token(scope)
        except ClientAuthenticationError:
            failure = IdentityError(
                "authentication_failed", "Entra could not issue this token."
            )
            raise failure from None
        except (ServiceRequestError, ServiceResponseError):
            failure = IdentityError(
                "connection_failed", "The Entra transport failed."
            )
            raise failure from None
        except HttpResponseError as exc:
            raise _http_failure(exc.status_code or 500) from None


class OfflineIdentityPort:
    """Explain the identity contract without fabricating a token."""

    mode: Mode = "local_contract"
    fixture_id = "azure-identity-flow-v1"
    sdk_invoked = False
    network_attempted = False

    async def inspect(self) -> IdentitySnapshot:
        """Represent every audience as unrequested, not acquired."""
        return IdentitySnapshot(
            [_token_report(scope, acquired=None) for scope in SCOPES], None
        )


def _live_port() -> IdentityPort:
    from azure.identity import EnvironmentCredential

    return AzureIdentityPort(EnvironmentCredential(), HttpArmPort())


async def run_azure_identity_demo(
    *,
    execution: str = "offline",
    port: IdentityPort | None = None,
    configured: Callable[[str], bool] = env_is_present,
    live_factory: Callable[[], IdentityPort] = _live_port,
) -> DemoResult:
    """Separate authentication from subscription authorization.

    Args:
        execution: ``offline`` explains; ``live`` requests tokens.
        port: Injected adapter, used instead of constructing one.
        configured: Non-secret configuration presence check.
        live_factory: Lazy SDK constructor and missing-SDK test seam.

    Returns:
        Token claim summaries and observed subscription visibility.

    Raises:
        ValueError: If execution is neither offline nor live.
    """
    if execution not in {"offline", "live"}:
        message = "execution must be offline or live."
        raise ValueError(message)
    if port is None and execution == "live":
        missing = [name for name in REQUIRED_ENV if not configured(name)]
        if missing:
            return _missing(missing)
        try:
            port = live_factory()
        except ImportError:
            return _missing(["azure-identity"])
    selected = port or OfflineIdentityPort()
    snapshot = await selected.inspect()
    errors = [row["error"] for row in snapshot.tokens if row["error"]]
    if snapshot.arm_error:
        errors.append(snapshot.arm_error)
    first_error = errors[0] if errors else None
    has_identity = any(row["acquired"] for row in snapshot.tokens)
    mode = selected.mode
    if mode == "live_identity" and not has_identity:
        # A failed authentication request did not acquire an identity.
        mode = "live_service"
    return result(
        demo=DEMO_NAME,
        technology=TECHNOLOGY,
        lane="shared",
        mode=mode,
        status="blocked" if first_error else "ok",
        headline=(
            "Authentication and resource authorization are separate checks."
        ),
        evidence=evidence(
            provider="microsoft-entra",
            sdk_invoked=selected.sdk_invoked,
            network_attempted=selected.network_attempted,
            service_executed=snapshot.service_executed,
            fixture_id=selected.fixture_id,
        ),
        error=first_error,
        data={
            "scenario": scenario.BRIEF,
            "cost": scenario.price_pilot(),
            "credential": "EnvironmentCredential",
            "configuration_names": list(REQUIRED_ENV),
            "principal_kind": "ordinary application service principal",
            "is_agent_id": False,
            "tokens": snapshot.tokens,
            "claims_verification": (
                "Decoded without verification; display only."
            ),
            "arm": {
                "method": "GET",
                "url": SUBSCRIPTIONS_URL,
                "subscriptions": snapshot.subscriptions,
                "empty_list_observed": snapshot.subscriptions == [],
                "error": snapshot.arm_error,
            },
            "lesson": (
                "A token proves authentication. Azure RBAC decides resource "
                "access. An empty ARM list means no subscriptions visible "
                "to this principal; it does not list all role assignments. "
                "JWT roles are app roles, not an inventory of Azure RBAC "
                "roles."
            ),
            "offline": (
                "Offline requests no tokens; acquired=null means unrequested. "
                "Use --execution live to observe the real subscription list."
            ),
        },
        next_steps=[
            "Provision pilot resources and assign the required scoped roles.",
            "Record named human approval before accepting the pilot.",
        ],
    )


def _missing(names: list[str]) -> DemoResult:
    return missing_configuration(
        demo=DEMO_NAME,
        technology=TECHNOLOGY,
        lane="shared",
        provider="microsoft-entra",
        missing=names,
        next_steps=[
            f"Configure {name} before using --execution live."
            for name in names
        ],
    )

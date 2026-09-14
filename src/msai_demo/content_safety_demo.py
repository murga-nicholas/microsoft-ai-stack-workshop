"""Legacy Content Safety classification and Foundry guardrails.

The application decides what to block after classifying one prompt.
This older SDK path leaves every intervention point to application
code. Microsoft Foundry guardrails apply controls at user input, tool
call, tool response and output; the two tool points are preview.

Offline classification is explicitly synthetic. The severity policy
and the business acceptance check both execute as ordinary Python.
An allowed prompt never substitutes for a human approving the pilot.

Run it:

    uv run msai-demo content-safety
    uv run msai-demo content-safety --execution live
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from importlib import import_module
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
    from collections.abc import Callable

DEMO_NAME = "content-safety"
TECHNOLOGY = "Azure AI Content Safety SDK 1.0.0"
PROVIDER = "azure-ai-content-safety"
SDK_MODULE = "azure.ai.contentsafety.aio"
ENDPOINT_ENV = "AZURE_CONTENT_SAFETY_ENDPOINT"
FIXTURE_ID = "content-safety-v1"
CATEGORIES = ("Hate", "SelfHarm", "Sexual", "Violence")
GUARDRAILS_SOURCE = (
    "https://learn.microsoft.com/en-us/azure/foundry/guardrails/"
    "guardrails-overview"
)

# Illustrative application policy, not a claim about Azure defaults.
# Scores at or above each threshold block, including the boundary.
SEVERITY_THRESHOLDS = dict.fromkeys(CATEGORIES, 4)


class SafetyDecision(TypedDict):
    """The application's decision after validating all categories.

    Attributes:
        allowed: Whether every score is below its threshold.
        blocked_categories: Categories meeting their block threshold.
        thresholds: The explicit policy used for this decision.
    """

    allowed: bool
    blocked_categories: list[str]
    thresholds: dict[str, int]


class MalformedClassificationError(ValueError):
    """An incomplete or invalid classification cannot permit content."""


@dataclass
class SafetyServiceError(Exception):
    """A known service failure without credential-bearing messages.

    Attributes:
        code: Stable failure code used by the result envelope.
        message: Fixed, actionable explanation safe for the console.
    """

    code: str
    message: str


class ContentSafetyPort(Protocol):
    """The external classifier and its execution evidence."""

    mode: Mode
    record: Evidence

    async def classify(self, text: str) -> object:
        """Return an untrusted classification payload."""


class FixtureContentSafetyPort:
    """Return a named synthetic classification of the pilot brief."""

    mode: Mode = "local_contract"

    def __init__(self) -> None:
        """Record that neither the SDK nor a service has executed."""
        self.record = evidence(provider=PROVIDER, fixture_id=FIXTURE_ID)

    async def classify(self, text: str) -> object:
        """Supply synthetic scores; this method is not a classifier."""
        del text
        return {
            "categoriesAnalysis": [
                {"category": category, "severity": 0}
                for category in CATEGORIES
            ]
        }


class _AsyncCredential(Protocol):
    async def close(self) -> None:
        """Close the credential's owned HTTP session."""


class _SafetyClient(Protocol):
    async def analyze_text(self, options: dict[str, object]) -> object:
        """Call the documented JSON overload of the text analyzer."""

    async def close(self) -> None:
        """Close the client's owned HTTP session."""


class _SafetyModule(Protocol):
    ContentSafetyClient: Callable[[str, _AsyncCredential], _SafetyClient]


class _IdentityModule(Protocol):
    DefaultAzureCredential: Callable[[], _AsyncCredential]


class LiveContentSafetyPort:
    """Call the optional asynchronous SDK once, closing its resources.

    Args:
        client: ContentSafetyClient or an injected SDK boundary.
        credential: Credential owned by this single-call adapter.
    """

    mode: Mode = "live_service"

    def __init__(
        self, client: _SafetyClient, credential: _AsyncCredential
    ) -> None:
        """Keep construction separate from the first network attempt."""
        self._client = client
        self._credential = credential
        self.record = evidence(provider=PROVIDER, sdk_invoked=True)

    async def classify(self, text: str) -> object:
        """Use the JSON overload and preserve known failures."""
        from azure.core.exceptions import (
            HttpResponseError,
            ServiceRequestTimeoutError,
            ServiceResponseTimeoutError,
        )

        self.record["network_attempted"] = True
        try:
            response = await self._client.analyze_text(
                {"text": text, "outputType": "EightSeverityLevels"}
            )
        except HttpResponseError as error:
            failures = {
                401: (
                    "authentication_failed",
                    "Microsoft Entra authentication was rejected.",
                ),
                403: (
                    "authorization_denied",
                    "Assign Cognitive Services User on the resource.",
                ),
                429: (
                    "throttled",
                    "Content Safety throttled the request; retry later.",
                ),
            }
            if error.status_code not in failures:
                raise
            code, message = failures[error.status_code]
            raise SafetyServiceError(code, message) from None
        except (
            TimeoutError,
            ServiceRequestTimeoutError,
            ServiceResponseTimeoutError,
        ):
            code = "timeout"
            message = "Content Safety did not answer before timeout."
            raise SafetyServiceError(code, message) from None
        else:
            self.record["service_executed"] = True
            return _sdk_payload(response)
        finally:
            try:
                await self._client.close()
            finally:
                await self._credential.close()


def build_live_port(
    endpoint: str,
    *,
    importer: Callable[[str], object] = import_module,
) -> ContentSafetyPort:
    """Import the optional SDK and build its Microsoft Entra client.

    Args:
        endpoint: Configured Content Safety resource endpoint.
        importer: Module loader seam for credential-free adapter tests.

    Returns:
        An adapter whose first network attempt is ``classify``.

    Raises:
        ModuleNotFoundError: If the optional SDK is not installed.
    """
    # The SDK accepts a JSON mapping. Read the documented model
    # attributes at the boundary so application policy uses plain data.
    sdk = cast("_SafetyModule", importer(SDK_MODULE))
    identity = cast("_IdentityModule", importer("azure.identity.aio"))
    credential = identity.DefaultAzureCredential()
    return LiveContentSafetyPort(
        sdk.ContentSafetyClient(endpoint, credential), credential
    )


def _sdk_payload(response: object) -> dict[str, object]:
    """Convert documented SDK model attributes into untrusted JSON."""
    rows: object = getattr(response, "categories_analysis", None)
    if not isinstance(rows, list):
        message = "SDK classification must contain category analysis rows."
        raise MalformedClassificationError(message)
    return {
        "categoriesAnalysis": [
            {
                "category": getattr(row, "category", None),
                "severity": getattr(row, "severity", None),
            }
            for row in cast("list[object]", rows)
        ]
    }


def decode_classification(payload: object) -> dict[str, int]:
    """Validate the service mapping before applying application policy.

    Args:
        payload: Untrusted JSON or mapping-compatible SDK response.

    Returns:
        One integer severity on the 0-7 scale for every category.

    Raises:
        MalformedClassificationError: If a score is missing or invalid.
    """
    message = "Classification must contain all four categories once."
    if not isinstance(payload, Mapping):
        raise MalformedClassificationError(message)
    response = cast("Mapping[str, object]", payload)
    rows = response.get("categoriesAnalysis")
    if not isinstance(rows, list):
        raise MalformedClassificationError(message)
    scores: dict[str, int] = {}
    for raw_row in cast("list[object]", rows):
        if not isinstance(raw_row, Mapping):
            raise MalformedClassificationError(message)
        row = cast("Mapping[str, object]", raw_row)
        category = row.get("category")
        severity = row.get("severity")
        if not isinstance(category, str) or category not in CATEGORIES:
            raise MalformedClassificationError(message)
        if category in scores:
            raise MalformedClassificationError(message)
        if type(severity) is not int or not 0 <= severity <= 7:
            message = "Category severity must be an integer from 0 to 7."
            raise MalformedClassificationError(message)
        scores[category] = severity
    if set(scores) != set(CATEGORIES):
        raise MalformedClassificationError(message)
    return scores


def decide_content(
    scores: Mapping[str, int],
    *,
    thresholds: Mapping[str, int] | None = None,
) -> SafetyDecision:
    """Block a prompt when any score meets its category threshold.

    Args:
        scores: Complete classifier scores on the 0-7 scale.
        thresholds: Explicit category thresholds on the 1-7 scale.
            Defaults to illustrative medium-or-higher blocking at 4.

    Returns:
        The allow/block decision and the policy that produced it.

    Raises:
        ValueError: If the configured policy is incomplete or invalid.
        MalformedClassificationError: If classifier scores are invalid.
    """
    policy = dict(SEVERITY_THRESHOLDS if thresholds is None else thresholds)
    if set(policy) != set(CATEGORIES) or any(
        type(value) is not int or not 1 <= value <= 7
        for value in policy.values()
    ):
        message = "Thresholds must cover all four categories with 1-7."
        raise ValueError(message)
    validated = decode_classification(
        {
            "categoriesAnalysis": [
                {"category": category, "severity": severity}
                for category, severity in scores.items()
            ]
        }
    )
    blocked = [
        category
        for category in CATEGORIES
        if validated[category] >= policy[category]
    ]
    return {
        "allowed": not blocked,
        "blocked_categories": blocked,
        "thresholds": policy,
    }


def _migration() -> dict[str, object]:
    """Keep policy ownership and preview scope visible in the output."""
    return {
        "legacy": "Classify one prompt yourself, then enforce a policy.",
        "replacement": "Microsoft Foundry guardrails",
        "why": "Apply configured controls throughout model and agent runs.",
        "intervention_points": [
            {"point": "user input", "preview": False},
            {"point": "tool call", "preview": True, "agents_only": True},
            {
                "point": "tool response",
                "preview": True,
                "agents_only": True,
            },
            {"point": "output", "preview": False},
        ],
        "scope": (
            "Learn also marks agent applicability as preview. Guardrails "
            "reuse Azure AI Content Safety classifiers; the service is "
            "not claimed to be retired."
        ),
        "source": GUARDRAILS_SOURCE,
    }


async def run_content_safety_demo(
    *,
    execution: str = "offline",
    port: ContentSafetyPort | None = None,
    environment: Mapping[str, str] = os.environ,
    port_factory: Callable[[str], ContentSafetyPort] = build_live_port,
) -> DemoResult:
    """Classify one scenario prompt and execute its application policy.

    Args:
        execution: ``offline`` for the fixture or ``live`` for Azure.
        port: Injected classifier; its evidence describes what ran.
        environment: Configuration seam, defaulting to the process.
        port_factory: Constructor seam for the optional live adapter.

    Returns:
        An honest result including classification and policy outcome.

    Raises:
        ValueError: If execution is neither ``offline`` nor ``live``.
    """
    if execution not in {"offline", "live"}:
        message = "execution must be 'offline' or 'live'."
        raise ValueError(message)
    if (
        port is not None
        and port.mode == "live_service"
        and execution != "live"
    ):
        message = "A live Content Safety port requires execution='live'."
        raise ValueError(message)
    if port is None:
        if execution == "offline":
            port = FixtureContentSafetyPort()
        else:
            endpoint = environment.get(ENDPOINT_ENV, "").strip()
            if not endpoint:
                return _missing(ENDPOINT_ENV)
            try:
                port = port_factory(endpoint)
            except ModuleNotFoundError as error:
                if error.name not in {"azure.ai.contentsafety", SDK_MODULE}:
                    raise
                return _missing("azure-ai-contentsafety")

    try:
        scores = decode_classification(await port.classify(scenario.BRIEF))
        decision = decide_content(scores)
    except (SafetyServiceError, MalformedClassificationError) as error:
        malformed = isinstance(error, MalformedClassificationError)
        if isinstance(error, MalformedClassificationError):
            error_code = "malformed_response"
            error_message = str(error)
        else:
            error_code = error.code
            error_message = error.message
        return result(
            demo=DEMO_NAME,
            technology=TECHNOLOGY,
            lane="legacy",
            mode=port.mode,
            status="error" if malformed else "blocked",
            headline="Content Safety could not produce an allow decision.",
            evidence=port.record,
            error={
                "code": error_code,
                "message": error_message,
            },
            data={"migration": _migration(), "content_allowed": False},
        )

    cost = scenario.price_pilot()
    accepted, failures = scenario.proposal_is_acceptable(
        cost=cost, approved=False, cited_sources=["workshop-scenario"]
    )
    return result(
        demo=DEMO_NAME,
        technology=TECHNOLOGY,
        lane="legacy",
        mode=port.mode,
        status="ok" if decision["allowed"] else "blocked",
        headline=(
            "Application policy allows the prompt; human approval remains."
            if decision["allowed"]
            else "Application policy blocks the classified prompt."
        ),
        evidence=port.record,
        data={
            "scenario_id": scenario.SCENARIO_ID,
            "prompt": scenario.BRIEF,
            "classification": scores,
            "policy": decision,
            "policy_basis": "Illustrative workshop thresholds, not defaults.",
            "outcome": "allow" if decision["allowed"] else "block",
            "cost": cost,
            "proposal_accepted": accepted,
            "acceptance_failures": failures,
            "last_sdk_release": "2023-12-12",
            "migration": _migration(),
        },
    )


def _missing(name: str) -> DemoResult:
    """Explain prerequisites without attempting a service call."""
    return missing_configuration(
        demo=DEMO_NAME,
        technology=TECHNOLOGY,
        lane="legacy",
        provider=PROVIDER,
        missing=[name],
        next_steps=[
            "Set AZURE_CONTENT_SAFETY_ENDPOINT to the resource endpoint.",
            "Install azure-ai-contentsafety==1.0.0 for this legacy path.",
            "Configure Microsoft Entra and Cognitive Services User access.",
        ],
    )

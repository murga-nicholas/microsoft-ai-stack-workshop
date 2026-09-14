"""Azure AI Inference: a legacy request beside the OpenAI v1 surface.

The 1.0.0b9 beta last shipped on 2025-02-15. Foundry clients and the
OpenAI v1 surface are the current path. This module validates the old
wire contract and decodes an explicitly synthetic response. No SDK,
credential or network connection is needed, even if the SDK exists.

Run it:

    uv run msai-demo azure-ai-inference
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, Protocol, TypedDict
from urllib.parse import parse_qs, urlsplit

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from msai_demo import scenario
from msai_demo.contracts import (
    DemoResult,
    evidence,
    missing_configuration,
    result,
)

if TYPE_CHECKING:
    from msai_demo.contracts import DemoError, Status

DEMO_NAME = "azure-ai-inference"
TECHNOLOGY = "Azure AI Inference (azure-ai-inference 1.0.0b9)"
FIXTURE_ID = "azure-ai-inference-v1"
API_VERSION = "2024-05-01-preview"
RESOURCE = "https://workshop-example.services.ai.azure.com"
MODEL = "workshop-deployment"

# Verified in 1.0.0b9: _operations.py builds the route and query;
# _patch.py adds api-key alongside the Bearer key credential policy.
SDK_SOURCE = (
    "https://github.com/Azure/azure-sdk-for-python/tree/"
    "azure-ai-inference_1.0.0b9/sdk/ai/azure-ai-inference"
)
CURRENT_REFERENCE = (
    "https://learn.microsoft.com/en-us/rest/api/"
    "microsoft-foundry/azureopenai/chat"
)


class InferenceRequest(TypedDict):
    """A redacted HTTP contract passed to the local response port.

    Attributes:
        method: HTTP method in the legacy operation.
        url: Example resource, operation path and version query.
        headers: Header names with placeholders instead of secrets.
        body: Serialized JSON sent by ``complete(messages=...)``.
    """

    method: str
    url: str
    headers: dict[str, str]
    body: str


@dataclass(frozen=True)
class FixtureReply:
    """Synthetic HTTP status and JSON, never a live service response.

    Attributes:
        status_code: HTTP status being replayed locally.
        body: Synthetic response JSON to validate and decode.
    """

    status_code: int
    body: str


class InferencePort(Protocol):
    """Supply one fixture response without sending the request."""

    async def replay(self, request: InferenceRequest) -> FixtureReply:
        """Read a local fixture for the supplied request contract."""


class FixtureInferencePort:
    """Replay a synthetic completion with real scenario arithmetic."""

    async def replay(self, request: InferenceRequest) -> FixtureReply:
        """Return a completion, with unknown token usage left absent."""
        del request
        cost = scenario.price_pilot()
        return FixtureReply(
            status_code=200,
            body=json.dumps(
                {
                    "id": "synthetic-support-pilot-completion",
                    "model": MODEL,
                    # Fixture timestamp: 2025-02-15 at midnight UTC.
                    "created": 1739577600,
                    "choices": [
                        {
                            "index": 0,
                            "finish_reason": "stop",
                            "message": {
                                "role": "assistant",
                                "content": (
                                    f"Pilot total: {cost['total']} USD. "
                                    "Human approval is still required."
                                ),
                            },
                        }
                    ],
                }
            ),
        )


class _Message(BaseModel):
    model_config = ConfigDict(strict=True)
    role: Literal["system", "user", "assistant"]
    content: str = Field(min_length=1)


class _RequestBody(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    model: str = Field(min_length=1)
    messages: list[_Message] = Field(min_length=1)
    stream: Literal[False]


class _Choice(BaseModel):
    model_config = ConfigDict(strict=True)
    index: int = Field(ge=0)
    finish_reason: str = Field(min_length=1)
    message: _Message


class _Usage(BaseModel):
    model_config = ConfigDict(strict=True)
    prompt_tokens: int = Field(ge=0)
    completion_tokens: int = Field(ge=0)
    total_tokens: int = Field(ge=0)


class _Completion(BaseModel):
    model_config = ConfigDict(strict=True)
    id: str = Field(min_length=1)
    model: str = Field(min_length=1)
    created: int = Field(ge=0)
    choices: list[_Choice] = Field(min_length=1)
    usage: _Usage | None = None


def _build_request() -> InferenceRequest:
    """Render one supported SDK profile: a unified models endpoint."""
    cost = scenario.price_pilot()
    return {
        "method": "POST",
        "url": (
            f"{RESOURCE}/models/chat/completions?api-version={API_VERSION}"
        ),
        "headers": {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": "Bearer <redacted-key>",
            "api-key": "<redacted-key>",
        },
        "body": json.dumps(
            {
                "model": MODEL,
                "messages": [
                    {"role": "system", "content": scenario.BRIEF},
                    {
                        "role": "user",
                        "content": (
                            "Summarize this computed pilot cost and "
                            "request human approval: "
                            + json.dumps(cost, sort_keys=True)
                        ),
                    },
                ],
                "stream": False,
            }
        ),
    }


def _validate_request(request: InferenceRequest) -> _RequestBody:
    """Check the chosen endpoint profile, version, headers and body."""
    url = urlsplit(request["url"])
    expected_headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Authorization": "Bearer <redacted-key>",
        "api-key": "<redacted-key>",
    }
    checks = (
        request["method"] == "POST",
        url.scheme == "https",
        url.netloc == "workshop-example.services.ai.azure.com",
        url.path == "/models/chat/completions",
        parse_qs(url.query) == {"api-version": [API_VERSION]},
        not url.fragment,
        request["headers"] == expected_headers,
    )
    if not all(checks):
        message = "Request does not match the redacted 1.0.0b9 profile."
        raise ValueError(message)
    return _RequestBody.model_validate_json(request["body"])


def _failure(code: str, message: str, *, blocked: bool = False) -> DemoResult:
    """Report a fixture failure without claiming a cloud call ran."""
    status: Status = "blocked" if blocked else "error"
    error: DemoError = {"code": code, "message": message}
    return result(
        demo=DEMO_NAME,
        technology=TECHNOLOGY,
        lane="legacy",
        mode="local_contract",
        status=status,
        headline="Synthetic inference response exercised an error path.",
        evidence=evidence(
            provider="azure-ai-inference", fixture_id=FIXTURE_ID
        ),
        error=error,
    )


async def run_azure_ai_inference_demo(
    *,
    execution: str = "offline",
    port: InferencePort | None = None,
) -> DemoResult:
    """Validate the legacy request and decode one synthetic response.

    Args:
        execution: ``offline`` runs the contract. ``live`` reports
            that this teaching module has no network adapter.
        port: Optional local fixture supplier, including error cases.

    Returns:
        A contract result with both request shapes and decoded text.

    Raises:
        ValueError: If execution is neither ``offline`` nor ``live``.
        RuntimeError: If a fixture supplies an unhandled HTTP status.
    """
    if execution not in {"offline", "live"}:
        message = "execution must be 'offline' or 'live'."
        raise ValueError(message)
    if execution == "live":
        return missing_configuration(
            demo=DEMO_NAME,
            technology=TECHNOLOGY,
            lane="legacy",
            provider="azure-ai-inference",
            missing=["a live adapter (intentionally absent in this demo)"],
            next_steps=[
                "Run offline to inspect this contract without a request.",
                "Use Foundry clients / OpenAI v1 for live inference.",
            ],
        )

    request = _build_request()
    body = _validate_request(request)
    adapter = port if port is not None else FixtureInferencePort()
    try:
        reply = await adapter.replay(request)
    except TimeoutError:
        return _failure("timeout", "The local fixture replay timed out.")
    if reply.status_code in {401, 403}:
        return _failure(
            "authorization_denied",
            f"Fixture HTTP {reply.status_code}: access was denied.",
            blocked=True,
        )
    if reply.status_code == 429:
        return _failure("throttled", "Fixture HTTP 429: retry later.")
    if reply.status_code != 200:
        message = f"Unhandled fixture HTTP status: {reply.status_code}."
        raise RuntimeError(message)
    try:
        completion = _Completion.model_validate_json(reply.body)
    except ValidationError:
        # Do not echo untrusted payloads into a console or error log.
        return _failure(
            "malformed_response", "Fixture is not a valid chat completion."
        )
    if completion.choices[0].message.role != "assistant":
        return _failure(
            "malformed_response", "The completion must contain an assistant."
        )

    cost = scenario.price_pilot()
    acceptable, failures = scenario.proposal_is_acceptable(
        cost=cost, approved=False, cited_sources=[scenario.SCENARIO_ID]
    )
    return result(
        demo=DEMO_NAME,
        technology=TECHNOLOGY,
        lane="legacy",
        mode="local_contract",
        status="ok",
        headline="Legacy request validated; synthetic response decoded.",
        evidence=evidence(
            provider="azure-ai-inference",
            fixture_id=FIXTURE_ID,
            requested_model=MODEL,
            observed_model=completion.model,
        ),
        data={
            "legacy_request": request,
            "current_request": {
                "method": "POST",
                "url": f"{RESOURCE}/openai/v1/chat/completions",
                "headers": {
                    "Content-Type": "application/json",
                    "Authorization": "Bearer <redacted-key-or-token>",
                },
                "body": request["body"],
            },
            "request_body": body.model_dump(),
            "api_version": API_VERSION,
            "response": completion.model_dump(),
            "cost": cost,
            "approval": {"accepted": acceptable, "failures": failures},
            "replacement": "Foundry clients / OpenAI v1 surface",
            "why_migrate": (
                "The 1.0.0b9 beta last shipped on 2025-02-15; current "
                "Foundry clients share the OpenAI v1 API surface."
            ),
            "contract_notes": [
                "Example resource and deployment; neither is provisioned.",
                "No SDK import is needed, including when it is absent.",
                "SDK key auth sends Authorization and api-key together.",
                "Bearer keys support serverless and managed endpoints; "
                "api-key supports Azure OpenAI and unified inference.",
                "OpenAI v1 defaults to v1 without a dated api-version.",
                "Routine SDK transport headers are omitted.",
                "The completion is synthetic; no model ran.",
            ],
            "sources": [SDK_SOURCE, CURRENT_REFERENCE],
        },
    )

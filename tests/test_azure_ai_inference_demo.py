from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import pytest
from pydantic import ValidationError

from msai_demo import azure_ai_inference_demo as demo
from msai_demo import scenario

if TYPE_CHECKING:
    from msai_demo.azure_ai_inference_demo import (
        FixtureReply,
        InferenceRequest,
    )


@dataclass
class RecordingPort:
    reply: FixtureReply
    requests: list[InferenceRequest] = field(default_factory=list)

    async def replay(self, request: InferenceRequest) -> FixtureReply:
        self.requests.append(request)
        return self.reply


class TimeoutPort:
    async def replay(self, request: InferenceRequest) -> FixtureReply:
        del request
        message = "A deliberate local timeout."
        raise TimeoutError(message)


class BrokenPort:
    async def replay(self, request: InferenceRequest) -> FixtureReply:
        del request
        message = "A programming bug in the injected fixture."
        raise LookupError(message)


def _response_body() -> dict[str, object]:
    return {
        "id": "synthetic-custom-completion",
        "model": "synthetic-observed-model",
        "created": 1739577600,
        "choices": [
            {
                "index": 0,
                "finish_reason": "stop",
                "message": {
                    "role": "assistant",
                    "content": "Await human approval.",
                },
            }
        ],
    }


def test_default_contract_runs_without_an_sdk_or_credentials() -> None:
    outcome = asyncio.run(demo.run_azure_ai_inference_demo())

    assert outcome["demo"] == "azure-ai-inference"
    assert outcome["mode"] == "local_contract"
    assert outcome["status"] == "ok"
    assert outcome["evidence"] == {
        "provider": "azure-ai-inference",
        "fixture_id": "azure-ai-inference-v1",
        "sdk_invoked": False,
        "network_attempted": False,
        "service_executed": False,
        "requested_model": "workshop-deployment",
        "observed_model": "workshop-deployment",
    }
    data = outcome["data"]
    assert data is not None
    assert data["cost"] == scenario.price_pilot()
    assert data["response"]["usage"] is None
    assert (
        str(scenario.price_pilot()["total"])
        in (data["response"]["choices"][0]["message"]["content"])
    )
    assert data["approval"] == {
        "accepted": False,
        "failures": ["No human approval recorded."],
    }
    assert data["replacement"] == "Foundry clients / OpenAI v1 surface"
    assert "2025-02-15" in data["why_migrate"]


def test_legacy_and_current_requests_keep_the_same_business_body() -> None:
    port = RecordingPort(demo.FixtureReply(200, json.dumps(_response_body())))

    outcome = asyncio.run(demo.run_azure_ai_inference_demo(port=port))

    assert len(port.requests) == 1
    request = port.requests[0]
    assert request["method"] == "POST"
    assert request["url"] == (
        "https://workshop-example.services.ai.azure.com/models/"
        "chat/completions?api-version=2024-05-01-preview"
    )
    assert request["headers"]["Authorization"] == "Bearer <redacted-key>"
    assert request["headers"]["api-key"] == "<redacted-key>"
    data = outcome["data"]
    assert data is not None
    assert data["current_request"]["url"] == (
        "https://workshop-example.services.ai.azure.com/"
        "openai/v1/chat/completions"
    )
    assert data["current_request"]["body"] == request["body"]
    assert data["request_body"]["messages"][0]["content"] == scenario.BRIEF
    assert data["request_body"]["stream"] is False
    assert outcome["evidence"]["observed_model"] == "synthetic-observed-model"
    assert data["response"]["choices"][0]["message"]["content"] == (
        "Await human approval."
    )


def test_live_is_blocked_before_even_an_injected_port_is_called() -> None:
    port = RecordingPort(demo.FixtureReply(200, "{}"))

    outcome = asyncio.run(
        demo.run_azure_ai_inference_demo(execution="live", port=port)
    )

    assert outcome["mode"] == "not_run"
    assert outcome["status"] == "blocked"
    assert outcome["error"] is not None
    assert outcome["error"]["code"] == "missing_configuration"
    assert outcome["evidence"]["network_attempted"] is False
    assert port.requests == []


def test_unknown_execution_is_rejected() -> None:
    with pytest.raises(ValueError, match="execution must be"):
        asyncio.run(demo.run_azure_ai_inference_demo(execution="typo"))


@pytest.mark.parametrize(
    ("status_code", "expected_status", "code"),
    [
        (401, "blocked", "authorization_denied"),
        (403, "blocked", "authorization_denied"),
        (429, "error", "throttled"),
    ],
)
def test_known_http_fixtures_are_reported_honestly(
    status_code: int, expected_status: str, code: str
) -> None:
    port = RecordingPort(demo.FixtureReply(status_code, "sensitive payload"))

    outcome = asyncio.run(demo.run_azure_ai_inference_demo(port=port))

    assert outcome["status"] == expected_status
    assert outcome["mode"] == "local_contract"
    assert outcome["error"] is not None
    assert outcome["error"]["code"] == code
    assert outcome["evidence"]["network_attempted"] is False
    assert outcome["evidence"]["service_executed"] is False
    assert "sensitive payload" not in str(outcome)


def test_timeout_is_a_local_fixture_failure() -> None:
    outcome = asyncio.run(demo.run_azure_ai_inference_demo(port=TimeoutPort()))
    assert outcome["status"] == "error"
    assert outcome["error"] is not None
    assert outcome["error"]["code"] == "timeout"
    assert outcome["evidence"]["fixture_id"] == "azure-ai-inference-v1"


def test_unknown_status_is_not_manufactured_into_success() -> None:
    port = RecordingPort(demo.FixtureReply(500, "{}"))
    with pytest.raises(RuntimeError, match="Unhandled fixture HTTP status"):
        asyncio.run(demo.run_azure_ai_inference_demo(port=port))


def test_programming_failure_is_not_swallowed() -> None:
    with pytest.raises(LookupError, match="programming bug"):
        asyncio.run(demo.run_azure_ai_inference_demo(port=BrokenPort()))


@pytest.mark.parametrize("payload", ["not JSON", "{}", "[]"])
def test_malformed_response_never_echoes_the_payload(payload: str) -> None:
    port = RecordingPort(demo.FixtureReply(200, payload))
    outcome = asyncio.run(demo.run_azure_ai_inference_demo(port=port))
    assert outcome["status"] == "error"
    assert outcome["error"] == {
        "code": "malformed_response",
        "message": "Fixture is not a valid chat completion.",
    }


@pytest.mark.parametrize(
    "choices",
    [
        [],
        [{"index": 0, "finish_reason": "stop", "message": {}}],
        [
            {
                "index": 0,
                "finish_reason": "stop",
                "message": {"role": "user", "content": "Wrong role."},
            }
        ],
    ],
)
def test_invalid_choices_are_not_presented_as_completions(
    choices: list[dict[str, object]],
) -> None:
    body = _response_body()
    body["choices"] = choices
    port = RecordingPort(demo.FixtureReply(200, json.dumps(body)))
    outcome = asyncio.run(demo.run_azure_ai_inference_demo(port=port))
    assert outcome["status"] == "error"
    assert outcome["error"] is not None
    assert outcome["error"]["code"] == "malformed_response"


@pytest.mark.parametrize("field_name", ["method", "url", "headers"])
def test_request_validator_rejects_broken_wire_contract(
    field_name: str,
) -> None:
    request = demo._build_request()
    if field_name == "method":
        request["method"] = "GET"
    elif field_name == "url":
        request["url"] = "https://example.invalid/chat/completions"
    else:
        request["headers"] = {}

    with pytest.raises(ValueError, match=r"redacted 1\.0\.0b9 profile"):
        demo._validate_request(request)


@pytest.mark.parametrize("body", ['{"messages": []}', "not JSON"])
def test_request_validator_rejects_invalid_json_body(body: str) -> None:
    request = demo._build_request()
    request["body"] = body

    with pytest.raises(ValidationError):
        demo._validate_request(request)

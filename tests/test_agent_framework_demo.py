from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import pytest

from msai_demo import agent_framework_demo as demo
from msai_demo import scenario
from msai_demo.offline import ScriptedChatClient
from msai_demo.providers import create_chat_client, resolve_model_name

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable
    from pathlib import Path

    from agent_framework import Agent, ChatContext, ChatOptions


def _proposal_json(**changes: object) -> str:
    proposal: dict[str, object] = {
        "title": "Customer-support pilot",
        "weeks": scenario.PILOT_WEEKS,
        "total_usd": scenario.price_pilot()["total"],
        "source": demo.retrieve_grounding()["source"],
        "requires_human_approval": True,
    }
    proposal.update(changes)
    return json.dumps(proposal)


def _scripted_port(final_reply: str) -> demo.FrameworkAgentPort:
    client = create_chat_client(
        "offline",
        replies=["Costed.", "Morgan.", "Draft ready.", final_reply],
        tool_plan=[("price_support_pilot", {"weeks": scenario.PILOT_WEEKS})],
    )
    return demo.FrameworkAgentPort(client=client)


@dataclass
class _BuildFailurePort(demo.FrameworkAgentPort):
    failure: Exception = field(
        default_factory=lambda: ModuleNotFoundError(
            "agent_framework unavailable"
        )
    )

    def build(self, grounding: demo.Grounding) -> Agent[ChatOptions]:
        del grounding
        raise self.failure


class _HttpError(Exception):
    def __init__(self, status_code: int) -> None:
        super().__init__("Sensitive provider response must not escape.")
        self.status_code = status_code


def _failing_client(cause: Exception | None) -> ScriptedChatClient:
    from agent_framework import ChatMiddleware
    from agent_framework.exceptions import ChatClientException

    class FailingMiddleware(ChatMiddleware):
        async def process(
            self,
            context: ChatContext,
            call_next: Callable[[], Awaitable[None]],
        ) -> None:
            del context, call_next
            message = "Sensitive SDK details must not escape."
            raise ChatClientException(message) from cause

    return ScriptedChatClient(middleware=[FailingMiddleware()])


def test_default_runner_exercises_the_real_offline_runtime() -> None:
    result = asyncio.run(demo.run_agent_framework_demo())

    assert result["demo"] == "agent-framework"
    assert result["lane"] == "current"
    assert result["mode"] == "local_execution"
    assert result["status"] == "ok"
    assert result["error"] is None
    assert result["evidence"]["sdk_invoked"] is True
    assert result["evidence"]["network_attempted"] is False
    assert result["evidence"]["service_executed"] is False
    assert result["evidence"]["requested_model"] == resolve_model_name(
        "offline"
    )
    assert result["evidence"]["observed_model"] == resolve_model_name(
        "offline"
    )
    data = result["data"]
    assert data is not None
    assert data["scenario_id"] == scenario.SCENARIO_ID
    assert data["cost"] == scenario.price_pilot()
    assert data["usage"] is None
    assert data["accepted"] is False
    memory = data["session"]
    assert memory["remembered_first_turn"] is True
    assert len(memory["replies"]) == 2
    assert len(memory["user_messages"]) == 2
    assert len(memory["pricing_tool_results"]) == 1
    assert (
        json.loads(memory["pricing_tool_results"][0]) == scenario.price_pilot()
    )
    assert len(data["stream_chunks"]) > 1
    assert "".join(data["stream_chunks"]) == (
        "Draft ready for human review; no work accepted."
    )
    proposal = demo.Proposal.model_validate(data["structured_proposal"])
    assert proposal.total_usd == scenario.price_pilot()["total"]
    assert proposal.source == data["grounding"]["source"]
    assert proposal.requires_human_approval is True


def test_session_supplies_first_turn_and_tool_result_to_next_request() -> None:
    from agent_framework import ChatMiddleware

    requests: list[list[tuple[str, str]]] = []
    formats: list[object] = []

    class Recorder(ChatMiddleware):
        async def process(
            self,
            context: ChatContext,
            call_next: Callable[[], Awaitable[None]],
        ) -> None:
            requests.append([(m.role, m.text) for m in context.messages])
            formats.append((context.options or {}).get("response_format"))
            await call_next()

    client = ScriptedChatClient(
        replies=["Costed.", "Morgan.", "Review draft.", _proposal_json()],
        tool_plan=[("price_support_pilot", {})],
        middleware=[Recorder()],
    )
    result = asyncio.run(
        demo.run_agent_framework_demo(
            port=demo.FrameworkAgentPort(client=client)
        )
    )

    assert result["status"] == "ok"
    second_request = next(
        messages
        for messages in requests
        if messages[-1] == ("user", "Who must approve this pilot?")
    )
    assert any(
        role == "user" and demo.MEMORY_FACT in text
        for role, text in second_request
    )
    assert ("assistant", "Costed.") in second_request
    assert any(role == "tool" for role, _ in second_request)
    assert formats[-1] is demo.Proposal
    assert client.turns == 5


def test_agent_and_pricing_tool_use_safe_explicit_defaults() -> None:
    agent = demo.build_agent("offline")
    pricing = demo.build_pricing_tool()

    assert agent.name == "PilotArchitect"
    assert pricing.approval_mode == "never_require"
    contents = asyncio.run(pricing.invoke(arguments={"weeks": 1}))
    assert json.loads(contents[0].text or "") == scenario.price_pilot(weeks=1)


@pytest.mark.parametrize("provider", ["anthropic", "unknown"])
def test_builder_rejects_unsupported_providers(provider: str) -> None:
    with pytest.raises(ValueError, match="supports offline and openai"):
        demo.build_agent(provider)


def test_runner_rejects_unknown_execution() -> None:
    with pytest.raises(ValueError, match="execution must be offline or live"):
        asyncio.run(demo.run_agent_framework_demo(execution="unknown"))


def test_missing_configuration_is_checked_before_client_creation() -> None:
    port = demo.FrameworkAgentPort(
        provider="openai", configured=lambda _: False
    )
    result = asyncio.run(
        demo.run_agent_framework_demo(execution="live", port=port)
    )

    assert result["mode"] == "not_run"
    assert result["status"] == "blocked"
    assert result["error"] is not None
    assert result["error"]["code"] == "missing_configuration"
    assert "OPENAI_API_KEY" in result["error"]["message"]
    assert result["evidence"]["sdk_invoked"] is False
    assert result["evidence"]["network_attempted"] is False


def test_configured_provider_mode_uses_the_injected_client_boundary() -> None:
    port = _scripted_port(_proposal_json())
    port.provider = "openai"
    port.configured = lambda _: True
    result = asyncio.run(
        demo.run_agent_framework_demo(execution="live", port=port)
    )

    # A local transport checks the live adapter's result envelope.
    assert result["mode"] == "live_model"
    assert result["status"] == "ok"
    assert result["evidence"]["network_attempted"] is True
    assert result["evidence"]["service_executed"] is True
    assert result["evidence"]["requested_model"] == resolve_model_name(
        "openai"
    )
    assert result["evidence"]["observed_model"] == resolve_model_name(
        "offline"
    )


@pytest.mark.parametrize("reported_model", ["provider-snapshot-1", None])
def test_observed_model_comes_from_response_metadata(
    reported_model: str | None,
) -> None:
    from agent_framework import ChatMiddleware, ChatResponse

    class ResponseMetadata(ChatMiddleware):
        async def process(
            self,
            context: ChatContext,
            call_next: Callable[[], Awaitable[None]],
        ) -> None:
            await call_next()
            if isinstance(context.result, ChatResponse):
                context.result.model = reported_model

    client = ScriptedChatClient(
        replies=["Costed.", "Morgan.", "Draft ready.", _proposal_json()],
        tool_plan=[("price_support_pilot", {})],
        middleware=[ResponseMetadata()],
    )
    port = demo.FrameworkAgentPort(
        provider="openai", client=client, configured=lambda _: True
    )
    result = asyncio.run(
        demo.run_agent_framework_demo(execution="live", port=port)
    )

    assert result["status"] == "ok"
    assert result["evidence"]["requested_model"] == resolve_model_name(
        "openai"
    )
    assert result["evidence"]["observed_model"] == reported_model


def test_missing_sdk_retains_local_cost_and_grounding() -> None:
    result = asyncio.run(
        demo.run_agent_framework_demo(port=_BuildFailurePort())
    )

    assert result["mode"] == "local_contract"
    assert result["status"] == "blocked"
    assert result["evidence"]["sdk_invoked"] is False
    assert result["evidence"]["fixture_id"] == "agent-sdk-missing-v1"
    assert result["error"] is not None
    assert result["error"]["code"] == "missing_sdk"
    assert result["data"] is not None
    assert result["data"]["cost"] == scenario.price_pilot()
    assert result["data"]["grounding"]["source"].startswith("Source: ")


@pytest.mark.parametrize(
    "final_reply",
    [
        "",
        "not json",
        "{}",
        _proposal_json(total_usd=scenario.price_pilot()["total"] + 1),
        _proposal_json(weeks=scenario.PILOT_WEEKS + 1),
        _proposal_json(source="Source: unsupported"),
        _proposal_json(requires_human_approval=False),
        _proposal_json(unexpected_field="reject"),
    ],
)
def test_invalid_structured_responses_fail_closed(final_reply: str) -> None:
    result = asyncio.run(
        demo.run_agent_framework_demo(port=_scripted_port(final_reply))
    )

    assert result["status"] == "error"
    assert result["mode"] == "local_execution"
    assert result["data"] is None
    assert result["error"] is not None
    assert result["error"]["code"] == "malformed_response"


@pytest.mark.parametrize(
    ("status_code", "error_code"),
    [
        (401, "authorization_denied"),
        (403, "authorization_denied"),
        (429, "throttled"),
    ],
)
def test_known_provider_errors_are_sanitized(
    status_code: int, error_code: str
) -> None:
    port = demo.FrameworkAgentPort(
        client=_failing_client(_HttpError(status_code))
    )
    result = asyncio.run(demo.run_agent_framework_demo(port=port))

    assert result["status"] == (
        "blocked" if error_code == "authorization_denied" else "error"
    )
    assert result["data"] is None
    assert result["error"] is not None
    assert result["error"]["code"] == error_code
    assert "Sensitive" not in json.dumps(result)
    assert result["evidence"]["service_executed"] is False


@pytest.mark.parametrize("cause", [None, _HttpError(500)])
def test_unknown_provider_errors_are_not_disguised(
    cause: Exception | None,
) -> None:
    from agent_framework.exceptions import ChatClientException

    port = demo.FrameworkAgentPort(client=_failing_client(cause))
    with pytest.raises(ChatClientException, match="Sensitive SDK details"):
        asyncio.run(demo.run_agent_framework_demo(port=port))


@pytest.mark.parametrize(
    "kind", ["builtin", "httpx", "wrapped_httpx", "httpx2", "wrapped_httpx2"]
)
def test_provider_timeouts_are_sanitized(kind: str) -> None:
    from httpx import ReadTimeout

    cause: Exception = TimeoutError("Sensitive transport details")
    if kind != "builtin":
        cause = ReadTimeout("Sensitive transport details")
    if kind == "wrapped_httpx":
        outer = RuntimeError("Provider wrapped the timeout")
        outer.__cause__ = cause
        cause = outer
    if kind in {"httpx2", "wrapped_httpx2"}:
        from httpx2 import ReadTimeout as ModernReadTimeout

        cause = ModernReadTimeout("Sensitive transport details")
    if kind == "wrapped_httpx2":
        provider_error = RuntimeError("Provider wrapped the timeout")
        provider_error.__cause__ = cause
        cause = provider_error
    port = demo.FrameworkAgentPort(client=_failing_client(cause))
    result = asyncio.run(demo.run_agent_framework_demo(port=port))

    assert result["status"] == "error"
    assert result["error"] is not None
    assert result["error"]["code"] == "timeout"
    assert "Sensitive" not in json.dumps(result)


def test_timeout_returns_a_handled_failure() -> None:
    result = asyncio.run(
        demo.run_agent_framework_demo(
            port=_BuildFailurePort(failure=TimeoutError("Sensitive detail"))
        )
    )

    assert result["status"] == "error"
    assert result["error"] is not None
    assert result["error"]["code"] == "timeout"
    assert "Sensitive" not in json.dumps(result)


@pytest.mark.parametrize("error_type", [RuntimeError, ValueError])
def test_unknown_build_errors_propagate(error_type: type[Exception]) -> None:
    port = _BuildFailurePort(failure=error_type("Unexpected build failure"))
    with pytest.raises(error_type, match="Unexpected build failure"):
        asyncio.run(demo.run_agent_framework_demo(port=port))


def test_retrieval_scores_terms_and_keeps_first_match_on_ties(
    tmp_path: Path,
) -> None:
    corpus = tmp_path / "notes.md"
    corpus.write_text(
        "Preamble is not a section.\n"
        "## Section: First\nAgents guide workflows.\nSource: first\n"
        "## Section: Second\nWorkflows require approval.\nSource: second\n",
        encoding="utf-8",
    )

    best = demo.retrieve_grounding("WORKFLOWS agents agents", path=corpus)
    assert best == {
        "section": "First",
        "text": "Agents guide workflows.",
        "source": "Source: first",
        "score": 2,
    }
    assert (
        demo.retrieve_grounding("workflows", path=corpus)["section"] == "First"
    )
    assert (
        demo.retrieve_grounding("approval", path=corpus)["section"] == "Second"
    )


@pytest.mark.parametrize(
    ("corpus_text", "query", "message"),
    [
        ("No headings.", "agents", "no Section headings"),
        ("## Section: Agents\nNo attribution.", "agents", "Source line"),
        (
            "## Section: Agents\nSource: local",
            "unrelated",
            "matches the query",
        ),
        ("## Section: Agents\nSource: local", "", "matches the query"),
    ],
)
def test_retrieval_rejects_missing_evidence(
    tmp_path: Path, corpus_text: str, query: str, message: str
) -> None:
    corpus = tmp_path / "notes.md"
    corpus.write_text(corpus_text, encoding="utf-8")

    with pytest.raises(ValueError, match=message):
        demo.retrieve_grounding(query, path=corpus)

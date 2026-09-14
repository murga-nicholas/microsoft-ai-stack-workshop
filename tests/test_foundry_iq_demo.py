from __future__ import annotations

import asyncio
from copy import deepcopy
from typing import cast

import pytest

from msai_demo import foundry_iq_demo as demo
from msai_demo import scenario


def _response() -> demo.KnowledgeResponse:
    return {
        "context": "The application owns its agent. A human must approve.",
        "citation_ids": ["source-a"],
        "citations": [
            {
                "id": "source-a",
                "source": "https://learn.microsoft.com/example",
                "quote": "The application owns its agent.",
            }
        ],
    }


class Port:
    fixture_id = "foundry-iq-test-v1"

    def __init__(self, response: demo.KnowledgeResponse) -> None:
        self.response = response
        self.request: demo.KnowledgeRequest | None = None

    async def retrieve(
        self, request: demo.KnowledgeRequest
    ) -> demo.KnowledgeResponse:
        self.request = request
        return deepcopy(self.response)


def test_default_fixture_validates_context_and_preserves_human_gate() -> None:
    actual = asyncio.run(demo.run_foundry_iq_demo())
    assert actual["mode"] == "local_contract"
    assert actual["status"] == "ok"
    assert actual["evidence"]["fixture_id"] == "foundry-iq-v1"
    assert not actual["evidence"]["sdk_invoked"]
    assert not actual["evidence"]["service_executed"]
    assert actual["data"] is not None
    data = actual["data"]
    assert data["knowledge_sources"] == [
        "Work IQ",
        "Fabric IQ",
        "Azure SQL",
        "file search",
        "MCP",
    ]
    assert data["citations_valid"] is True
    assert data["cost"] == scenario.price_pilot()
    assert data["acceptable"] is False
    assert data["acceptance_failures"] == ["No human approval recorded."]
    assert "not by your prompt" in data["authorization"]
    assert "does not execute authorization" in data["authorization"]
    assert "not an SDK or REST schema" in data["contract_kind"]
    assert asyncio.run(demo.run_foundry_iq_demo()) == actual


def test_injected_port_receives_explicit_application_request() -> None:
    port = Port(_response())
    actual = asyncio.run(demo.run_foundry_iq_demo(port=port))
    assert actual["status"] == "ok"
    assert actual["evidence"]["fixture_id"] == port.fixture_id
    assert port.request == {
        "question": scenario.BRIEF,
        "knowledge_sources": list(demo.KNOWLEDGE_SOURCES),
        "caller_context": "synthetic-workshop-caller",
        "include_citations": True,
    }


@pytest.mark.parametrize(
    "mutation",
    [
        "empty_context",
        "empty_references",
        "empty_id",
        "duplicate_id",
        "http_url",
        "missing_host",
        "empty_quote",
        "invented_quote",
        "dangling_reference",
        "unused_source",
        "missing_field",
        "wrong_context_type",
        "wrong_references_type",
        "wrong_citations_type",
        "wrong_source_type",
    ],
)
def test_invalid_grounding_is_rejected(mutation: str) -> None:
    response = _response()
    citation = response["citations"][0]
    match mutation:
        case "empty_context":
            response["context"] = " "
        case "empty_references":
            response["citation_ids"] = []
        case "empty_id":
            citation["id"] = ""
        case "duplicate_id":
            response["citations"].append(citation.copy())
        case "http_url":
            citation["source"] = "http://example.com"
        case "missing_host":
            citation["source"] = "https:///missing-host"
        case "empty_quote":
            citation["quote"] = ""
        case "invented_quote":
            citation["quote"] = "An unsupported invented statement."
        case "dangling_reference":
            response["citation_ids"].append("missing")
        case "unused_source":
            response["citation_ids"] = ["another"]
        case "missing_field":
            response = cast("demo.KnowledgeResponse", {"context": "text"})
        case "wrong_context_type":
            response["context"] = cast("str", 123)
        case "wrong_references_type":
            response["citation_ids"] = cast("list[str]", "source-a")
        case "wrong_citations_type":
            response["citations"] = cast("list[demo.KnowledgeCitation]", {})
        case "wrong_source_type":
            citation["source"] = cast("str", 123)
    actual = asyncio.run(demo.run_foundry_iq_demo(port=Port(response)))
    assert actual["mode"] == "local_contract"
    assert actual["status"] == "error"
    assert actual["error"] is not None
    assert actual["error"]["code"] == "malformed_response"
    assert not actual["evidence"]["network_attempted"]
    assert actual["data"] is not None
    assert "response" not in actual["data"]


def test_live_request_names_missing_integration_without_faking_it() -> None:
    actual = asyncio.run(demo.run_foundry_iq_demo(execution="live"))
    assert actual["mode"] == "not_run"
    assert actual["status"] == "blocked"
    assert actual["error"] is not None
    assert actual["error"]["code"] == "missing_configuration"
    assert not actual["evidence"]["network_attempted"]
    assert actual["next_steps"]


def test_unknown_execution_is_rejected() -> None:
    with pytest.raises(ValueError, match="execution"):
        asyncio.run(demo.run_foundry_iq_demo(execution="pretend"))

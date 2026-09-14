from __future__ import annotations

import asyncio
from functools import partial
from typing import TYPE_CHECKING

import pytest
from azure.core.exceptions import (
    ClientAuthenticationError,
    HttpResponseError,
    ServiceRequestError,
    ServiceResponseError,
)
from azure.core.pipeline.transport import HttpRequest, HttpResponse
from azure.search.documents.models import VectorizableTextQuery

from msai_demo import ai_search_demo as demo
from msai_demo import scenario
from msai_demo.contracts import evidence, result
from msai_demo.runtime import REPO_ROOT

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

    from msai_demo.contracts import Evidence, Mode


def _request() -> demo.SearchRequest:
    return {
        "search_text": scenario.BRIEF,
        "vector_fields": "content_vector",
        "semantic_configuration_name": "workshop-semantic",
        "top": 3,
    }


def _row(
    identifier: str = "source-a", score: float = 1.0
) -> dict[str, object]:
    return {
        "id": identifier,
        "content": "A passage about explicit approval.",
        "source": "https://learn.microsoft.com/example",
        "@search.score": score,
    }


class Client:
    def __init__(
        self,
        rows: list[Mapping[str, object]] | None = None,
        error: Exception | None = None,
    ) -> None:
        self.rows = [_row()] if rows is None else rows
        self.error = error
        self.kwargs: dict[str, object] = {}
        self.closed = False

    def search(self, **kwargs: object) -> Iterable[Mapping[str, object]]:
        self.kwargs = kwargs
        if self.error is not None:
            raise self.error
        return self.rows

    def close(self) -> None:
        self.closed = True

    def factory(self, endpoint: str, index_name: str) -> Client:
        assert endpoint == "https://workshop.search.windows.net"
        assert index_name == "notes"
        return self


def _port(client: Client) -> demo.LiveSearchPort:
    return demo.LiveSearchPort(
        "https://workshop.search.windows.net",
        "notes",
        executor=partial(demo._execute_search, client_factory=client.factory),
    )


def test_offline_default_uses_real_corpus_and_human_gate() -> None:
    actual = asyncio.run(demo.run_ai_search_demo(environ={}))
    assert actual["mode"] == "local_contract"
    assert actual["status"] == "ok"
    assert actual["evidence"]["fixture_id"] == "ai-search-v1"
    assert not actual["evidence"]["network_attempted"]
    assert actual["data"] is not None
    data = actual["data"]
    assert data["cost"] == scenario.price_pilot()
    assert data["acceptable"] is False
    assert data["acceptance_failures"] == ["No human approval recorded."]
    assert data["rename"]["date"] == "2023-11-15"
    notes = (REPO_ROOT / "data/microsoft_ai_stack_notes.md").read_text(
        encoding="utf-8"
    )
    assert len(data["citations"]) == 3
    for hit in data["citations"]:
        assert hit["content"] in notes
        assert hit["source"] in notes
    assert asyncio.run(demo.run_ai_search_demo(environ={})) == actual


def test_real_sdk_query_and_semantic_order_are_used() -> None:
    first = _row("a", 2.0)
    first["@search.reranker_score"] = 1.0
    second = _row("b", 1.0)
    second["@search.reranker_score"] = 3.0
    client = Client([first, second, second])
    actual = asyncio.run(demo.run_ai_search_demo(port=_port(client)))
    assert client.closed
    assert client.kwargs["search_text"] == scenario.BRIEF
    assert client.kwargs["query_type"] == "semantic"
    vectors = client.kwargs["vector_queries"]
    assert isinstance(vectors, list)
    assert isinstance(vectors[0], VectorizableTextQuery)
    assert vectors[0].as_dict() == {
        "kind": "text",
        "text": scenario.BRIEF,
        "fields": "content_vector",
        "k": 50,
    }
    assert actual["data"] is not None
    assert [hit["id"] for hit in actual["data"]["citations"]] == ["b", "a"]
    assert actual["mode"] == "live_service"
    assert actual["evidence"]["sdk_invoked"]
    assert actual["evidence"]["service_executed"]


def test_sdk_default_client_can_be_constructed_without_credentials() -> None:
    client = demo._create_client(
        "https://workshop.search.windows.net", "notes"
    )
    client.close()


def test_owned_client_delegates_and_closes_its_credential() -> None:
    client = Client()
    credential = Client()
    owned = demo._OwnedSearchClient(client, credential)
    assert list(owned.search(search_text="question")) == [_row()]
    owned.close()
    assert client.closed
    assert credential.closed


def test_port_resets_evidence_between_success_and_denial() -> None:
    client = Client()
    port = _port(client)
    assert asyncio.run(demo.run_ai_search_demo(port=port))["status"] == "ok"
    client.error = _http_error(403)
    denied = asyncio.run(demo.run_ai_search_demo(port=port))
    assert denied["status"] == "blocked"
    assert denied["mode"] == "live_service"
    assert not denied["evidence"]["service_executed"]


def test_empty_search_results_do_not_claim_grounding() -> None:
    actual = asyncio.run(demo.run_ai_search_demo(port=_port(Client([]))))
    assert actual["data"] is not None
    assert actual["data"]["citations"] == []
    assert (
        "No grounding source cited." in actual["data"]["acceptance_failures"]
    )


@pytest.mark.parametrize(
    "settings, missing",
    [
        ({}, "AZURE_SEARCH_ENDPOINT, AZURE_SEARCH_INDEX"),
        (
            {"AZURE_SEARCH_ENDPOINT": "https://example.com"},
            "AZURE_SEARCH_INDEX",
        ),
        ({"AZURE_SEARCH_INDEX": "notes"}, "AZURE_SEARCH_ENDPOINT"),
    ],
)
def test_missing_configuration(settings: dict[str, str], missing: str) -> None:
    actual = asyncio.run(
        demo.run_ai_search_demo(execution="live", environ=settings)
    )
    assert actual["mode"] == "not_run"
    assert actual["error"] is not None
    assert missing in actual["error"]["message"]
    assert not actual["evidence"]["network_attempted"]


def test_configured_live_path_uses_injected_constructor() -> None:
    client = Client()

    def factory(endpoint: str, index_name: str) -> demo.SearchPort:
        assert endpoint == "https://workshop.search.windows.net"
        assert index_name == "notes"
        return _port(client)

    actual = asyncio.run(
        demo.run_ai_search_demo(
            execution="live",
            environ={
                "AZURE_SEARCH_ENDPOINT": "https://workshop.search.windows.net",
                "AZURE_SEARCH_INDEX": "notes",
                "AZURE_SEARCH_SEMANTIC_CONFIGURATION": "explicit-semantic",
            },
            live_port_factory=factory,
        )
    )
    assert actual["status"] == "ok"
    assert client.kwargs["semantic_configuration_name"] == "explicit-semantic"


def test_missing_optional_sdk_is_a_preflight_failure() -> None:
    def absent(
        endpoint: str, index_name: str, request: demo.SearchRequest
    ) -> list[Mapping[str, object]]:
        del endpoint, index_name, request
        message = "azure.search.documents is not installed"
        raise ModuleNotFoundError(message)

    port = demo.LiveSearchPort("https://example.com", "notes", executor=absent)
    actual = asyncio.run(demo.run_ai_search_demo(port=port))
    assert actual["mode"] == "not_run"
    assert actual["error"] is not None
    assert actual["error"]["code"] == "missing_sdk"
    assert not actual["evidence"]["sdk_invoked"]
    assert not actual["evidence"]["network_attempted"]


def _http_error(
    status: int, *, has_response: bool = True
) -> HttpResponseError:
    response = HttpResponse(HttpRequest("POST", "https://example.com"), None)
    response.status_code = status
    response.reason = "Test response"
    error = HttpResponseError(response=response)
    if not has_response:
        error.response = None
    return error


@pytest.mark.parametrize(
    "status, code",
    [
        (401, "authorization_denied"),
        (403, "authorization_denied"),
        (429, "throttled"),
    ],
)
def test_known_http_error_is_a_blocked_live_call(
    status: int, code: str
) -> None:
    client = Client(error=_http_error(status))
    actual = asyncio.run(demo.run_ai_search_demo(port=_port(client)))
    assert client.closed
    assert actual["mode"] == "live_service"
    assert actual["status"] == "blocked"
    assert actual["error"] is not None
    assert actual["error"]["code"] == code
    assert actual["evidence"]["network_attempted"]
    assert not actual["evidence"]["service_executed"]


def test_authentication_preflight_does_not_claim_network() -> None:
    client = Client(error=_http_error(401, has_response=False))
    actual = asyncio.run(demo.run_ai_search_demo(port=_port(client)))
    assert actual["mode"] == "not_run"
    assert not actual["evidence"]["network_attempted"]


@pytest.mark.parametrize("has_response", [False, True])
def test_credential_failure_is_classified_before_or_after_http(
    has_response: bool,
) -> None:
    error = ClientAuthenticationError(message="Test credential failure")
    if has_response:
        error.response = _http_error(401).response
    actual = asyncio.run(
        demo.run_ai_search_demo(port=_port(Client(error=error)))
    )
    assert actual["status"] == "blocked"
    assert actual["mode"] == ("live_service" if has_response else "not_run")
    assert actual["error"] is not None
    assert actual["error"]["code"] == (
        "authorization_denied" if has_response else "credential_unavailable"
    )


def test_unrecognized_sdk_failure_raises_and_closes_client() -> None:
    client = Client(error=_http_error(500))
    with pytest.raises(HttpResponseError):
        asyncio.run(demo.run_ai_search_demo(port=_port(client)))
    assert client.closed


@pytest.mark.parametrize(
    "error", [ServiceRequestError("request"), ServiceResponseError("response")]
)
def test_transport_failure_is_structured(error: Exception) -> None:
    actual = asyncio.run(
        demo.run_ai_search_demo(port=_port(Client(error=error)))
    )
    assert actual["mode"] == "live_service"
    assert actual["status"] == "blocked"
    assert actual["error"] is not None
    assert actual["error"]["code"] == "service_unavailable"


@pytest.mark.parametrize(
    "field, value",
    [
        ("id", ""),
        ("content", None),
        ("source", 4),
        ("@search.score", None),
        ("@search.score", True),
        ("@search.score", float("nan")),
        ("@search.score", float("inf")),
        ("@search.reranker_score", "invalid"),
        ("source", "http://example.com"),
        ("source", "https:///missing-host"),
    ],
)
def test_malformed_live_response_preserves_execution_evidence(
    field: str, value: object
) -> None:
    row = _row()
    row[field] = value
    actual = asyncio.run(demo.run_ai_search_demo(port=_port(Client([row]))))
    assert actual["status"] == "error"
    assert actual["mode"] == "live_service"
    assert actual["evidence"]["service_executed"]
    assert actual["error"] is not None
    assert actual["error"]["code"] == "malformed_response"


def test_malformed_fixture_retains_contract_mode() -> None:
    class MalformedFixture(demo.FixtureSearchPort):
        async def search(
            self, request: demo.SearchRequest
        ) -> list[demo.SearchHit]:
            hits = await super().search(request)
            hits[0]["source"] = "file:///secret.txt"
            return hits

    actual = asyncio.run(demo.run_ai_search_demo(port=MalformedFixture()))
    assert actual["mode"] == "local_contract"
    assert actual["status"] == "error"
    assert not actual["evidence"]["network_attempted"]


def test_invalid_execution_fails_before_adapter() -> None:
    with pytest.raises(ValueError, match="execution"):
        asyncio.run(demo.run_ai_search_demo(execution="pretend"))


@pytest.mark.parametrize(
    "mode, record",
    [
        ("live_service", evidence(provider="test")),
        ("local_contract", evidence(provider="test")),
        (
            "local_contract",
            evidence(
                provider="test", service_executed=True, fixture_id="test"
            ),
        ),
    ],
)
def test_contract_rejects_dishonest_evidence(
    mode: Mode, record: Evidence
) -> None:
    with pytest.raises(ValueError):
        result(
            demo="test",
            technology="test",
            lane="current",
            mode=mode,
            status="ok",
            headline="Cannot claim work that did not happen.",
            evidence=record,
        )

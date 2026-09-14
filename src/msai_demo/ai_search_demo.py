"""Azure AI Search: the current index-based retrieval service.

Formerly Azure Cognitive Search, this service combines keyword and
vector retrieval with a semantic ranker. The application still owns
the index schema, the query and the decision to trust a citation.
Offline responses come from the workshop notes; ranking, citation
checks and pilot costing run as ordinary Python in both paths.

Run it:

    uv run msai-demo ai-search
    uv run msai-demo ai-search --execution live
"""

from __future__ import annotations

import asyncio
import math
import os
import re
from typing import TYPE_CHECKING, Protocol, TypedDict, cast
from urllib.parse import urlsplit

from msai_demo import scenario
from msai_demo.contracts import (
    DemoResult,
    Mode,
    evidence,
    missing_configuration,
    result,
)
from msai_demo.runtime import REPO_ROOT

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Mapping

DEMO_NAME = "ai-search"
TECHNOLOGY = "Azure AI Search (azure-search-documents 12.0.0)"
RENAME_SOURCE = (
    "https://techcommunity.microsoft.com/blog/azure-ai-foundry-blog/"
    "announcing-general-availability-of-vector-search-and-semantic-"
    "ranker-in-azure-ai/3978525"
)


class SearchRequest(TypedDict):
    """Application-owned query inputs, mapped to the Search SDK."""

    search_text: str
    vector_fields: str
    semantic_configuration_name: str
    top: int


class SearchHit(TypedDict):
    """Validated passage and service ranking metadata."""

    id: str
    content: str
    source: str
    score: float
    semantic_score: float | None


class SearchError(Exception):
    """A known boundary failure with explicit execution evidence.

    Args:
        code: Stable error code safe to display.
        network_attempted: Whether the SDK reached the HTTP boundary.
    """

    def __init__(self, code: str, *, network_attempted: bool = True) -> None:
        """Keep vendor messages, which can contain secrets, private."""
        super().__init__(code)
        self.code = code
        self.network_attempted = network_attempted


class SearchPort(Protocol):
    """The one retrieval call, including what actually executed."""

    mode: Mode
    fixture_id: str | None
    sdk_invoked: bool
    network_attempted: bool
    service_executed: bool

    async def search(self, request: SearchRequest) -> list[SearchHit]:
        """Retrieve passages for one hybrid query."""
        raise NotImplementedError


class FixtureSearchPort:
    """Read real notes and return explicitly synthetic search scores."""

    mode: Mode = "local_contract"
    fixture_id: str | None = "ai-search-v1"
    sdk_invoked = False
    network_attempted = False
    service_executed = False

    async def search(self, request: SearchRequest) -> list[SearchHit]:
        """Use lexical overlap to create deterministic fixture rows."""
        terms = set(re.findall(r"\w+", request["search_text"].casefold()))
        notes = (REPO_ROOT / "data/microsoft_ai_stack_notes.md").read_text(
            encoding="utf-8"
        )
        hits: list[SearchHit] = []
        for section in notes.split("## Section: ")[1:]:
            name, _, body = section.partition("\n")
            content, _, source = body.partition("Source: ")
            words = set(re.findall(r"\w+", content.casefold()))
            hits.append(
                {
                    "id": name.strip(),
                    "content": content.strip(),
                    "source": source.strip(),
                    "score": float(len(terms & words)),
                    "semantic_score": None,
                }
            )
        return hits


class _SearchClient(Protocol):
    """The small synchronous SDK surface used by the live adapter."""

    def search(self, **kwargs: object) -> Iterable[Mapping[str, object]]:
        raise NotImplementedError

    def close(self) -> None:
        raise NotImplementedError


class _Credential(Protocol):
    """Lifecycle of the Entra credential owned by this adapter."""

    def close(self) -> None:
        raise NotImplementedError


class _OwnedSearchClient:
    """Close both Azure objects even if client cleanup fails."""

    def __init__(self, client: _SearchClient, credential: _Credential) -> None:
        self._client = client
        self._credential = credential

    def search(self, **kwargs: object) -> Iterable[Mapping[str, object]]:
        return self._client.search(**kwargs)

    def close(self) -> None:
        try:
            self._client.close()
        finally:
            self._credential.close()


def _create_client(endpoint: str, index_name: str) -> _SearchClient:
    """Construct the verified SDK with an Entra credential."""
    from azure.identity import DefaultAzureCredential
    from azure.search.documents import SearchClient

    credential = DefaultAzureCredential()
    client = cast(
        "_SearchClient",
        SearchClient(
            endpoint=endpoint,
            index_name=index_name,
            credential=credential,
        ),
    )
    return _OwnedSearchClient(client, credential)


def _execute_search(
    endpoint: str,
    index_name: str,
    request: SearchRequest,
    *,
    client_factory: Callable[[str, str], _SearchClient] = _create_client,
) -> list[Mapping[str, object]]:
    """Serialize the real hybrid request and consume its lazy pages."""
    from azure.core.exceptions import (
        ClientAuthenticationError,
        HttpResponseError,
        ServiceRequestError,
        ServiceResponseError,
    )
    from azure.search.documents.models import VectorizableTextQuery

    client = client_factory(endpoint, index_name)
    try:
        # The index vectorizer produces embeddings. A fake numeric
        # vector would hide a model/dimension mismatch in a live demo.
        vector = VectorizableTextQuery(
            text=request["search_text"],
            fields=request["vector_fields"],
            k_nearest_neighbors=50,
        )
        return list(
            client.search(
                search_text=request["search_text"],
                vector_queries=[vector],
                query_type="semantic",
                semantic_configuration_name=request[
                    "semantic_configuration_name"
                ],
                select=["id", "content", "source"],
                top=request["top"],
            )
        )
    except ClientAuthenticationError as exc:
        code = (
            "authorization_denied"
            if exc.response is not None
            else "credential_unavailable"
        )
        raise SearchError(
            code, network_attempted=exc.response is not None
        ) from exc
    except HttpResponseError as exc:
        codes = {401: "authorization_denied", 403: "authorization_denied"}
        codes[429] = "throttled"
        if exc.status_code not in codes:
            raise
        raise SearchError(
            codes[exc.status_code],
            network_attempted=exc.response is not None,
        ) from exc
    except (ServiceRequestError, ServiceResponseError) as exc:
        code = "service_unavailable"
        raise SearchError(code) from exc
    finally:
        client.close()


class LiveSearchPort:
    """Call the Search SDK, keeping its synchronous I/O off the loop.

    Args:
        endpoint: Configured Azure AI Search resource endpoint.
        index_name: Existing index with a configured vectorizer.
        executor: Injectable SDK boundary for deterministic tests.
    """

    mode: Mode = "live_service"
    fixture_id: str | None = None

    def __init__(
        self,
        endpoint: str,
        index_name: str,
        *,
        executor: Callable[
            [str, str, SearchRequest], list[Mapping[str, object]]
        ] = _execute_search,
    ) -> None:
        """Store configuration without importing an optional SDK."""
        self.endpoint = endpoint
        self.index_name = index_name
        self._executor = executor
        self.sdk_invoked = False
        self.network_attempted = False
        self.service_executed = False

    async def search(self, request: SearchRequest) -> list[SearchHit]:
        """Decode returned rows before the application trusts them."""
        self.sdk_invoked = False
        self.network_attempted = False
        self.service_executed = False
        try:
            rows = await asyncio.to_thread(
                self._executor, self.endpoint, self.index_name, request
            )
        except SearchError as exc:
            self.sdk_invoked = True
            self.network_attempted = exc.network_attempted
            raise
        self.sdk_invoked = True
        self.network_attempted = True
        self.service_executed = True
        return [_decode_hit(row) for row in rows]


def _decode_hit(row: Mapping[str, object]) -> SearchHit:
    """Convert SDK dictionaries into a validated application type."""
    texts = [row.get(name) for name in ("id", "content", "source")]
    if not all(isinstance(text, str) and text.strip() for text in texts):
        message = "A search hit needs nonempty id, content and source."
        raise ValueError(message)
    return {
        "id": cast("str", texts[0]),
        "content": cast("str", texts[1]),
        "source": cast("str", texts[2]),
        "score": _score(row.get("@search.score")),
        "semantic_score": (
            None
            if row.get("@search.reranker_score") is None
            else _score(row["@search.reranker_score"])
        ),
    }


def _score(value: object) -> float:
    """Reject missing, nonnumeric and nonfinite ranking metadata."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        message = "A search score must be a finite number."
        raise TypeError(message)
    number = float(value)
    if not math.isfinite(number):
        message = "A search score must be finite."
        raise ValueError(message)
    return number


def _rank(hits: list[SearchHit], top: int) -> list[SearchHit]:
    """Prefer reranker order and deduplicate citations by section."""
    ranked = sorted(
        hits,
        key=lambda hit: (
            -(
                hit["semantic_score"]
                if hit["semantic_score"] is not None
                else hit["score"]
            ),
            -hit["score"],
            hit["id"],
        ),
    )
    unique: dict[str, SearchHit] = {}
    for hit in ranked:
        parsed = urlsplit(hit["source"])
        if parsed.scheme != "https" or not parsed.netloc:
            message = "A citation must identify an HTTPS source."
            raise ValueError(message)
        unique.setdefault(hit["id"], hit)
    return list(unique.values())[:top]


def _payload(request: SearchRequest) -> dict[str, object]:
    """Expose prerequisites and query shape without making claims."""
    return {
        "scenario": scenario.BRIEF,
        "request": dict(request),
        "query_shape": {
            "search_text": request["search_text"],
            "vector_queries": [
                {
                    "kind": "text",
                    "text": request["search_text"],
                    "fields": request["vector_fields"],
                    "k_nearest_neighbors": 50,
                }
            ],
            "query_type": "semantic",
            "semantic_configuration_name": request[
                "semantic_configuration_name"
            ],
        },
        "rename": {
            "from": "Azure Cognitive Search",
            "to": "Azure AI Search",
            "date": "2023-11-15",
            "source": RENAME_SOURCE,
        },
        "ownership": "Your application builds and queries the index.",
        "live_prerequisites": (
            "Index fields id/content/source/content_vector, a vectorizer, "
            "a semantic configuration and Search Index Data Reader access."
        ),
        "fixture_scoring": (
            "Lexical overlap over local notes is synthetic service "
            "metadata; no vector search or semantic ranker ran offline."
        ),
    }


async def run_ai_search_demo(
    *,
    execution: str = "offline",
    port: SearchPort | None = None,
    environ: Mapping[str, str] | None = None,
    live_port_factory: Callable[[str, str], SearchPort] = LiveSearchPort,
) -> DemoResult:
    """Retrieve grounding, rank citations and apply the approval gate.

    Args:
        execution: ``offline`` or ``live``.
        port: Optional retrieval boundary; overrides configuration.
        environ: Explicit environment for deterministic callers.
        live_port_factory: Injectable live adapter constructor.

    Returns:
        An honest result; an HTTP denial is a blocked live service.
    """
    if execution not in {"offline", "live"}:
        message = "execution must be offline or live."
        raise ValueError(message)
    settings = os.environ if environ is None else environ
    if port is None:
        if execution == "live":
            missing = [
                key
                for key in ("AZURE_SEARCH_ENDPOINT", "AZURE_SEARCH_INDEX")
                if not settings.get(key, "").strip()
            ]
            if missing:
                return missing_configuration(
                    demo=DEMO_NAME,
                    technology=TECHNOLOGY,
                    lane="current",
                    provider="azure-ai-search",
                    missing=missing,
                    next_steps=[f"Set {key}." for key in missing],
                )
            port = live_port_factory(
                settings["AZURE_SEARCH_ENDPOINT"],
                settings["AZURE_SEARCH_INDEX"],
            )
        else:
            port = FixtureSearchPort()
    request: SearchRequest = {
        "search_text": scenario.BRIEF,
        "vector_fields": "content_vector",
        "semantic_configuration_name": settings.get(
            "AZURE_SEARCH_SEMANTIC_CONFIGURATION", "workshop-semantic"
        ),
        "top": 3,
    }
    data = _payload(request)
    try:
        ranked = _rank(await port.search(request), request["top"])
    except ImportError:
        return result(
            demo=DEMO_NAME,
            technology=TECHNOLOGY,
            lane="current",
            mode="not_run",
            status="blocked",
            headline="The optional Search SDK is unavailable.",
            evidence=evidence(provider="azure-ai-search"),
            data=data,
            error={"code": "missing_sdk", "message": "Install Search SDK."},
            next_steps=["Run uv sync to install azure-search-documents."],
        )
    except (SearchError, TypeError, ValueError) as exc:
        code = (
            exc.code if isinstance(exc, SearchError) else "malformed_response"
        )
        return result(
            demo=DEMO_NAME,
            technology=TECHNOLOGY,
            lane="current",
            mode=(
                port.mode
                if port.mode == "local_contract" or port.network_attempted
                else "not_run"
            ),
            status="blocked" if code != "malformed_response" else "error",
            headline="Search could not supply trusted grounding.",
            evidence=evidence(
                provider="azure-ai-search",
                sdk_invoked=port.sdk_invoked,
                network_attempted=port.network_attempted,
                service_executed=port.service_executed,
                fixture_id=port.fixture_id,
            ),
            data=data,
            error={"code": code, "message": "Retrieval did not validate."},
            next_steps=["Check Search access, connectivity and index schema."],
        )
    cost = scenario.price_pilot()
    accepted, failures = scenario.proposal_is_acceptable(
        cost=cost, approved=False, cited_sources=[hit["id"] for hit in ranked]
    )
    data.update(
        citations=ranked,
        cost=cost,
        acceptable=accepted,
        acceptance_failures=failures,
        approval="pending",
    )
    return result(
        demo=DEMO_NAME,
        technology=TECHNOLOGY,
        lane="current",
        mode=port.mode,
        status="ok",
        headline="Grounding ranked and cited; pilot awaits human approval.",
        evidence=evidence(
            provider="azure-ai-search",
            sdk_invoked=port.sdk_invoked,
            network_attempted=port.network_attempted,
            service_executed=port.service_executed,
            fixture_id=port.fixture_id,
        ),
        data=data,
        next_steps=["Obtain named human approval before accepting the pilot."],
    )

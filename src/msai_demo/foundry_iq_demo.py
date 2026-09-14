"""Foundry IQ: the current serverless knowledge retrieval plane.

An agent asks one knowledge endpoint for grounded context and
citations. Foundry IQ integrates Work IQ, Fabric IQ, Azure SQL, file
search and MCP sources, with caller authorization enforced by the
service. This module tests an application contract, not a fabricated
SDK method or REST route. No service authorization runs offline.

Run it:

    uv run msai-demo foundry-iq
"""

from __future__ import annotations

from typing import Protocol, TypedDict
from urllib.parse import urlsplit

from msai_demo import scenario
from msai_demo.ai_search_demo import FixtureSearchPort, SearchRequest
from msai_demo.contracts import (
    DemoResult,
    evidence,
    missing_configuration,
    result,
)

DEMO_NAME = "foundry-iq"
TECHNOLOGY = "Microsoft Foundry IQ"
KNOWLEDGE_SOURCES = ("Work IQ", "Fabric IQ", "Azure SQL", "file search", "MCP")


class KnowledgeRequest(TypedDict):
    """Application contract for an agent's knowledge request.

    The caller context is a label, never a token or an authorization
    decision. A live integration must pass authenticated identity
    through the service's documented authentication mechanism.
    """

    question: str
    knowledge_sources: list[str]
    caller_context: str
    include_citations: bool


class KnowledgeCitation(TypedDict):
    """A source identifier and the passage returned as grounding."""

    id: str
    source: str
    quote: str


class KnowledgeResponse(TypedDict):
    """Grounded text plus citations at the application boundary."""

    context: str
    citation_ids: list[str]
    citations: list[KnowledgeCitation]


class KnowledgePort(Protocol):
    """The synthetic external response used to test the contract."""

    fixture_id: str

    async def retrieve(self, request: KnowledgeRequest) -> KnowledgeResponse:
        """Return context and citations for the agent's question."""
        raise NotImplementedError


class FixtureKnowledgePort:
    """Reuse real note passages as a synthetic Foundry IQ response."""

    fixture_id = "foundry-iq-v1"

    async def retrieve(self, request: KnowledgeRequest) -> KnowledgeResponse:
        """Ground the fixture in the notes without asserting access."""
        search_request: SearchRequest = {
            "search_text": request["question"],
            "vector_fields": "content_vector",
            "semantic_configuration_name": "workshop-semantic",
            "top": 3,
        }
        hits = await FixtureSearchPort().search(search_request)
        selected = [
            hit
            for hit in hits
            if hit["id"] in {"foundry-clients", "agents-vs-workflows"}
        ]
        return {
            "context": "\n\n".join(hit["content"] for hit in selected),
            "citation_ids": [hit["id"] for hit in selected],
            "citations": [
                {
                    "id": hit["id"],
                    "source": hit["source"],
                    "quote": hit["content"],
                }
                for hit in selected
            ],
        }


def _validate_citations(response: KnowledgeResponse) -> list[str]:
    """Reject dangling citations, unsafe URLs and invented quotes."""
    if (
        not isinstance(response["context"], str)
        or not isinstance(response["citation_ids"], list)
        or not isinstance(response["citations"], list)
    ):
        message = "Grounding needs text and lists of references and sources."
        raise TypeError(message)
    if not response["context"].strip() or not response["citation_ids"]:
        message = "Grounding requires context and citation references."
        raise ValueError(message)
    citations: dict[str, KnowledgeCitation] = {}
    for citation in response["citations"]:
        values = (citation["id"], citation["source"], citation["quote"])
        if not all(isinstance(value, str) for value in values):
            message = "Citation identifiers, URLs and quotes must be text."
            raise TypeError(message)
        identifier = citation["id"]
        parsed = urlsplit(citation["source"])
        if not identifier or identifier in citations:
            message = "Citation identifiers must be nonempty and unique."
            raise ValueError(message)
        if parsed.scheme != "https" or not parsed.netloc:
            message = "Citations require an HTTPS source URL."
            raise ValueError(message)
        if (
            not citation["quote"].strip()
            or citation["quote"] not in response["context"]
        ):
            message = "A cited quote must appear in the returned context."
            raise ValueError(message)
        citations[identifier] = citation
    cited = set(response["citation_ids"])
    if cited != set(citations):
        message = "Every reference and source must match without orphans."
        raise ValueError(message)
    return sorted(cited)


async def run_foundry_iq_demo(
    *,
    execution: str = "offline",
    port: KnowledgePort | None = None,
) -> DemoResult:
    """Validate the knowledge contract and keep acceptance gated.

    Args:
        execution: ``offline``; ``live`` reports missing integration.
        port: Optional synthetic response for contract testing.

    Returns:
        A local contract result that makes no service access claim.
    """
    if execution not in {"offline", "live"}:
        message = "execution must be offline or live."
        raise ValueError(message)
    if execution == "live":
        return missing_configuration(
            demo=DEMO_NAME,
            technology=TECHNOLOGY,
            lane="current",
            provider="foundry-iq",
            missing=["a provisioned knowledge endpoint and live adapter"],
            next_steps=[
                "Provision a Foundry IQ knowledge endpoint and its sources.",
                "Bind the documented service API with caller identity.",
                "Grant the caller access to the underlying knowledge.",
            ],
        )
    selected = FixtureKnowledgePort() if port is None else port
    request: KnowledgeRequest = {
        "question": scenario.BRIEF,
        "knowledge_sources": list(KNOWLEDGE_SOURCES),
        "caller_context": "synthetic-workshop-caller",
        "include_citations": True,
    }
    data: dict[str, object] = {
        "request": request,
        "contract_kind": "Application contract; not an SDK or REST schema.",
        "knowledge_sources": list(KNOWLEDGE_SOURCES),
        "service": (
            "Serverless knowledge and retrieval behind one SLA-backed "
            "endpoint; no SLA was exercised by this fixture."
        ),
        "comparison": {
            "ai_search": "An index your application builds and queries.",
            "foundry_iq": (
                "A knowledge endpoint an agent asks for grounded context "
                "and citations across connected sources."
            ),
        },
        "authorization": (
            "Per-user authorization is enforced by the service, not by "
            "your prompt. The fixture does not execute authorization."
        ),
        "validation_scope": (
            "Citation references, source URLs and quoted context; this "
            "does not prove factual entailment or caller access rights."
        ),
    }
    response = await selected.retrieve(request)
    try:
        cited_sources = _validate_citations(response)
    except (KeyError, TypeError, ValueError):
        return result(
            demo=DEMO_NAME,
            technology=TECHNOLOGY,
            lane="current",
            mode="local_contract",
            status="error",
            headline="The knowledge response failed citation validation.",
            evidence=evidence(
                provider="foundry-iq", fixture_id=selected.fixture_id
            ),
            data=data,
            error={
                "code": "malformed_response",
                "message": "Grounding must have valid matching citations.",
            },
            next_steps=["Repair the response before supplying agent context."],
        )
    cost = scenario.price_pilot()
    acceptable, failures = scenario.proposal_is_acceptable(
        cost=cost, approved=False, cited_sources=cited_sources
    )
    data.update(
        response=response,
        citations_valid=True,
        cost=cost,
        acceptable=acceptable,
        acceptance_failures=failures,
        approval="pending",
    )
    return result(
        demo=DEMO_NAME,
        technology=TECHNOLOGY,
        lane="current",
        mode="local_contract",
        status="ok",
        headline="Knowledge citations validated; human approval is pending.",
        evidence=evidence(
            provider="foundry-iq", fixture_id=selected.fixture_id
        ),
        data=data,
        next_steps=["Obtain named human approval before accepting the pilot."],
    )

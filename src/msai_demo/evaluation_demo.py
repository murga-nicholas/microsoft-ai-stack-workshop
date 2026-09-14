"""Current Foundry evaluations, with repeatable local quality gates.

Three proposals run through two ordinary Python evaluators. One bad
citation stays in the dataset deliberately: all-green examples cannot
demonstrate that a quality gate detects a regression.

Run it:

    uv run msai-demo evaluation
"""

from __future__ import annotations

import io
import json
import re
from contextlib import redirect_stdout
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import TYPE_CHECKING, Protocol, TypedDict

from pydantic import BaseModel, Field, StrictBool

from msai_demo import scenario
from msai_demo.contracts import (
    DemoResult,
    evidence,
    missing_configuration,
    result,
)
from msai_demo.runtime import REPO_ROOT

if TYPE_CHECKING:
    from collections.abc import Sequence

DEMO_NAME = "evaluation"
TECHNOLOGY = "Microsoft Foundry evaluations / azure-ai-evaluation"


@dataclass(frozen=True)
class EvaluationCase:
    """One input and its expected, deterministic acceptance criteria.

    Attributes:
        name: Stable dataset row identifier.
        question: Business question passed to the target.
        source: Source section the target will cite.
        required_terms: Terms the output must contain.
    """

    name: str
    question: str
    source: str
    required_terms: tuple[str, ...]


class EvaluationScore(TypedDict):
    """An evaluator's measured verdict and actionable explanation."""

    passed: bool
    missing: list[str]


class EvaluationPort(Protocol):
    """Supply the target output; evaluators remain application owned."""

    async def respond(self, case: EvaluationCase) -> str:
        """Return a proposal for one dataset row."""


class LocalEvaluationPort:
    """Execute the deterministic target without model inference."""

    async def respond(self, case: EvaluationCase) -> str:
        """Cost and cite the shared pilot for one dataset row."""
        return proposal_target(question=case.question, source=case.source)


class EvaluationRow(BaseModel):
    """Validate each SDK row before using it as evaluation evidence."""

    case: str = Field(alias="inputs.case")
    question: str = Field(alias="inputs.question")
    response: str = Field(alias="inputs.response")
    terms_passed: StrictBool = Field(alias="outputs.required_terms.passed")
    terms_missing: list[str] = Field(alias="outputs.required_terms.missing")
    sources_passed: StrictBool = Field(alias="outputs.source_sections.passed")
    sources_missing: list[str] = Field(alias="outputs.source_sections.missing")


class EvaluationBatch(BaseModel):
    """The verified portion of the SDK's evaluation result contract."""

    rows: list[EvaluationRow]
    metrics: dict[str, float]
    studio_url: str | None


class EvaluationBatchPort(Protocol):
    """Run a dataset through an evaluation engine."""

    sdk_invoked: bool

    def evaluate(self, data: Path) -> EvaluationBatch:
        """Evaluate the materialized JSONL and return validated rows."""


class AzureEvaluationBatchPort:
    """Execute the evaluation SDK without a model or project."""

    sdk_invoked = False

    def evaluate(self, data: Path) -> EvaluationBatch:
        """Call the installed SDK's threaded callable-evaluator path.

        Version 1.18.5 selects CodeClient with these two compatibility
        kwargs. They avoid Windows process-worker startup timeouts;
        evaluate still owns loading, execution and metric aggregation.
        No project, grader, target model or exporter is configured.
        """
        from azure.ai.evaluation import evaluate

        # SDK progress must not corrupt the CLI's JSON document.
        with redirect_stdout(io.StringIO()):
            evaluated = evaluate(
                data=str(data),
                evaluators={
                    "required_terms": evaluate_required_terms,
                    "source_sections": evaluate_source_sections,
                },
                _use_run_submitter_client=False,
                _use_pf_client=False,
            )
        self.sdk_invoked = True
        return EvaluationBatch.model_validate(evaluated)


def proposal_target(*, question: str, source: str) -> str:
    """Produce a costed answer with an explicit source citation.

    Args:
        question: Dataset input, retained to make the target auditable.
        source: Corpus section to cite, possibly deliberately invalid.

    Returns:
        A proposal requiring human approval before acceptance.
    """
    cost = scenario.price_pilot()
    return (
        f"{question}\nA {cost['weeks']}-week customer-support pilot costs "
        f"{cost['total']} USD against a {cost['budget']} USD budget. "
        "Human approval is required before acceptance. "
        f"Source: {source}"
    )


def evaluate_required_terms(
    *, response: str, required_terms: Sequence[str]
) -> EvaluationScore:
    """Check required terms without asking a model to grade itself.

    Args:
        response: Target output to inspect.
        required_terms: Case-insensitive phrases required by the case.

    Returns:
        Verdict and every missing phrase.
    """
    missing = [
        term
        for term in required_terms
        if term.casefold() not in response.casefold()
    ]
    return {"passed": not missing, "missing": missing}


def evaluate_source_sections(
    *, response: str, sections: Sequence[str] | frozenset[str]
) -> EvaluationScore:
    """Require at least one citation and resolve every cited section.

    Args:
        response: Text containing ``Source: section-name`` citations.
        sections: Section identifiers read from the repository corpus.

    Returns:
        Verdict and unresolved citations, including absent citations.
    """
    citations = re.findall(r"Source:\s*([\w-]+)", response)
    if not citations:
        return {"passed": False, "missing": ["No source section cited."]}
    missing = sorted(set(citations) - frozenset(sections))
    return {"passed": not missing, "missing": missing}


def evaluation_dataset() -> tuple[EvaluationCase, ...]:
    """Build three business cases, including an invented citation."""
    terms = ("customer-support", "budget", "human approval")
    return (
        EvaluationCase(
            "costed-pilot", scenario.BRIEF, "agent-framework-overview", terms
        ),
        EvaluationCase(
            "approval-gate",
            "Explain the acceptance gate.",
            "guardrails",
            terms,
        ),
        EvaluationCase(
            "invented-source",
            "Explain the delivery proposal.",
            "nonexistent-pilot-guarantee",
            terms,
        ),
    )


def _cloud_recipe() -> dict[str, object]:
    """Describe verified SDK entry points without inventing methods."""
    return {
        "requested_api": "AIProjectClient.evaluations",
        "installed_api_note": (
            "azure-ai-projects 2.6.0 exposes evaluation_rules, not an "
            "evaluations operation group. Do not call a nonexistent method."
        ),
        "verified_api": "AIProjectClient.get_openai_client().evals",
        "steps": [
            "Provision a Foundry project and grant the caller access.",
            "Materialize these same rows with proposal_target outputs.",
            "Upload JSONL with one {item: row} object per line.",
            "Create an eval with evals.create(data_source_config=..., "
            "testing_criteria=...).",
            "Submit the file with evals.runs.create(eval_id, "
            "data_source={type: jsonl, source: {type: file_id, id: ...}}).",
        ],
        "local_sdk_recipe": (
            "azure.ai.evaluation.evaluate(data='cases.jsonl', "
            "evaluators={...})"
        ),
        "local_sdk_facts": (
            "Installed evaluate accepts custom callable evaluators and "
            "does not require model configuration for deterministic checks. "
            "This runner selects its threaded CodeClient with the verified "
            "1.18.5 compatibility kwargs _use_run_submitter_client=False "
            "and _use_pf_client=False. The default process batch workers "
            "previously timed out on this Windows environment."
        ),
        "judge": (
            "A model-graded judge is a separate, paid, non-deterministic "
            "evaluation requiring a deployed model and resource access."
        ),
        "submitted": False,
    }


async def run_evaluation_demo(
    *,
    execution: str = "offline",
    port: EvaluationPort | None = None,
    corpus_path: Path | None = None,
    batch_port: EvaluationBatchPort | None = None,
) -> DemoResult:
    """Execute local evaluators and preserve the intentional failure.

    Args:
        execution: ``offline`` runs locally; cloud work needs a project.
        port: Optional target implementation, injected by tests.
        corpus_path: Optional test corpus.
        batch_port: Optional evaluation engine, injected by tests.

    Returns:
        Actual case scores, including the deliberate failing case.
    """
    if execution != "offline":
        return missing_configuration(
            demo=DEMO_NAME,
            technology=TECHNOLOGY,
            lane="current",
            provider="foundry-evaluations",
            missing=["configured Foundry evaluation submission"],
            next_steps=["Follow data.cloud_submission from the offline run."],
        )
    path = corpus_path or REPO_ROOT / "data" / "microsoft_ai_stack_notes.md"
    sections = frozenset(
        re.findall(
            r"^## Section:\s*(\S+)\s*$", path.read_text(encoding="utf-8"), re.M
        )
    )
    if not sections:
        message = "The evaluation corpus contains no named sections."
        raise ValueError(message)
    engine = batch_port or AzureEvaluationBatchPort()
    dataset = await _materialize_cases(port or LocalEvaluationPort(), sections)
    with TemporaryDirectory(prefix="msai-evaluation-") as directory:
        data_path = Path(directory) / "cases.jsonl"
        data_path.write_text(
            "".join(json.dumps(row) + "\n" for row in dataset),
            encoding="utf-8",
        )
        try:
            evaluated = engine.evaluate(data_path)
        except ImportError:
            return _missing_sdk_result(dataset)
    rows = [_result_row(row) for row in evaluated.rows]
    if [row.case for row in evaluated.rows] != [
        case.name for case in evaluation_dataset()
    ]:
        message = "The SDK did not return every evaluation case in order."
        raise ValueError(message)
    failures = sum(not row["passed"] for row in rows)
    return result(
        demo=DEMO_NAME,
        technology=TECHNOLOGY,
        lane="current",
        mode="local_execution",
        status="ok",
        headline=(
            f"Evaluated {len(rows)} proposals; "
            f"{failures} failed quality gates."
        ),
        evidence=evidence(
            provider="azure-ai-evaluation",
            sdk_invoked=engine.sdk_invoked,
        ),
        data={
            "scenario_id": scenario.SCENARIO_ID,
            "cost": scenario.price_pilot(),
            "api_path": (
                "azure.ai.evaluation.evaluate(data=..., evaluators=...)"
            ),
            "sdk_metrics": evaluated.metrics,
            "rows": rows,
            "failed_cases": failures,
            "suite_passed": failures == 0,
            "intentional_failure": (
                "invented-source cites a section absent from the corpus. "
                "An evaluation that only shows green is a dashboard, "
                "not a test."
            ),
            "limitation": (
                "Term presence and citation existence do not prove that a "
                "source supports the answer or that the answer is correct."
            ),
            "cloud_submission": _cloud_recipe(),
        },
    )


async def _materialize_cases(
    target: EvaluationPort, sections: frozenset[str]
) -> list[dict[str, object]]:
    """Write target outputs before the SDK scores the JSONL dataset."""
    return [
        {
            "case": case.name,
            "question": case.question,
            "response": await target.respond(case),
            "required_terms": list(case.required_terms),
            "sections": sorted(sections),
        }
        for case in evaluation_dataset()
    ]


def _result_row(row: EvaluationRow) -> dict[str, object]:
    """Expose scores returned by the SDK, without recomputing them."""
    return {
        "case": row.case,
        "question": row.question,
        "response": row.response,
        "required_terms": {
            "passed": row.terms_passed,
            "missing": row.terms_missing,
        },
        "source_sections": {
            "passed": row.sources_passed,
            "missing": row.sources_missing,
        },
        "passed": row.terms_passed and row.sources_passed,
    }


def _missing_sdk_result(dataset: list[dict[str, object]]) -> DemoResult:
    """Keep prepared cases available without claiming SDK execution."""
    return result(
        demo=DEMO_NAME,
        technology=TECHNOLOGY,
        lane="current",
        mode="local_execution",
        status="blocked",
        headline="Prepared evaluation cases; azure-ai-evaluation is absent.",
        evidence=evidence(provider="deterministic-python"),
        data={"prepared_cases": dataset, "cost": scenario.price_pilot()},
        error={
            "code": "missing_sdk",
            "message": "Install azure-ai-evaluation to execute the cases.",
        },
        next_steps=["Run uv sync, then rerun msai-demo evaluation."],
    )

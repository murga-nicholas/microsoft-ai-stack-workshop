from __future__ import annotations

import asyncio
import json
import sys
from typing import TYPE_CHECKING

import pytest

from msai_demo import evaluation_demo as demo
from msai_demo import scenario

if TYPE_CHECKING:
    from pathlib import Path


class TargetPort:
    def __init__(self, response: str) -> None:
        self.response = response

    async def respond(self, case: demo.EvaluationCase) -> str:
        assert case.name
        return self.response


def test_real_local_evaluators_keep_the_regression_visible() -> None:
    guard = {"enabled": False}
    network_attempts: list[str] = []

    def reject_network(event: str, arguments: tuple[object, ...]) -> None:
        del arguments
        if guard["enabled"] and event in {
            "socket.connect",
            "socket.getaddrinfo",
            "socket.gethostbyname",
        }:
            network_attempts.append(event)
            message = "The local evaluator attempted network access."
            raise RuntimeError(message)

    # Audit hooks observe real socket operations, including SDK threads.
    sys.addaudithook(reject_network)

    async def guarded_run() -> demo.DemoResult:
        # Windows creates loopback sockets while initializing asyncio.
        # Observe the SDK after asyncio initializes its local sockets.
        guard["enabled"] = True
        try:
            return await demo.run_evaluation_demo()
        finally:
            guard["enabled"] = False

    result = asyncio.run(guarded_run())
    assert network_attempts == []
    assert result["mode"] == "local_execution"
    assert result["status"] == "ok"
    assert result["evidence"]["network_attempted"] is False
    assert result["evidence"]["sdk_invoked"] is True
    data = result["data"]
    assert data is not None
    assert data["failed_cases"] == 1
    assert data["suite_passed"] is False
    assert data["cost"] == scenario.price_pilot()
    assert [row["passed"] for row in data["rows"]] == [True, True, False]
    assert data["rows"][-1]["source_sections"]["missing"] == [
        "nonexistent-pilot-guarantee"
    ]
    assert data["cloud_submission"]["submitted"] is False
    assert data["sdk_metrics"]["required_terms.passed"] == 1.0
    assert data["sdk_metrics"]["source_sections.passed"] == pytest.approx(
        2 / 3
    )
    assert (
        "not an evaluations operation group"
        in data["cloud_submission"]["installed_api_note"]
    )


def test_term_checker_explains_missing_phrases() -> None:
    assert demo.evaluate_required_terms(
        response="Human APPROVAL", required_terms=["approval", "budget"]
    ) == {"passed": False, "missing": ["budget"]}


@pytest.mark.parametrize(
    ("response", "expected"),
    [
        ("No citation.", ["No source section cited."]),
        ("Source: known\nSource: invented", ["invented"]),
        ("Source: known\nSource: known", []),
    ],
)
def test_source_checker_requires_every_citation(
    response: str, expected: list[str]
) -> None:
    score = demo.evaluate_source_sections(
        response=response, sections=frozenset({"known"})
    )
    assert score == {"passed": not expected, "missing": expected}


def test_injected_target_can_fail_every_case() -> None:
    result = asyncio.run(
        demo.run_evaluation_demo(port=TargetPort("Source: guardrails"))
    )
    assert result["data"] is not None
    assert result["data"]["failed_cases"] == 3


def test_injected_target_can_pass_every_case() -> None:
    result = asyncio.run(
        demo.run_evaluation_demo(
            port=TargetPort(
                "Customer-support budget human approval. Source: guardrails"
            )
        )
    )
    assert result["data"] is not None
    assert result["data"]["suite_passed"] is True


def test_empty_corpus_is_an_error(tmp_path: Path) -> None:
    corpus = tmp_path / "empty.md"
    corpus.write_text("No sections.", encoding="utf-8")
    with pytest.raises(ValueError, match="no named sections"):
        asyncio.run(demo.run_evaluation_demo(corpus_path=corpus))


def test_live_submission_stops_without_a_configured_adapter() -> None:
    result = asyncio.run(demo.run_evaluation_demo(execution="live"))
    assert result["mode"] == "not_run"
    assert result["error"] is not None
    assert result["error"]["code"] == "missing_configuration"
    assert result["evidence"]["network_attempted"] is False


class MissingSdkPort:
    sdk_invoked = False

    def __init__(self) -> None:
        self.path: Path | None = None

    def evaluate(self, data: Path) -> demo.EvaluationBatch:
        self.path = data
        rows = [json.loads(line) for line in data.read_text().splitlines()]
        assert [row["case"] for row in rows] == [
            case.name for case in demo.evaluation_dataset()
        ]
        assert all(row["response"] and row["sections"] for row in rows)
        raise ImportError


def test_missing_sdk_reports_prepared_cases_without_sdk_evidence() -> None:
    engine = MissingSdkPort()
    result = asyncio.run(demo.run_evaluation_demo(batch_port=engine))
    assert result["status"] == "blocked"
    assert result["evidence"]["sdk_invoked"] is False
    assert result["error"] is not None
    assert result["error"]["code"] == "missing_sdk"
    assert result["data"] is not None
    assert len(result["data"]["prepared_cases"]) == 3
    assert engine.path is not None
    assert not engine.path.exists()


class EmptyBatchPort:
    sdk_invoked = False

    def evaluate(self, data: Path) -> demo.EvaluationBatch:
        assert data.is_file()
        return demo.EvaluationBatch(rows=[], metrics={}, studio_url=None)


def test_missing_sdk_rows_cannot_become_a_successful_suite() -> None:
    with pytest.raises(ValueError, match="every evaluation case"):
        asyncio.run(demo.run_evaluation_demo(batch_port=EmptyBatchPort()))


def test_malformed_sdk_score_is_rejected_before_reporting_success() -> None:
    with pytest.raises(ValueError, match=r"source_sections\.passed"):
        demo.EvaluationBatch.model_validate(
            {
                "rows": [
                    {
                        "inputs.case": "costed-pilot",
                        "inputs.question": scenario.BRIEF,
                        "inputs.response": "bad response",
                        "outputs.required_terms.passed": True,
                        "outputs.required_terms.missing": [],
                        "outputs.source_sections.passed": "not a verdict",
                        "outputs.source_sections.missing": [],
                    }
                ],
                "metrics": {},
                "studio_url": None,
            }
        )

from __future__ import annotations

import asyncio

import pytest

from msai_demo import scenario
from msai_demo.promptflow_demo import (
    FLOW_DAG,
    FlowOutputs,
    LocalFlowPort,
    build_prompt_node,
    run_promptflow_demo,
    score_proposal_node,
)


class RecordingFlow:
    def __init__(self, *, corrupt_score: bool = False) -> None:
        self.inputs: list[dict[str, str]] = []
        self.corrupt_score = corrupt_score

    async def run(self, inputs: dict[str, str]) -> FlowOutputs:
        self.inputs.append(dict(inputs))
        outputs = await LocalFlowPort().run(inputs)
        if self.corrupt_score:
            outputs["score_proposal"]["acceptable"] = True
        return outputs


def test_offline_runner_executes_two_nodes_and_preserves_approval_gate() -> (
    None
):
    report = asyncio.run(run_promptflow_demo())
    assert report["mode"] == "local_execution"
    assert report["status"] == "ok"
    assert not report["evidence"]["sdk_invoked"]
    assert not report["evidence"]["network_attempted"]
    assert not report["evidence"]["service_executed"]
    assert report["evidence"]["fixture_id"] is None
    data = report["data"]
    assert data is not None
    outputs = data["node_outputs"]
    assert outputs["build_prompt"]["cost"] == scenario.price_pilot()
    assert outputs["score_proposal"] == {
        "acceptable": False,
        "failures": ["No human approval recorded."],
        "within_budget": True,
        "human_approved": False,
        "grounded": True,
    }
    assert data["flow_dag"]["nodes"] == FLOW_DAG
    conflict = data["dependency_conflict"]
    assert conflict["pin"] == "opentelemetry-sdk>=1.22,<1.39"
    assert conflict["current_requirement"] == "opentelemetry-api>=1.39"
    assert set(data["replacement"].values()) == {
        "Foundry evaluations",
        "Foundry observability",
    }


def test_prompt_node_uses_input_and_scenario_arithmetic() -> None:
    draft = build_prompt_node("A task passed through a DAG binding.")
    assert draft["prompt"].startswith("A task passed through a DAG binding.")
    assert str(scenario.price_pilot()["total"]) in draft["prompt"]
    assert draft["cited_sources"] == [scenario.SCENARIO_ID]
    assert not draft["approved"]


@pytest.mark.parametrize("brief", ["", "  "])
def test_prompt_node_rejects_blank_input(brief: str) -> None:
    with pytest.raises(ValueError, match="nonblank brief"):
        build_prompt_node(brief)


def test_score_consumes_upstream_facts_instead_of_recomputing_defaults() -> (
    None
):
    draft = build_prompt_node(scenario.BRIEF)
    draft["cost"] = scenario.price_pilot(budget=1)
    draft["cited_sources"] = []
    draft["approved"] = True
    score = score_proposal_node(draft)
    assert not score["acceptable"]
    assert not score["within_budget"]
    assert score["human_approved"]
    assert not score["grounded"]
    assert len(score["failures"]) == 2


def test_score_accepts_costed_grounded_human_approved_proposal() -> None:
    draft = build_prompt_node(scenario.BRIEF)
    draft["approved"] = True
    score = score_proposal_node(draft)
    assert score["acceptable"]
    assert score["failures"] == []


def test_local_dag_resolves_custom_input() -> None:
    outputs = asyncio.run(LocalFlowPort().run({"brief": "Custom input"}))
    assert outputs["build_prompt"]["prompt"].startswith("Custom input")
    assert outputs["score_proposal"] == score_proposal_node(
        outputs["build_prompt"]
    )


def test_runner_accepts_injected_flow() -> None:
    port = RecordingFlow()
    report = asyncio.run(run_promptflow_demo(port=port))
    assert report["status"] == "ok"
    assert port.inputs == [{"brief": scenario.BRIEF}]


def test_runner_rejects_a_fabricated_score() -> None:
    with pytest.raises(ValueError, match="contradicts"):
        asyncio.run(
            run_promptflow_demo(port=RecordingFlow(corrupt_score=True))
        )


def test_live_requires_configuration_before_executing_nodes() -> None:
    port = RecordingFlow()
    report = asyncio.run(run_promptflow_demo(execution="live", port=port))
    assert report["mode"] == "not_run"
    assert report["error"] is not None
    assert report["error"]["code"] == "missing_configuration"
    assert not report["evidence"]["network_attempted"]
    assert port.inputs == []


def test_invalid_execution_is_rejected() -> None:
    with pytest.raises(ValueError, match="execution"):
        asyncio.run(run_promptflow_demo(execution="typo"))


def test_unexpected_node_failure_is_not_manufactured_success() -> None:
    class BrokenFlow:
        async def run(self, inputs: dict[str, str]) -> FlowOutputs:
            del inputs
            message = "node bug"
            raise RuntimeError(message)

    with pytest.raises(RuntimeError, match="node bug"):
        asyncio.run(run_promptflow_demo(port=BrokenFlow()))

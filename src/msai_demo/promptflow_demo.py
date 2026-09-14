"""Prompt flow: execute two Python nodes, then name the current path.

Prompt flow 1.18.5 is the legacy authoring and evaluation lane.
Its tracing dependency caps OpenTelemetry below the version required
by Agent Framework. This module executes the same small DAG as plain
Python, with no promptflow import and no model-generated score.

Foundry evaluations and Foundry observability bring evaluation and
tracing into the current control plane.

Run it:

    uv run msai-demo promptflow
"""

from __future__ import annotations

from typing import Protocol, TypedDict

from msai_demo import scenario
from msai_demo.contracts import (
    DemoResult,
    evidence,
    missing_configuration,
    result,
)

DEMO_NAME = "promptflow"
TECHNOLOGY = "promptflow 1.18.5 (legacy authoring and evaluation)"

# The same references drive execution and appear in the slide's DAG.
FLOW_DAG: dict[str, dict[str, str]] = {
    "build_prompt": {"brief": "inputs.brief"},
    "score_proposal": {"draft": "build_prompt.output"},
}


class PromptDraft(TypedDict):
    """A deterministic prompt and the facts used to build it."""

    prompt: str
    cost: scenario.PilotCost
    approved: bool
    cited_sources: list[str]


class ProposalScore(TypedDict):
    """Executed acceptance checks, without an invented model score."""

    acceptable: bool
    failures: list[str]
    within_budget: bool
    human_approved: bool
    grounded: bool


class FlowOutputs(TypedDict):
    """The two materialized node outputs in dependency order."""

    build_prompt: PromptDraft
    score_proposal: ProposalScore


class FlowPort(Protocol):
    """The local flow execution boundary, replaceable in tests."""

    async def run(self, inputs: dict[str, str]) -> FlowOutputs:
        """Execute the two-node DAG with the supplied flow inputs."""


def build_prompt_node(brief: str) -> PromptDraft:
    """Build a prompt using deterministic scenario costing.

    Args:
        brief: Business task passed in through the flow's inputs.

    Returns:
        Prompt text and facts consumed by the downstream scorer.

    Raises:
        ValueError: If the flow supplies a blank brief.
    """
    if not brief.strip():
        message = "The prompt-builder node needs a nonblank brief."
        raise ValueError(message)
    cost = scenario.price_pilot()
    return {
        "prompt": (
            f"{brief}\n"
            f"Verified cost: {cost['total']} USD; "
            f"budget: {cost['budget']} USD.\n"
            f"Source: {scenario.SCENARIO_ID}.\n"
            "Draft a proposal; do not accept work before human approval."
        ),
        "cost": cost,
        "approved": False,
        "cited_sources": [scenario.SCENARIO_ID],
    }


def score_proposal_node(draft: PromptDraft) -> ProposalScore:
    """Apply the shared acceptance rules to the previous node's facts.

    Args:
        draft: Structured output from the prompt-builder node.

    Returns:
        Boolean checks and explicit failures. This is a deterministic
        business-rule score; no LLM judges quality or grounding.
    """
    acceptable, failures = scenario.proposal_is_acceptable(
        cost=draft["cost"],
        approved=draft["approved"],
        cited_sources=draft["cited_sources"],
    )
    return {
        "acceptable": acceptable,
        "failures": failures,
        "within_budget": draft["cost"]["within_budget"],
        "human_approved": draft["approved"],
        "grounded": bool(draft["cited_sources"]),
    }


class LocalFlowPort:
    """Run the DAG bindings and node bodies as ordinary Python."""

    async def run(self, inputs: dict[str, str]) -> FlowOutputs:
        """Resolve the prompt input, then feed its output to scoring."""
        input_values = {"inputs.brief": inputs["brief"]}
        prompt_bindings = FLOW_DAG["build_prompt"]
        draft = build_prompt_node(input_values[prompt_bindings["brief"]])

        # A node consumes the upstream output, not another copy of
        # the scenario. Changing the binding changes the data flow.
        node_values = {"build_prompt.output": draft}
        score_bindings = FLOW_DAG["score_proposal"]
        score = score_proposal_node(node_values[score_bindings["draft"]])
        return {"build_prompt": draft, "score_proposal": score}


async def run_promptflow_demo(
    *,
    execution: str = "offline",
    port: FlowPort | None = None,
) -> DemoResult:
    """Execute the local DAG and explain the tracing dependency split.

    Args:
        execution: ``offline`` executes Python nodes. ``live`` reports
            the missing isolated prompt flow environment.
        port: Optional local flow executor for deterministic tests.

    Returns:
        Actual node outputs, their input bindings and the migration
        to Foundry evaluations and observability.

    Raises:
        ValueError: If execution is unknown or the injected flow
            returns a score inconsistent with the proposal facts.
    """
    if execution not in {"offline", "live"}:
        message = "execution must be 'offline' or 'live'."
        raise ValueError(message)
    if execution == "live":
        return missing_configuration(
            demo=DEMO_NAME,
            technology=TECHNOLOGY,
            lane="legacy",
            provider="promptflow",
            missing=["an isolated prompt flow environment and model endpoint"],
            next_steps=[
                "Use Foundry evaluations and observability in this repo.",
                "Isolate prompt flow if maintaining an existing flow.",
            ],
        )
    flow = port if port is not None else LocalFlowPort()
    inputs = {"brief": scenario.BRIEF}
    outputs = await flow.run(inputs)
    if outputs["score_proposal"] != score_proposal_node(
        outputs["build_prompt"]
    ):
        message = "The scoring node output contradicts its input facts."
        raise ValueError(message)
    return result(
        demo=DEMO_NAME,
        technology=TECHNOLOGY,
        lane="legacy",
        mode="local_execution",
        status="ok",
        headline=(
            "Two Python nodes ran through real bindings and checked "
            "cost, grounding and human approval."
        ),
        evidence=evidence(provider="local-python"),
        data={
            "scenario_id": scenario.SCENARIO_ID,
            "flow_dag": {
                "inputs": inputs,
                "nodes": FLOW_DAG,
                "outputs": {"score": "score_proposal.output"},
            },
            "node_outputs": outputs,
            "dependency_conflict": {
                "package": "promptflow-tracing 1.18.5",
                "pin": "opentelemetry-sdk>=1.22,<1.39",
                "current_requirement": "opentelemetry-api>=1.39",
                "required_by": "agent-framework-core",
                "reason": (
                    "OpenTelemetry SDK releases require their matching "
                    "API version, so these constraints cannot coexist."
                ),
            },
            "replacement": {
                "prompt flow evaluation": "Foundry evaluations",
                "prompt flow tracing": "Foundry observability",
            },
            "why_migrate": (
                "Evaluation and tracing are integrated in the Foundry "
                "control plane without the legacy OpenTelemetry cap."
            ),
            "limitations": (
                "Python DAG execution only; no promptflow SDK, model "
                "inference, LLM judging or service tracing was invoked."
            ),
        },
    )

"""Foundry guardrails: current policy at four intervention points.

The policy evaluator and pre-tool gate execute locally. Risk signals
are synthetic; Foundry's classification and service enforcement are
not invoked. Tool-call and tool-response interception are preview.

Run it:

    uv run msai-demo foundry-guardrails
    uv run msai-demo foundry-guardrails --execution live
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, Protocol, TypedDict

from msai_demo import scenario
from msai_demo.contracts import (
    DemoResult,
    evidence,
    missing_configuration,
    result,
)

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from msai_demo.scenario import PilotCost

Point = Literal["user_input", "tool_call", "tool_response", "output"]
Action = Literal["allow", "annotate", "block"]
DEMO_NAME = "foundry-guardrails"
TECHNOLOGY = "Microsoft Foundry guardrails and controls"
FIXTURE_ID = "foundry-guardrails-v1"
POINTS: tuple[Point, ...] = (
    "user_input",
    "tool_call",
    "tool_response",
    "output",
)
PRIORITY: dict[Action, int] = {"allow": 0, "annotate": 1, "block": 2}


@dataclass(frozen=True)
class Control:
    """One workshop policy rule, not a Foundry SDK request model.

    Attributes:
        name: Human-readable control identifier.
        risk: Signal this control reacts to.
        points: Intervention points at which the risk is scanned.
        action: Decision when the risk is present.
    """

    name: str
    risk: str
    points: tuple[Point, ...]
    action: Action


class Decision(TypedDict):
    """The strongest matching action at one intervention point.

    Attributes:
        point: Where evaluation took place.
        action: Allow, annotate or block, with block taking priority.
        matched_controls: Controls whose signals actually matched.
    """

    point: Point
    action: Action
    matched_controls: list[str]


class _CaseResult(TypedDict):
    """Policy decisions and observed action execution for one case."""

    case: str
    cost: PilotCost
    human_approval: bool
    signals: dict[Point, list[str]]
    decisions: list[Decision]
    acceptance_failures: list[str]
    acceptable: bool
    blocked: bool
    accept_proposal_executed: bool
    receipt: str | None


POLICY: tuple[Control, ...] = (
    Control("Stop prompt attacks", "prompt_injection", POINTS, "block"),
    Control("Keep budget", "over_budget", ("tool_call",), "block"),
    Control("Require approval", "approval_missing", ("tool_call",), "block"),
    Control("Require grounding", "grounding_missing", ("tool_call",), "block"),
    Control(
        "Mark untrusted tool content",
        "untrusted_source",
        ("tool_response",),
        "annotate",
    ),
    Control(
        "Disclose estimates", "illustrative_cost", ("output",), "annotate"
    ),
)


class GuardrailsPort(Protocol):
    """Supply fixture signals and an observable acceptance action."""

    async def read_signals(self) -> Mapping[Point, frozenset[str]]:
        """Return synthetic detector output at the four boundaries."""

    async def accept_proposal(self, scenario_id: str) -> str:
        """Record a local acceptance only after every gate passes."""


class FixtureGuardrailsPort:
    """Replay declared detector signals without calling Foundry."""

    async def read_signals(self) -> Mapping[Point, frozenset[str]]:
        """Mark tool content and illustrative costing for annotation."""
        return {
            "user_input": frozenset(),
            "tool_call": frozenset(),
            "tool_response": frozenset({"untrusted_source"}),
            "output": frozenset({"illustrative_cost"}),
        }

    async def accept_proposal(self, scenario_id: str) -> str:
        """Return a local receipt without delivery or billing."""
        return f"accepted::{scenario_id}"


def evaluate_policy(
    policy: Sequence[Control],
    signals: Mapping[Point, frozenset[str]],
) -> list[Decision]:
    """Evaluate every point, with block taking precedence over annotate.

    Args:
        policy: Controls naming a risk, intervention points and action.
        signals: Present risks; absent points have no detected signals.

    Returns:
        Ordered decisions for the four intervention points.

    Raises:
        ValueError: If a control or intervention point is malformed.
    """
    if set(signals) - set(POINTS):
        message = "Signals contain an unknown intervention point."
        raise ValueError(message)
    for control in policy:
        if (
            not control.name.strip()
            or not control.risk.strip()
            or not control.points
            or set(control.points) - set(POINTS)
            or control.action not in PRIORITY
        ):
            message = "Each control needs a name, risk, points and action."
            raise ValueError(message)
    decisions: list[Decision] = []
    for point in POINTS:
        matches = [
            control
            for control in policy
            if point in control.points
            and control.risk in signals.get(point, frozenset())
        ]
        default_action: Action = "allow"
        action: Action = max(
            (control.action for control in matches),
            key=PRIORITY.__getitem__,
            default=default_action,
        )
        decisions.append(
            {
                "point": point,
                "action": action,
                "matched_controls": [control.name for control in matches],
            }
        )
    return decisions


async def _evaluate_case(
    *,
    name: str,
    cost: PilotCost,
    approved: bool,
    signals: Mapping[Point, frozenset[str]],
    port: GuardrailsPort,
    policy: Sequence[Control],
) -> _CaseResult:
    """Compute business signals before considering acceptance."""
    risks = set(signals.get("tool_call", frozenset()))
    if not cost["within_budget"]:
        risks.add("over_budget")
    if not approved:
        risks.add("approval_missing")
    acceptable, reasons = scenario.proposal_is_acceptable(
        cost=cost,
        approved=approved,
        cited_sources=["agent-framework-overview"],
    )
    case_signals = dict(signals)
    case_signals["tool_call"] = frozenset(risks)
    decisions = evaluate_policy(policy, case_signals)
    blocked = any(decision["action"] == "block" for decision in decisions)
    receipt: str | None = None
    if not blocked and acceptable:
        # A missing policy rule is a demo failure, never permission
        # to bypass the shared budget and human-approval requirements.
        receipt = await port.accept_proposal(scenario.SCENARIO_ID)
    return {
        "case": name,
        "cost": cost,
        "human_approval": approved,
        "signals": {
            point: sorted(risks) for point, risks in case_signals.items()
        },
        "decisions": decisions,
        "acceptance_failures": reasons,
        "acceptable": acceptable,
        "blocked": blocked,
        "accept_proposal_executed": receipt is not None,
        "receipt": receipt,
    }


async def run_foundry_guardrails_demo(
    *,
    execution: str = "offline",
    port: GuardrailsPort | None = None,
    approve: bool = False,
    policy: Sequence[Control] = POLICY,
) -> DemoResult:
    """Run the policy on standard and over-budget support proposals.

    Args:
        execution: ``offline`` or ``live``; live is not deployed here.
        port: Optional synthetic signals and local acceptance recorder.
        approve: Explicit workshop human decision, false by default.
        policy: Controls evaluated against the shared acceptance rules.

    Returns:
        Decisions and evidence that blocked tool calls never executed.

    Raises:
        ValueError: If execution is neither offline nor live.
    """
    if execution not in {"offline", "live"}:
        message = "execution must be 'offline' or 'live'."
        raise ValueError(message)
    if execution == "live":
        return missing_configuration(
            demo=DEMO_NAME,
            technology=TECHNOLOGY,
            lane="current",
            provider="foundry-guardrails",
            missing=["Foundry project, deployed guardrail and permissions"],
            next_steps=[
                "Create a Foundry guardrail and bind it to the agent.",
                "Enable preview tool-call and tool-response interception.",
            ],
        )
    adapter = port if port is not None else FixtureGuardrailsPort()
    try:
        signals = await adapter.read_signals()
        cases = []
        for name, cost in (
            ("standard", scenario.price_pilot()),
            (
                "over_budget",
                scenario.price_pilot(
                    team=dict.fromkeys(scenario.rate_card(), 1.0)
                ),
            ),
        ):
            cases.append(
                await _evaluate_case(
                    name=name,
                    cost=cost,
                    approved=approve,
                    signals=signals,
                    port=adapter,
                    policy=policy,
                )
            )
    except (PermissionError, ValueError) as exc:
        denied = isinstance(exc, PermissionError)
        return result(
            demo=DEMO_NAME,
            technology=TECHNOLOGY,
            lane="current",
            mode="local_contract",
            status="blocked" if denied else "error",
            headline="The local guardrail contract could not run.",
            evidence=evidence(
                provider="foundry-guardrails", fixture_id=FIXTURE_ID
            ),
            error={
                "code": "authorization_denied" if denied else "malformed",
                "message": "Synthetic guardrail signals or access failed.",
            },
        )
    failed_count = sum(
        not case["acceptable"] and not case["blocked"] for case in cases
    )
    blocked_points = Counter(
        decision["point"]
        for case in cases
        for decision in case["decisions"]
        if decision["action"] == "block"
    )
    block_summary = ", ".join(
        f"{count} at {point}" for point, count in blocked_points.items()
    )
    return result(
        demo=DEMO_NAME,
        technology=TECHNOLOGY,
        lane="current",
        mode="local_contract",
        status="error" if failed_count else "ok",
        headline=(
            f"The policy missed {failed_count} required acceptance blocks."
            if failed_count
            else f"Evaluated {len(cases)} cases; blocks: {block_summary}."
        ),
        evidence=evidence(
            provider="foundry-guardrails", fixture_id=FIXTURE_ID
        ),
        error=(
            {
                "code": "policy_failed",
                "message": (
                    "The policy allowed a proposal that failed the "
                    "acceptance rules; the application refused acceptance."
                ),
            }
            if failed_count
            else None
        ),
        data={
            "scenario_id": scenario.SCENARIO_ID,
            "scenario": scenario.BRIEF,
            "policy": [
                {
                    "name": control.name,
                    "risk": control.risk,
                    "points": list(control.points),
                    "action": control.action,
                }
                for control in policy
            ],
            "intervention_points": [
                {"point": point, "preview": point.startswith("tool_")}
                for point in POINTS
            ],
            "cases": cases,
            "content_safety_demo_contrast": (
                "content_safety_demo classifies one prompt in application "
                "code. Foundry guardrails configure service interception "
                "at input, tool call, tool response and output."
            ),
            "enforcement_scope": (
                "This local policy gate enforces budget and human approval; "
                "it does not claim Foundry supplies an over-budget detector. "
                "Tool-response and output signals are independent fixture "
                "examples, not output from a blocked tool invocation."
            ),
            "source": (
                "https://learn.microsoft.com/en-us/azure/foundry/guardrails/"
                "guardrails-overview"
            ),
        },
        next_steps=["Bind the corresponding service controls in Foundry."],
    )

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, cast

import pytest

from msai_demo import scenario
from msai_demo.foundry_guardrails_demo import (
    POINTS,
    Action,
    Control,
    Point,
    evaluate_policy,
    run_foundry_guardrails_demo,
)

if TYPE_CHECKING:
    from collections.abc import Mapping


@dataclass
class RecordingPort:
    signals: Mapping[Point, frozenset[str]] = field(default_factory=dict)
    calls: list[str] = field(default_factory=list)

    async def read_signals(self) -> Mapping[Point, frozenset[str]]:
        return self.signals

    async def accept_proposal(self, scenario_id: str) -> str:
        self.calls.append(scenario_id)
        return f"recorded::{scenario_id}"


class DeniedPort:
    async def read_signals(self) -> Mapping[Point, frozenset[str]]:
        message = "Synthetic Foundry 403."
        raise PermissionError(message)

    async def accept_proposal(self, scenario_id: str) -> str:
        pytest.fail(f"Guardrails must stop before accepting {scenario_id}.")


def test_offline_executes_policy_with_synthetic_signals() -> None:
    output = asyncio.run(run_foundry_guardrails_demo())
    assert output["mode"] == "local_contract"
    assert output["status"] == "ok"
    assert output["error"] is None
    assert output["headline"] == "Evaluated 2 cases; blocks: 2 at tool_call."
    assert output["evidence"]["fixture_id"] == "foundry-guardrails-v1"
    assert not output["evidence"]["sdk_invoked"]
    assert not output["evidence"]["network_attempted"]
    data = output["data"]
    assert data is not None
    cases = data["cases"]
    assert all(case["blocked"] for case in cases)
    assert cases[0]["cost"] == scenario.price_pilot()
    assert cases[1]["cost"]["total"] > cases[1]["cost"]["budget"]
    assert not any(case["accept_proposal_executed"] for case in cases)
    assert [decision["action"] for decision in cases[1]["decisions"]] == [
        "allow",
        "block",
        "annotate",
        "annotate",
    ]
    assert "over_budget" in cases[1]["signals"]["tool_call"]
    assert [row["preview"] for row in data["intervention_points"]] == [
        False,
        True,
        True,
        False,
    ]


def test_real_gate_calls_only_the_approved_affordable_case() -> None:
    port = RecordingPort()
    output = asyncio.run(run_foundry_guardrails_demo(port=port, approve=True))
    assert port.calls == [scenario.SCENARIO_ID]
    assert output["status"] == "ok"
    assert output["error"] is None
    assert output["headline"] == "Evaluated 2 cases; blocks: 1 at tool_call."
    assert output["data"] is not None
    standard, over_budget = output["data"]["cases"]
    assert standard["accept_proposal_executed"]
    assert standard["acceptable"]
    assert over_budget["human_approval"]
    assert not over_budget["accept_proposal_executed"]
    assert not over_budget["acceptable"]
    assert over_budget["signals"]["tool_call"] == ["over_budget"]


def test_fixture_acceptance_body_can_run_after_human_approval() -> None:
    output = asyncio.run(run_foundry_guardrails_demo(approve=True))
    assert output["data"] is not None
    assert output["data"]["cases"][0]["receipt"] == (
        f"accepted::{scenario.SCENARIO_ID}"
    )


def test_input_injection_blocks_even_approved_affordable_proposals() -> None:
    port = RecordingPort(
        signals={"user_input": frozenset({"prompt_injection"})}
    )
    output = asyncio.run(run_foundry_guardrails_demo(port=port, approve=True))
    assert port.calls == []
    assert output["status"] == "ok"
    assert output["error"] is None
    assert output["headline"] == (
        "Evaluated 2 cases; blocks: 2 at user_input, 1 at tool_call."
    )
    assert output["data"] is not None
    assert output["data"]["cases"][0]["decisions"][0]["action"] == "block"


@pytest.mark.parametrize("approve", [False, True])
def test_missing_policy_blocks_are_errors_without_unsafe_acceptance(
    approve: bool,
) -> None:
    port = RecordingPort()
    output = asyncio.run(
        run_foundry_guardrails_demo(port=port, approve=approve, policy=())
    )
    expected_failures = 1 if approve else 2
    assert output["status"] == "error"
    assert output["headline"] == (
        f"The policy missed {expected_failures} required acceptance blocks."
    )
    assert output["error"] is not None
    assert output["error"]["code"] == "policy_failed"
    assert output["data"] is not None
    assert output["data"]["policy"] == []
    cases = output["data"]["cases"]
    assert all(not case["blocked"] for case in cases)
    assert all(
        not case["accept_proposal_executed"]
        for case in cases
        if not case["acceptable"]
    )
    assert port.calls == ([scenario.SCENARIO_ID] if approve else [])


def test_policy_priority_is_independent_of_rule_order() -> None:
    for actions in (
        ("allow", "annotate", "block"),
        ("block", "annotate", "allow"),
    ):
        controls = tuple(
            Control(action, "risk", POINTS, cast("Action", action))
            for action in actions
        )
        decisions = evaluate_policy(
            controls, dict.fromkeys(POINTS, frozenset({"risk"}))
        )
        assert all(decision["action"] == "block" for decision in decisions)
        assert all(len(row["matched_controls"]) == 3 for row in decisions)
    assert all(row["action"] == "allow" for row in evaluate_policy((), {}))


@pytest.mark.parametrize(
    "control",
    [
        Control("", "risk", POINTS, "block"),
        Control("name", "", POINTS, "block"),
        Control("name", "risk", (), "block"),
        Control("name", "risk", (cast("Point", "unknown"),), "block"),
        Control("name", "risk", POINTS, cast("Action", "unknown")),
    ],
)
def test_malformed_policies_fail_closed(control: Control) -> None:
    with pytest.raises(ValueError, match="Each control"):
        evaluate_policy((control,), {})


def test_unknown_signal_boundary_is_reported_as_malformed() -> None:
    port = RecordingPort(signals={cast("Point", "unknown"): frozenset()})
    output = asyncio.run(run_foundry_guardrails_demo(port=port))
    assert output["status"] == "error"
    assert output["error"] is not None
    assert output["error"]["code"] == "malformed"
    assert port.calls == []


def test_synthetic_403_is_not_remote_execution() -> None:
    output = asyncio.run(run_foundry_guardrails_demo(port=DeniedPort()))
    assert output["status"] == "blocked"
    assert output["error"] is not None
    assert output["error"]["code"] == "authorization_denied"
    assert not output["evidence"]["service_executed"]


def test_live_requires_deployed_controls_before_any_call() -> None:
    output = asyncio.run(
        run_foundry_guardrails_demo(execution="live", port=DeniedPort())
    )
    assert output["mode"] == "not_run"
    assert output["error"] is not None
    assert output["error"]["code"] == "missing_configuration"


def test_unknown_execution_is_rejected() -> None:
    with pytest.raises(ValueError, match="execution must"):
        asyncio.run(run_foundry_guardrails_demo(execution="typo"))

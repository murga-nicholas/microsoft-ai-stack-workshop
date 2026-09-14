"""Check deterministic pilot costs and every acceptance-rule outcome.

Run it:

    uv run pytest tests/test_scenario.py
"""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from typing import TYPE_CHECKING

import pytest

from msai_demo import scenario

if TYPE_CHECKING:
    from pathlib import Path


def test_default_pilot_cost_uses_the_shared_rate_card() -> None:
    cost = scenario.price_pilot()
    rates = scenario.rate_card()
    expected_staffing = {
        "solution-architect": round(
            rates["solution-architect"] * 0.5 * scenario.PILOT_WEEKS
        ),
        "python-engineer": rates["python-engineer"] * scenario.PILOT_WEEKS,
    }
    platform = scenario.PLATFORM_COST_USD_PER_WEEK * scenario.PILOT_WEEKS
    total = sum(expected_staffing.values()) + platform

    assert cost == {
        "weeks": scenario.PILOT_WEEKS,
        "staffing": expected_staffing,
        "staffing_total": sum(expected_staffing.values()),
        "platform_total": platform,
        "total": total,
        "budget": scenario.PILOT_BUDGET_USD,
        "within_budget": True,
        "headroom": scenario.PILOT_BUDGET_USD - total,
    }
    assert scenario.price_pilot(team={}) == cost


def test_custom_team_weeks_and_budget_are_costed_explicitly() -> None:
    weeks = 3
    allocation = {"python-engineer": 0.333, "qa-engineer": 0.5}
    rates = scenario.rate_card()
    staffing = {
        role: round(rates[role] * fte * weeks)
        for role, fte in allocation.items()
    }
    platform = scenario.PLATFORM_COST_USD_PER_WEEK * weeks
    total = sum(staffing.values()) + platform
    cost = scenario.price_pilot(weeks=weeks, team=allocation, budget=total)

    assert cost == {
        "weeks": weeks,
        "staffing": staffing,
        "staffing_total": sum(staffing.values()),
        "platform_total": platform,
        "total": total,
        "budget": total,
        "within_budget": True,
        "headroom": 0,
    }
    over_budget = scenario.price_pilot(
        weeks=weeks, team=allocation, budget=total - 1
    )
    assert over_budget["within_budget"] is False
    assert over_budget["headroom"] == -1
    assert allocation == {"python-engineer": 0.333, "qa-engineer": 0.5}


@pytest.mark.parametrize("weeks", [0, -1])
def test_non_positive_weeks_are_rejected(weeks: int) -> None:
    with pytest.raises(
        ValueError, match=rf"weeks must be positive, got {weeks}\."
    ):
        scenario.price_pilot(weeks=weeks)


def test_unknown_roles_are_reported_in_sorted_order() -> None:
    with pytest.raises(ValueError, match="Unknown roles") as exc:
        scenario.price_pilot(
            team={"z-unknown": 1.0, "python-engineer": 1.0, "a-unknown": 0.5}
        )

    assert str(exc.value) == (
        "Unknown roles: a-unknown, z-unknown. Known: "
        + ", ".join(sorted(scenario.rate_card()))
        + "."
    )


def test_rate_card_returns_an_independent_copy() -> None:
    original = scenario.rate_card()
    changed = scenario.rate_card()
    changed["python-engineer"] = 0
    changed["new-role"] = 1

    assert scenario.rate_card() == original
    assert changed != original


def test_plan_summary_is_complete_and_independent_of_the_plan() -> None:
    rows = scenario.plan_summary()

    assert len(rows) == scenario.PILOT_WEEKS
    assert [row["week"] for row in rows] == list(
        range(1, scenario.PILOT_WEEKS + 1)
    )
    assert rows == [
        {
            "week": milestone.week,
            "title": milestone.title,
            "exit_gate": milestone.exit_gate,
        }
        for milestone in scenario.PLAN
    ]
    rows[0]["title"] = "Changed copy"
    assert scenario.plan_summary()[0]["title"] == scenario.PLAN[0].title


@pytest.mark.parametrize("within_budget", [False, True])
@pytest.mark.parametrize("approved", [False, True])
@pytest.mark.parametrize("grounded", [False, True])
def test_proposal_reports_every_failed_rule(
    within_budget: bool, approved: bool, grounded: bool
) -> None:
    default_cost = scenario.price_pilot()
    budget = default_cost["total"] - (0 if within_budget else 1)
    cost = scenario.price_pilot(budget=budget)
    sources = ["agent-framework-overview"] if grounded else []
    expected_reasons = []
    if not within_budget:
        expected_reasons.append(f"Over budget by {abs(cost['headroom'])} USD.")
    if not approved:
        expected_reasons.append("No human approval recorded.")
    if not grounded:
        expected_reasons.append("No grounding source cited.")

    acceptable, reasons = scenario.proposal_is_acceptable(
        cost=cost, approved=approved, cited_sources=sources
    )

    assert acceptable is (within_budget and approved and grounded)
    assert reasons == expected_reasons


def test_proposal_schema_checks_the_executed_fields(tmp_path: Path) -> None:
    proposal = scenario.pilot_proposal()
    assert (
        scenario.proposal_schema()
        .model_validate(proposal)
        .model_dump()["cost"]["total"]
        == (scenario.price_pilot()["total"])
    )
    assert all(scenario.proposal_checks(proposal).values())
    assert scenario.proposal_schema() is scenario.proposal_schema()
    notes = tmp_path / "notes.md"
    notes.write_text("## Section: other-section\n", encoding="utf-8")
    assert scenario.proposal_checks(proposal, notes_path=notes) == {
        "schema_valid": True,
        "sources_valid": False,
        "within_budget": True,
        "cost_matches_pricing": True,
    }
    proposal["cost"] = scenario.price_pilot(budget=1)
    assert not scenario.proposal_checks(proposal)["within_budget"]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("scope", ""),
        ("milestones", []),
        ("cost", {"total": "invented"}),
        ("cited_sections", []),
        ("extra", True),
    ],
)
def test_malformed_proposals_fail_the_schema(
    field: str, value: object
) -> None:
    proposal = scenario.pilot_proposal()
    proposal[field] = value
    assert scenario.proposal_checks(proposal) == {
        "schema_valid": False,
        "sources_valid": False,
        "within_budget": False,
        "cost_matches_pricing": False,
    }


def test_event_store_records_actions_atomically_once(tmp_path: Path) -> None:
    reads: list[str] = []
    store = scenario.EventStore(tmp_path, files_read=reads)
    assert store.events() == []
    assert store.actions() == []
    assert reads == [str((tmp_path / "events.sqlite3").resolve())]
    store.append("gate_reached")
    store.append("approval_recorded", approved=True)
    action = store.execute_action(scenario.SCENARIO_ID)
    assert action is not None
    assert action["kind"] == "simulated business action"
    assert store.execute_action(scenario.SCENARIO_ID) is None
    assert scenario.EventStore(tmp_path).actions() == [action]
    events = store.events()
    assert [event["sequence"] for event in events] == [1, 2, 3]
    assert [event["name"] for event in events] == [
        "gate_reached",
        "approval_recorded",
        "action_executed",
    ]
    assert {event["pid"] for event in events} == {os.getpid()}
    assert events[-1]["details"] == action


@pytest.mark.parametrize("approved", [None, False, "yes"])
def test_event_store_requires_an_actual_approval(
    tmp_path: Path, approved: object
) -> None:
    store = scenario.EventStore(tmp_path)
    if approved is not None:
        store.append("approval_recorded", approved=approved)
    with pytest.raises(ValueError, match="human approval"):
        store.execute_action(scenario.SCENARIO_ID)
    assert store.actions() == []


def test_latest_decision_replaces_an_earlier_approval(tmp_path: Path) -> None:
    store = scenario.EventStore(tmp_path)
    store.append("approval_recorded", approved=True)
    store.append("approval_recorded", approved=False)
    with pytest.raises(ValueError, match="human approval"):
        store.execute_action(scenario.SCENARIO_ID)


def test_competing_resumes_cannot_duplicate_the_action(tmp_path: Path) -> None:
    store = scenario.EventStore(tmp_path)
    store.append("approval_recorded", approved=True)
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(
            executor.map(store.execute_action, [scenario.SCENARIO_ID] * 2)
        )
    assert sum(action is not None for action in results) == 1
    assert len(store.actions()) == 1
    assert (
        sum(event["name"] == "action_executed" for event in store.events())
        == 1
    )


def test_altered_cost_and_scenario_identity_are_rejected(
    tmp_path: Path,
) -> None:
    proposal = scenario.pilot_proposal()
    proposal["cost"] = {**scenario.price_pilot(), "total": 0}
    checks = scenario.proposal_checks(proposal)
    assert checks["schema_valid"]
    assert not checks["cost_matches_pricing"]
    store = scenario.EventStore(tmp_path)
    store.append("approval_recorded", approved=True)
    with pytest.raises(ValueError, match="shared pilot scenario"):
        store.execute_action("model-invented-scenario")
    assert store.actions() == []

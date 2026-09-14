"""One business task, shared by every demo in the repo.

Thirty-two demos across two lanes are only comparable if they are all
doing the same job. They are: draft a six-week customer-support pilot
proposal, keep it inside an illustrative budget, and refuse to accept
it until a human approves.

Everything here is deterministic Python with no model in the loop, so
the arithmetic in a proposal is checkable rather than plausible. When
a demo reports ``within_budget: true``, that came from
:func:`price_pilot`, not from a language model's opinion.

Run it:

    uv run msai-demo group-chat --format json
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from functools import cache
from typing import (
    TYPE_CHECKING,
    Annotated,
    Final,
    NotRequired,
    TypedDict,
    cast,
)

from msai_demo.runtime import REPO_ROOT

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

    from pydantic import BaseModel

PILOT_BUDGET_USD: Final[int] = 25_000
PILOT_WEEKS: Final[int] = 6
SCENARIO_ID: Final[str] = "support-pilot-v1"

BRIEF: Final[str] = (
    "Contoso wants a six-week customer-support agent pilot. Budget is "
    "an illustrative 25,000 USD. Azure resources and permissions are "
    "not provisioned yet. A named human must approve the proposal "
    "before any work is accepted."
)

# Illustrative weekly rates for the workshop. Not a DataArt rate card.
RATE_CARD_USD_PER_WEEK: Final[dict[str, int]] = {
    "solution-architect": 2_400,
    "python-engineer": 1_900,
    "qa-engineer": 1_500,
}

# Running costs a proposal must not forget. Also illustrative.
PLATFORM_COST_USD_PER_WEEK: Final[int] = 180


class PilotCost(TypedDict):
    """Costed pilot, computed rather than generated.

    Attributes:
        weeks: Pilot length in weeks.
        staffing: Cost per role for the whole pilot.
        staffing_total: Sum of ``staffing``.
        platform_total: Model, hosting and telemetry running cost.
        total: Everything the pilot costs.
        budget: The budget it is measured against.
        within_budget: Whether ``total`` fits inside ``budget``.
        headroom: ``budget`` minus ``total``. Negative when over.
    """

    weeks: int
    staffing: dict[str, int]
    staffing_total: int
    platform_total: int
    total: int
    budget: int
    within_budget: bool
    headroom: int


@dataclass(frozen=True)
class Milestone:
    """One week of the pilot with an exit gate.

    Attributes:
        week: One-based week number.
        title: What the week delivers.
        exit_gate: The condition that lets the pilot continue.
    """

    week: int
    title: str
    exit_gate: str


PLAN: Final[tuple[Milestone, ...]] = (
    Milestone(
        1,
        "Readiness and identity",
        "Scoped RBAC calls succeed; unauthorised calls are denied",
    ),
    Milestone(2, "One agent, one tool", "Tool call succeeds on real data"),
    Milestone(3, "Retrieval grounding", "Answers cite a source document"),
    Milestone(
        4,
        "Approval workflow",
        "No action before approval, including after a restart",
    ),
    Milestone(5, "Telemetry and cost", "Per-run tokens and latency shown"),
    Milestone(6, "Evaluation and handover", "Evaluation suite passes"),
)


def rate_card() -> dict[str, int]:
    """Return a copy of the illustrative weekly rate card."""
    return dict(RATE_CARD_USD_PER_WEEK)


def price_pilot(
    *,
    weeks: int = PILOT_WEEKS,
    team: dict[str, float] | None = None,
    budget: int = PILOT_BUDGET_USD,
) -> PilotCost:
    """Cost a pilot from the rate card.

    Args:
        weeks: Pilot length. Must be positive.
        team: Role name to full-time equivalents, for example
            ``{"python-engineer": 1.0}``. Defaults to one architect at
            half time plus one engineer full time.
        budget: Budget to measure the total against.

    Returns:
        A fully costed :class:`PilotCost`.

    Raises:
        ValueError: If ``weeks`` is not positive, or a role is not on
            the rate card. An unknown role is a proposal error worth
            surfacing, not a silent zero.
    """
    if weeks <= 0:
        message = f"weeks must be positive, got {weeks}."
        raise ValueError(message)

    allocation = team or {"solution-architect": 0.5, "python-engineer": 1.0}
    unknown = sorted(set(allocation) - set(RATE_CARD_USD_PER_WEEK))
    if unknown:
        known = ", ".join(sorted(RATE_CARD_USD_PER_WEEK))
        message = f"Unknown roles: {', '.join(unknown)}. Known: {known}."
        raise ValueError(message)

    staffing = {
        role: round(RATE_CARD_USD_PER_WEEK[role] * fte * weeks)
        for role, fte in allocation.items()
    }
    staffing_total = sum(staffing.values())
    platform_total = PLATFORM_COST_USD_PER_WEEK * weeks
    total = staffing_total + platform_total
    return {
        "weeks": weeks,
        "staffing": staffing,
        "staffing_total": staffing_total,
        "platform_total": platform_total,
        "total": total,
        "budget": budget,
        "within_budget": total <= budget,
        "headroom": budget - total,
    }


def plan_summary() -> list[dict[str, object]]:
    """Return the six-week plan as JSON-ready rows."""
    return [
        {"week": m.week, "title": m.title, "exit_gate": m.exit_gate}
        for m in PLAN
    ]


def proposal_is_acceptable(
    *,
    cost: PilotCost,
    approved: bool,
    cited_sources: list[str],
) -> tuple[bool, list[str]]:
    """Apply the three acceptance rules to a proposal.

    These are the rules every lane in this repo is judged against, so
    the legacy and current implementations are compared on identical
    terms.

    Args:
        cost: Output of :func:`price_pilot`.
        approved: Whether a human has approved.
        cited_sources: Section names the proposal cited.

    Returns:
        ``(acceptable, reasons)``. ``reasons`` lists every rule that
        failed, so one call explains the whole verdict.
    """
    reasons: list[str] = []
    if not cost["within_budget"]:
        reasons.append(f"Over budget by {abs(cost['headroom'])} USD.")
    if not approved:
        reasons.append("No human approval recorded.")
    if not cited_sources:
        reasons.append("No grounding source cited.")
    return (not reasons, reasons)


class ProposalTurn(TypedDict):
    """One speaking turn, recorded identically by both lanes.

    Attributes:
        index: Zero-based turn number.
        speaker: Participant name.
        provider: Which vendor answered this turn.
        model: Model the turn asked for.
        text: What the participant said.
        source_event: Native event or message class the framework
            emitted, so the transcript can be traced back to the SDK.
        usage: Reported token usage, or ``None`` when the framework
            did not report any. Never an invented zero.
    """

    index: int
    speaker: str
    provider: str
    model: str
    text: str
    source_event: str
    usage: dict[str, int] | None


class ProposalRun(TypedDict):
    """The shared payload both group-chat implementations return.

    Two frameworks are only comparable if they answer the same
    questions. These are the questions.

    Attributes:
        implementation: ``autogen`` or ``agent-framework``.
        framework_version: Installed version of that framework.
        scenario_id: Which scenario ran.
        participants: Name, provider and model per participant.
        turns: The transcript.
        cost: Deterministic costing from :func:`price_pilot`.
        approval: Approval request id, state and who decided.
        recovery: How state survived a process boundary.
        actions: Side effects, with their idempotency keys.
        checks: Executed acceptance checks, not opinions.
        application_owned: Integration concerns this lane made the
            application implement rather than the framework.
        tool_calling: Whether the run actually exercised a tool,
            and why not when it did not.
        stop_reason: Why the conversation ended.
    """

    implementation: str
    framework_version: str
    scenario_id: str
    participants: list[dict[str, str]]
    turns: list[ProposalTurn]
    cost: PilotCost
    approval: Mapping[str, object]
    recovery: Mapping[str, object]
    actions: list[dict[str, object]]
    checks: dict[str, bool]
    application_owned: list[str]
    tool_calling: str
    stop_reason: str
    proposal: NotRequired[dict[str, object]]
    events: NotRequired[list[dict[str, object]]]


@cache
def proposal_schema() -> type[BaseModel]:
    """Load and cache the schema only when validation is requested.

    Shared pricing also serves SDK-free contracts. Importing this
    module must therefore work before Pydantic is installed.
    """
    from pydantic import BaseModel, ConfigDict, Field

    class ProposalMilestone(BaseModel):
        """A delivery milestone with an explicit, nonempty exit gate."""

        model_config = ConfigDict(extra="forbid", strict=True)
        week: Annotated[int, Field(ge=1, le=PILOT_WEEKS)]
        title: Annotated[str, Field(min_length=1)]
        exit_gate: Annotated[str, Field(min_length=1)]

    class ProposalCost(BaseModel):
        """The real schema for every component of the pilot costing."""

        model_config = ConfigDict(extra="forbid", strict=True)
        weeks: Annotated[int, Field(gt=0)]
        staffing: dict[str, int]
        staffing_total: Annotated[int, Field(ge=0)]
        platform_total: Annotated[int, Field(ge=0)]
        total: Annotated[int, Field(ge=0)]
        budget: Annotated[int, Field(ge=0)]
        within_budget: bool
        headroom: int

    class PilotProposal(BaseModel):
        """Require scope, milestones, cost and citations."""

        model_config = ConfigDict(extra="forbid", strict=True)
        scope: Annotated[str, Field(min_length=1)]
        milestones: Annotated[list[ProposalMilestone], Field(min_length=1)]
        cost: ProposalCost
        cited_sections: Annotated[list[str], Field(min_length=1)]

    return PilotProposal


def pilot_proposal() -> dict[str, object]:
    """Build the scripted proposal from the shared plan and pricing."""
    return {
        "scope": BRIEF,
        "milestones": plan_summary(),
        "cost": price_pilot(),
        "cited_sections": ["agent-framework-overview"],
    }


def proposal_checks(
    proposal: Mapping[str, object], *, notes_path: Path | None = None
) -> dict[str, bool]:
    """Validate the actual proposal and resolve its cited headings.

    Args:
        proposal: Structured proposal produced during the chat.
        notes_path: Optional notes file for a different corpus.

    Returns:
        Independent schema, grounding and budget checks.
    """
    from pydantic import ValidationError

    try:
        validated = proposal_schema().model_validate(proposal)
    except ValidationError:
        return {
            "schema_valid": False,
            "sources_valid": False,
            "within_budget": False,
            "cost_matches_pricing": False,
        }
    path = notes_path or REPO_ROOT / "data/microsoft_ai_stack_notes.md"
    headings = set(
        re.findall(r"^## Section: (.+)$", path.read_text("utf-8"), re.M)
    )
    payload = cast("dict[str, object]", validated.model_dump())
    cost = cast("PilotCost", payload["cost"])
    cited_sections = cast("list[str]", payload["cited_sections"])
    return {
        "schema_valid": True,
        "sources_valid": set(cited_sections) <= headings,
        "within_budget": cost["total"] <= cost["budget"],
        "cost_matches_pricing": cost == price_pilot(),
    }


class EventStore:
    """Keep ordered events and idempotent simulated actions on disk.

    SQLite makes the action and its audit event one transaction. The
    action is the durable local record itself; no customer is billed.
    This deliberately makes no claim about external side effects.

    Args:
        directory: Run directory shared with the resume processes.
        files_read: Optional list recording actual database reads.
    """

    def __init__(
        self, directory: Path, *, files_read: list[str] | None = None
    ) -> None:
        """Open the shared event and idempotency database."""
        self.path = directory / "events.sqlite3"
        self._files_read = files_read
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.executescript(
                "CREATE TABLE IF NOT EXISTS events ("
                "sequence INTEGER PRIMARY KEY, name TEXT NOT NULL, "
                "pid INTEGER NOT NULL, details TEXT NOT NULL);"
                "CREATE TABLE IF NOT EXISTS actions ("
                "idempotency_key TEXT PRIMARY KEY, payload TEXT NOT NULL);"
            )

    def append(self, name: str, **details: object) -> None:
        """Append an observed lifecycle event with the current PID."""
        with closing(sqlite3.connect(self.path)) as connection, connection:
            self._append(connection, name, details)

    def events(self) -> list[dict[str, object]]:
        """Read lifecycle events in their committed execution order."""
        self._record_read()
        with closing(sqlite3.connect(self.path)) as connection, connection:
            rows = connection.execute(
                "SELECT sequence, name, pid, details FROM events "
                "ORDER BY sequence"
            ).fetchall()
        return [
            {
                "sequence": row[0],
                "name": row[1],
                "pid": row[2],
                "details": json.loads(row[3]),
            }
            for row in rows
        ]

    def actions(self) -> list[dict[str, object]]:
        """Read the simulated business actions actually committed."""
        self._record_read()
        with closing(sqlite3.connect(self.path)) as connection, connection:
            rows = connection.execute(
                "SELECT payload FROM actions ORDER BY rowid"
            ).fetchall()
        return [cast("dict[str, object]", json.loads(row[0])) for row in rows]

    def execute_action(self, scenario_id: str) -> dict[str, object] | None:
        """Commit an approved simulated action once per scenario.

        Returns:
            The new action, or ``None`` if it was already committed.

        Raises:
            ValueError: If the scenario differs or approval is missing.
        """
        if scenario_id != SCENARIO_ID:
            message = "Only the shared pilot scenario may be accepted."
            raise ValueError(message)
        self._record_read()
        with closing(sqlite3.connect(self.path)) as connection, connection:
            # Reserve the write transaction before reading the decision
            # and key, so competing resume processes cannot both act.
            connection.execute("BEGIN IMMEDIATE")
            approval = connection.execute(
                "SELECT details FROM events WHERE name = ? "
                "ORDER BY sequence DESC LIMIT 1",
                ("approval_recorded",),
            ).fetchone()
            if (
                approval is None
                or json.loads(approval[0]).get("approved") is not True
            ):
                message = "A human approval is required before the action."
                raise ValueError(message)
            key = f"accept::{scenario_id}"
            existing = connection.execute(
                "SELECT 1 FROM actions WHERE idempotency_key = ?", (key,)
            ).fetchone()
            if existing is not None:
                return None
            action: dict[str, object] = {
                "name": "accept_proposal",
                "kind": "simulated business action",
                "idempotency_key": key,
                "outcome": f"accepted::{scenario_id}",
            }
            connection.execute(
                "INSERT INTO actions VALUES (?, ?)",
                (key, json.dumps(action)),
            )
            self._append(connection, "action_executed", action)
        return action

    def _record_read(self) -> None:
        """Add a read once, without claiming that writes are reads."""
        if self._files_read is not None:
            path = str(self.path.resolve())
            if path not in self._files_read:
                self._files_read.append(path)

    @staticmethod
    def _append(
        connection: sqlite3.Connection,
        name: str,
        details: Mapping[str, object],
    ) -> None:
        """Append inside the caller's transaction."""
        connection.execute(
            "INSERT INTO events (name, pid, details) VALUES (?, ?, ?)",
            (name, os.getpid(), json.dumps(details)),
        )

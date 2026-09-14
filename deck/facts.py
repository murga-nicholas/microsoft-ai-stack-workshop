"""Numbers for the deck, taken from the code rather than typed in.

A slide that quotes a figure nobody can reproduce is a liability in
front of an architect. So every number in this deck comes from one of
three places:

1. the installed packages, read at build time;
2. ``msai_demo.scenario``, the same functions the demos call;
3. ``deck/facts.json``, written by ``collect_facts.py`` from a real
   run of the demos.

If a demo changes, rebuild the deck and the slides change with it.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

DECK_DIR = Path(__file__).resolve().parent
REPO_ROOT = DECK_DIR.parent
FACTS_FILE = DECK_DIR / "facts.json"

# The deck is built from the repository it documents.
sys.path.insert(0, str(REPO_ROOT / "src"))

from msai_demo import scenario  # noqa: E402
from msai_demo.doctor import collect_readiness  # noqa: E402

# Dates that are historical record, not machine state. Each one was
# read from an official source on the research date below.
RESEARCH_DATE = "2026-09-14"
AUTOGEN_LAST_RELEASE = "2025-09-30"
AF_LAST_RELEASE = "2026-09-10"
AF_GA_DATE = "2026-04-03"
FOUNDRY_RENAME_DATE = "2025-11-18"
BOT_FRAMEWORK_EOL = "2025-12"
ENTRA_AGENT_ID_GA = "2026-04"


@dataclass
class Facts:
    """Everything the slide modules are allowed to quote.

    Attributes:
        deck_date: Date printed on the cover.
        author: Presenter name.
        author_role: Presenter role and company.
        research_date: When the external claims were verified.
        packages: Installed distribution versions.
        credentials: Credential presence flags.
        demos: Per-demo live-path readiness.
        pilot_cost: Output of ``scenario.price_pilot()``.
        plan: The six-week plan rows.
        runs: Captured demo payloads from ``facts.json``.
    """

    deck_date: str
    author: str
    author_role: str
    research_date: str = RESEARCH_DATE
    packages: dict[str, str] = field(default_factory=dict)
    credentials: dict[str, bool] = field(default_factory=dict)
    demos: dict[str, bool] = field(default_factory=dict)
    pilot_cost: dict[str, Any] = field(default_factory=dict)
    plan: list[dict[str, Any]] = field(default_factory=list)
    runs: dict[str, Any] = field(default_factory=dict)

    # ---- convenience accessors used all over the slide modules ----
    @property
    def autogen_version(self) -> str:
        """Installed AutoGen version."""
        return self.packages.get("autogen-agentchat", "not installed")

    @property
    def af_version(self) -> str:
        """Installed Agent Framework core version."""
        return self.packages.get("agent-framework-core", "not installed")

    @property
    def autogen_last_release(self) -> str:
        """Date AutoGen last published to PyPI."""
        return AUTOGEN_LAST_RELEASE

    @property
    def af_last_release(self) -> str:
        """Date Agent Framework last published to PyPI."""
        return AF_LAST_RELEASE

    @property
    def package_count(self) -> str:
        """How many packages ``doctor`` reports."""
        return str(len(self.packages))

    @property
    def checkpoint_count(self) -> str:
        """Checkpoint files the Agent Framework resume process read."""
        files = self.recovery("agent-framework")["files_read"]
        # The run directory itself lives under .msai_checkpoints/, so
        # match the checkpoints folder inside it, not the substring.
        return str(sum(1 for path in files if "/checkpoints/" in path))

    @property
    def responsibility_matrix(self) -> list[dict[str, str]]:
        """Who owns each recovery concern, per the comparison."""
        comparison = self.demo_run("group-chat")["comparison"]
        return [dict(row) for row in comparison["responsibility_matrix"]]

    @property
    def verdict(self) -> str:
        """The comparison's own verdict sentence."""
        return str(self.demo_run("group-chat")["comparison"]["verdict"])

    def recovery(self, lane: str) -> dict[str, Any]:
        """Measured process and disk evidence for one lane."""
        return dict(self._lane(lane)["recovery"])

    def checks(self, lane: str) -> dict[str, bool]:
        """Computed acceptance checks for one lane."""
        return {k: bool(v) for k, v in self._lane(lane)["checks"].items()}

    def _lane(self, lane: str) -> dict[str, Any]:
        """One group-chat lane, by implementation name."""
        return self.demo_run(
            "autogen" if lane == "autogen" else "group-chat-agent-framework"
        )

    def demo_run(self, name: str) -> dict[str, Any]:
        """Return one captured demo payload.

        Raises:
            KeyError: If ``collect_facts.py`` did not capture it. A
                slide must never paper over a missing run with a
                number somebody typed.
        """
        value = self.runs[name]
        if not isinstance(value, dict):
            message = f"facts.json entry {name!r} is not an object"
            raise TypeError(message)
        return value

    def turns(self, implementation: str) -> list[dict[str, Any]]:
        """Return the recorded transcript for one group-chat lane."""
        return list(self.demo_run(implementation)["turns"])

    @property
    def evaluation_rows(self) -> list[dict[str, Any]]:
        """Per-case results from the recorded evaluation run."""
        return list(self.demo_run("evaluation")["rows"])

    @property
    def otel(self) -> dict[str, Any]:
        """The recorded OpenTelemetry capture."""
        return self.demo_run("otel")

    @property
    def spans(self) -> list[dict[str, Any]]:
        """Spans from the recorded OpenTelemetry capture."""
        return list(self.otel["spans"])

    @property
    def workflow_edges(self) -> set[tuple[str, str]]:
        """Executor edges from the recorded ``WorkflowViz`` mermaid."""
        graph = str(self.demo_run("workflow")["graph"])
        edges = set()
        for raw in graph.splitlines():
            line = raw.strip().rstrip(";")
            if "-->" in line:
                source, target = (part.strip() for part in line.split("-->"))
                edges.add((source, target))
        return edges

    @property
    def identity(self) -> dict[str, Any]:
        """The recorded Microsoft Entra identity run."""
        return self.demo_run("azure-identity")

    def guardrail_case(self, case: str) -> dict[str, Any]:
        """One recorded guardrails case, by name."""
        for item in self.demo_run("foundry-guardrails")["cases"]:
            if item["case"] == case:
                return dict(item)
        message = f"guardrails run has no case {case!r}"
        raise KeyError(message)


def load(*, deck_date: str, author: str, author_role: str) -> Facts:
    """Assemble the facts a deck build is allowed to quote."""
    readiness = collect_readiness()
    if not FACTS_FILE.is_file():
        message = (
            f"{FACTS_FILE} is missing. Run "
            "`uv run --group deck python deck/collect_facts.py` first: "
            "the deck only quotes numbers a real run produced."
        )
        raise FileNotFoundError(message)
    runs = json.loads(FACTS_FILE.read_text(encoding="utf-8"))

    return Facts(
        deck_date=deck_date,
        author=author,
        author_role=author_role,
        packages=readiness["packages"],
        credentials=readiness["credentials"],
        demos=readiness["demos"],
        pilot_cost=dict(scenario.price_pilot()),
        plan=scenario.plan_summary(),
        runs=runs,
    )

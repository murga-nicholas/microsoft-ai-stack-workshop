"""Capture real demo output so the deck cannot drift from the code.

    uv run --group deck python deck/collect_facts.py

Runs the demos the deck quotes, offline, and writes their payloads to
``deck/facts.json``. Build the deck afterwards and the slides show the
numbers those runs actually produced - checkpoint counts, action
outcomes, the ownership diff - rather than numbers somebody typed once
and forgot to update.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

DECK_DIR = Path(__file__).resolve().parent
REPO_ROOT = DECK_DIR.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from msai_demo.runtime import configure_telemetry  # noqa: E402

OUTPUT = DECK_DIR / "facts.json"


async def collect() -> dict[str, Any]:
    """Run the quoted demos and return their payloads by name."""
    # Nothing about building a deck should emit telemetry.
    configure_telemetry(enabled=False)

    from msai_demo.group_chat_demo import run_group_chat_demo

    captured: dict[str, Any] = {}
    group_chat = await run_group_chat_demo(
        implementation="both",
        execution="offline",
    )
    for child in group_chat.get("children", []):
        payload = _portable(child.get("data") or {})
        name = str(payload.get("implementation") or child["demo"])
        captured[name] = payload
        captured[child["demo"]] = payload

    data = _portable(group_chat.get("data") or {})
    captured["group-chat"] = {"comparison": data.get("comparison", {})}

    # Every other figure a slide quotes comes from a real run too.
    from msai_demo.evaluation_demo import run_evaluation_demo
    from msai_demo.foundry_guardrails_demo import (
        run_foundry_guardrails_demo,
    )

    for name, runner in (
        ("evaluation", run_evaluation_demo),
        ("foundry-guardrails", run_foundry_guardrails_demo),
    ):
        outcome = await runner(execution="offline")
        captured[name] = _flatten(outcome)

    from msai_demo.azure_identity_demo import run_azure_identity_demo
    from msai_demo.observability_demo import run_observability_demo
    from msai_demo.runtime import env_is_present
    from msai_demo.workflow_demo import run_workflow_demo

    captured["otel"] = _flatten(
        await run_observability_demo(execution="offline", trace="memory")
    )
    # The workflow slide draws the graph the SDK exported, not a sketch.
    captured["workflow"] = _flatten(
        await run_workflow_demo(execution="offline")
    )
    principal = all(
        env_is_present(name)
        for name in (
            "AZURE_TENANT_ID",
            "AZURE_CLIENT_ID",
            "AZURE_CLIENT_SECRET",
        )
    )
    # The identity slide is the one slide that can be recorded live on
    # a laptop. It says which mode it was recorded in either way.
    captured["azure-identity"] = _flatten(
        await run_azure_identity_demo(
            execution="live" if principal else "offline"
        )
    )
    return captured


def _portable(value: Any) -> Any:
    """Make recorded paths repository-relative, with forward slashes.

    facts.json is committed beside the deck, so it must not carry the
    absolute layout of whichever laptop recorded it.
    """
    if isinstance(value, dict):
        return {key: _portable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_portable(item) for item in value]
    if isinstance(value, str) and str(REPO_ROOT) in value:
        return value.replace(str(REPO_ROOT) + "\\", "").replace("\\", "/")
    return value


def _flatten(outcome: dict[str, Any]) -> dict[str, Any]:
    """Keep mode, status and headline beside their payload."""
    return {
        "mode": outcome["mode"],
        "status": outcome["status"],
        "headline": outcome["headline"],
        **(outcome["data"] or {}),
    }


def main() -> int:
    """Write ``deck/facts.json`` and report what was captured."""
    captured = asyncio.run(collect())
    OUTPUT.write_text(
        json.dumps(captured, indent=2, default=str),
        encoding="utf-8",
    )
    print(f"captured {len(captured)} payloads -> {OUTPUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

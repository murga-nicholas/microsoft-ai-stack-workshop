"""Bot Framework: keep the handler, replace the channel adapter.

The legacy Bot Framework SDK's final LTS ended in December 2025.
Microsoft 365 Agents SDK supplies the current hosting, authentication
and activity packages. This local adapter executes one channel turn;
it does not authenticate a channel or invoke either vendor SDK.

The business handler is ordinary Python, shared verbatim with the
current lane through :func:`handle_activity`.

Run it:

    uv run msai-demo bot-framework
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol, TypedDict

from msai_demo import scenario
from msai_demo.contracts import (
    DemoResult,
    evidence,
    missing_configuration,
    result,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

DEMO_NAME = "bot-framework"
TECHNOLOGY = "Bot Framework SDK (retired)"
MIGRATION_SOURCE = (
    "https://learn.microsoft.com/en-us/microsoft-365/agents-sdk/"
    "bf-migration-python"
)
PACKAGE_MAPPING: dict[str, list[str]] = {
    "botbuilder-core": ["microsoft-agents-hosting-core"],
    "botbuilder-schema": ["microsoft-agents-activity"],
    "botbuilder-integration-aiohttp": ["microsoft-agents-hosting-aiohttp"],
    "botbuilder-azure": [
        "microsoft-agents-storage-blob",
        "microsoft-agents-storage-cosmos",
    ],
}


class ActivityTurn(TypedDict):
    """One local turn and its captured outgoing activities."""

    activity: dict[str, object]
    responses: list[dict[str, object]]
    handled: bool


class ActivityPort(Protocol):
    """The adapter boundary around the portable business handler."""

    async def process_activity(
        self, activity: Mapping[str, object]
    ) -> ActivityTurn:
        """Process one input activity and capture its outgoing reply."""


@dataclass
class LocalTurnContext:
    """A local TurnContext shape, with replies captured in memory.

    Attributes:
        activity: The incoming channel activity.
        responses: Outgoing activities, never sent to a channel.
    """

    activity: Mapping[str, object]
    responses: list[dict[str, object]] = field(default_factory=list)

    def send_activity(self, response: dict[str, object]) -> None:
        """Capture a reply with the adapter's routing reference."""
        self.responses.append(
            {**response, "replyToId": self.activity.get("id")}
        )


def handle_activity(activity: Mapping[str, object]) -> dict[str, object]:
    """Cost a pilot without depending on either channel SDK.

    Args:
        activity: A channel activity dictionary with ``type`` and,
            for a message, nonblank ``text``. SDK adapters convert
            their activity models to this dictionary at the seam.

    Returns:
        A reply dictionary. Other activity types are acknowledged as
        unhandled. A message produces a costed proposal awaiting
        human approval; text claiming approval cannot grant it.

    Raises:
        ValueError: If the activity lacks a valid type or message.
    """
    activity_type = activity.get("type")
    if not isinstance(activity_type, str) or not activity_type.strip():
        message = "An activity needs a nonblank string type."
        raise ValueError(message)
    if activity_type != "message":
        return {"handled": False, "reason": "No message handler applies."}
    text = activity.get("text")
    if not isinstance(text, str) or not text.strip():
        message = "A message activity needs nonblank text."
        raise ValueError(message)

    cost = scenario.price_pilot()
    acceptable, failures = scenario.proposal_is_acceptable(
        cost=cost,
        approved=False,
        cited_sources=[scenario.SCENARIO_ID],
    )
    return {
        "handled": True,
        "type": "message",
        "text": (
            f"The {cost['weeks']}-week pilot costs {cost['total']} USD "
            f"against a {cost['budget']} USD budget. "
            "A named human must approve before work is accepted."
        ),
        "scenario_id": scenario.SCENARIO_ID,
        "cost": cost,
        "approved": False,
        "acceptable": acceptable,
        "acceptance_failures": failures,
    }


class LocalActivityAdapter:
    """Execute the legacy adapter and handler without botbuilder."""

    async def process_activity(
        self, activity: Mapping[str, object]
    ) -> ActivityTurn:
        """Run the shared handler and capture its reply in a context."""
        context = LocalTurnContext(activity=activity)
        reply = handle_activity(context.activity)
        handled = reply["handled"] is True
        if handled:
            context.send_activity(reply)
        return {
            "activity": dict(activity),
            "responses": context.responses,
            "handled": handled,
        }


async def run_bot_framework_demo(
    *,
    execution: str = "offline",
    port: ActivityPort | None = None,
) -> DemoResult:
    """Process one support-pilot message through a local adapter.

    Args:
        execution: ``offline`` runs locally. ``live`` reports the
            missing channel host before processing any activity.
        port: Optional local adapter replacement for deterministic
            tests. It must not authenticate or call a channel.

    Returns:
        The executed turn, portable handler and package migration.

    Raises:
        ValueError: If execution is unknown or the adapter violates
            the single-message reply contract.
    """
    if execution not in {"offline", "live"}:
        message = "execution must be 'offline' or 'live'."
        raise ValueError(message)
    if execution == "live":
        return missing_configuration(
            demo=DEMO_NAME,
            technology=TECHNOLOGY,
            lane="legacy",
            provider="bot-framework",
            missing=["an authenticated channel host"],
            next_steps=[
                "Host the shared handler using Microsoft 365 Agents SDK."
            ],
        )
    adapter = port if port is not None else LocalActivityAdapter()
    activity: dict[str, object] = {
        "id": "support-pilot-message-1",
        "type": "message",
        "channelId": "local-workshop",
        "text": scenario.BRIEF,
    }
    turn = await adapter.process_activity(activity)
    if turn["handled"] is not True or len(turn["responses"]) != 1:
        message = "The adapter must handle one message with one reply."
        raise ValueError(message)
    # The handler is pure: compare its business fields while allowing
    # the adapter to add channel routing. JSON keeps bools distinct
    # from integers, so an altered approval flag cannot compare equal.
    expected = handle_activity(activity)
    reply = turn["responses"][0]
    business_fields = {name: reply.get(name) for name in expected}
    if json.dumps(business_fields, sort_keys=True) != json.dumps(
        expected, sort_keys=True
    ):
        message = "The adapter reply must preserve the shared handler output."
        raise ValueError(message)
    return result(
        demo=DEMO_NAME,
        technology=TECHNOLOGY,
        lane="legacy",
        mode="local_execution",
        status="ok",
        headline=(
            "One channel turn executed locally; the same handler can "
            "run behind the Microsoft 365 Agents adapter."
        ),
        evidence=evidence(provider="local-channel"),
        data={
            "turn": turn,
            "handler": "msai_demo.bot_framework_demo.handle_activity",
            "package_mapping": PACKAGE_MAPPING,
            "replacement": "Microsoft 365 Agents SDK",
            "why_migrate": (
                "Bot Framework's final LTS ended December 2025. "
                "Move channel hosting and authentication to the "
                "supported SDK while keeping this business handler."
            ),
            "adapter_mapping": "BotFrameworkAdapter -> CloudAdapter",
            "authentication_package": "microsoft-agents-authentication-msal",
            "source": MIGRATION_SOURCE,
            "limitations": (
                "Local application execution only: no channel JWT "
                "validation, SDK invocation or network delivery."
            ),
        },
    )

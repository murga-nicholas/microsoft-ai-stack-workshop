"""Microsoft 365 Agents SDK: current hosting for the same handler.

The GA Agents SDK replaces the retired Bot Framework SDK. This local
contract executes the business handler against a synthetic activity;
the SDK, channel authentication and aiohttp server do not run here.

Run it:

    uv run msai-demo m365-agents
    uv run msai-demo m365-agents --execution live
"""

from __future__ import annotations

from typing import Protocol

from msai_demo import scenario
from msai_demo.bot_framework_demo import handle_activity
from msai_demo.contracts import (
    DemoResult,
    evidence,
    missing_configuration,
    result,
)

DEMO_NAME = "m365-agents"
TECHNOLOGY = "Microsoft 365 Agents SDK"
FIXTURE_ID = "m365-agents-activity-v1"
SOURCE = (
    "https://learn.microsoft.com/en-us/microsoft-365/agents-sdk/"
    "bf-migration-python"
)

PACKAGE_MAP: dict[str, list[str]] = {
    "botbuilder-core": ["microsoft-agents-hosting-core"],
    "botbuilder-schema": ["microsoft-agents-activity"],
    "botbuilder-integration-aiohttp": ["microsoft-agents-hosting-aiohttp"],
    "botbuilder-azure": [
        "microsoft-agents-storage-blob",
        "microsoft-agents-storage-cosmos",
    ],
}


class ActivityPort(Protocol):
    """Supply a synthetic inbound activity without a channel server."""

    async def receive(self) -> dict[str, object]:
        """Return the activity to pass unchanged to the handler."""


class FixtureActivityPort:
    """Supply the named migration fixture without SDK dependencies."""

    async def receive(self) -> dict[str, object]:
        """Return the support-pilot request as a channel activity."""
        return {
            "type": "message",
            "id": FIXTURE_ID,
            "channelId": "workshop",
            "text": scenario.BRIEF,
        }


def hosting_contract() -> dict[str, object]:
    """Describe the verified hosting and MSAL shape without secrets."""
    prefix = "CONNECTIONS__SERVICE_CONNECTION__SETTINGS__"
    return {
        "distribution": "microsoft-agents-hosting-aiohttp==1.5.0",
        "package_map": PACKAGE_MAP,
        "additional_packages": ["microsoft-agents-authentication-msal"],
        "import_change": "microsoft.agents -> microsoft_agents",
        "startup": [
            "config = load_configuration_from_env(environ)",
            "manager = MsalConnectionManager(**config)",
            "adapter = CloudAdapter(connection_manager=manager)",
            "storage = MemoryStorage()",
            "authorization = Authorization(storage, manager, **config)",
            "app = AgentApplication[TurnState](storage=storage, "
            "adapter=adapter, authorization=authorization, **config)",
        ],
        "aiohttp": {
            "route": "POST /api/messages",
            "dispatch": "await start_agent_process(req, app, app.adapter)",
            "handler_registration": '@app.activity("message")',
            "business_handler": "handle_activity(activity)",
            "hosting_import": "microsoft_agents.hosting.aiohttp",
            "application_import": "microsoft_agents.hosting.core",
        },
        "authentication": {
            "manager": "microsoft_agents.authentication.msal",
            "environment_names": [
                prefix + "CLIENTID",
                prefix + "CLIENTSECRET",
                prefix + "TENANTID",
            ],
            "incoming_requests": "CloudAdapter validates channel JWTs.",
            "secret_values": "Never included in this result.",
        },
        "sdk_state": "SDK not installed; hosting is a contract only.",
        "sources": [
            SOURCE,
            "https://learn.microsoft.com/en-us/microsoft-365/agents-sdk/"
            "agent-application",
            "https://learn.microsoft.com/en-us/microsoft-365/agents-sdk/"
            "configure-authentication-msal",
        ],
    }


async def run_m365_agents_demo(
    *,
    execution: str = "offline",
    port: ActivityPort | None = None,
) -> DemoResult:
    """Execute the handler and explain the replacement hosting layer.

    Args:
        execution: ``offline`` or ``live``. Live hosting is not set up.
        port: Optional synthetic activity source for contract tests.

    Returns:
        Handler evidence, package migration and authentication shape.

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
            provider="microsoft-365-agents",
            missing=["Agents SDK hosting and channel registration"],
            next_steps=[
                "Install microsoft-agents-hosting-aiohttp==1.5.0 and MSAL.",
                "Configure a channel registration and an aiohttp host.",
            ],
        )
    adapter = port if port is not None else FixtureActivityPort()
    try:
        activity = await adapter.receive()
        reply = handle_activity(activity)
    except (ValueError, PermissionError) as exc:
        denied = isinstance(exc, PermissionError)
        return result(
            demo=DEMO_NAME,
            technology=TECHNOLOGY,
            lane="current",
            mode="local_contract",
            status="blocked" if denied else "error",
            headline="The local activity contract rejected the request.",
            evidence=evidence(
                provider="microsoft-365-agents", fixture_id=FIXTURE_ID
            ),
            error={
                "code": "authorization_denied" if denied else "malformed",
                "message": "Synthetic activity validation or access failed.",
            },
            data=hosting_contract(),
        )
    return result(
        demo=DEMO_NAME,
        technology=TECHNOLOGY,
        lane="current",
        mode="local_contract",
        status="ok",
        headline="The business handler runs; hosting and MSAL are contracts.",
        evidence=evidence(
            provider="microsoft-365-agents", fixture_id=FIXTURE_ID
        ),
        data={
            **hosting_contract(),
            "scenario_id": scenario.SCENARIO_ID,
            "activity": activity,
            "reply": reply,
            "handler_executed": True,
            "handler_module": handle_activity.__module__,
        },
        next_steps=["Replace only the hosting seam when migrating handlers."],
    )

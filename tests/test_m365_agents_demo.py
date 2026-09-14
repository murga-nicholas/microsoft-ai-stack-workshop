from __future__ import annotations

import asyncio
from dataclasses import dataclass

import pytest

from msai_demo import scenario
from msai_demo.bot_framework_demo import handle_activity as legacy_handler
from msai_demo.m365_agents_demo import (
    FIXTURE_ID,
    handle_activity,
    hosting_contract,
    run_m365_agents_demo,
)


@dataclass
class ActivitySource:
    activity: dict[str, object]

    async def receive(self) -> dict[str, object]:
        return self.activity


class DeniedSource:
    async def receive(self) -> dict[str, object]:
        message = "Synthetic 403; do not expose service error content."
        raise PermissionError(message)


def test_offline_handler_runs_without_the_sdk() -> None:
    output = asyncio.run(run_m365_agents_demo())
    assert output["mode"] == "local_contract"
    assert output["status"] == "ok"
    assert output["evidence"]["fixture_id"] == FIXTURE_ID
    assert not output["evidence"]["sdk_invoked"]
    assert not output["evidence"]["network_attempted"]
    data = output["data"]
    assert data is not None
    assert data["handler_executed"]
    assert data["reply"]["cost"] == scenario.price_pilot()
    assert not data["reply"]["acceptable"]
    assert "human approval" in data["reply"]["acceptance_failures"][0]
    assert data["import_change"] == "microsoft.agents -> microsoft_agents"
    assert "botbuilder-core" in data["package_map"]


def test_injected_activity_is_passed_to_shared_handler() -> None:
    assert handle_activity is legacy_handler
    activity = {"type": "message", "text": "Please cost the pilot."}
    output = asyncio.run(
        run_m365_agents_demo(port=ActivitySource(activity=activity))
    )
    assert output["data"] is not None
    assert output["data"]["reply"] == handle_activity(activity)
    assert output["data"]["activity"] == activity


@pytest.mark.parametrize(
    "activity",
    [
        {},
        {"type": ""},
        {"type": "message"},
        {"type": "message", "text": 123},
        {"type": "message", "text": "   "},
    ],
)
def test_malformed_activities_fail_closed(activity: dict[str, object]) -> None:
    output = asyncio.run(
        run_m365_agents_demo(port=ActivitySource(activity=activity))
    )
    assert output["status"] == "error"
    assert output["error"] is not None
    assert output["error"]["code"] == "malformed"


def test_denied_fixture_does_not_claim_a_remote_call() -> None:
    output = asyncio.run(run_m365_agents_demo(port=DeniedSource()))
    assert output["status"] == "blocked"
    assert output["error"] is not None
    assert output["error"]["code"] == "authorization_denied"
    assert not output["evidence"]["service_executed"]


def test_live_requires_host_and_registration_before_using_port() -> None:
    output = asyncio.run(
        run_m365_agents_demo(execution="live", port=DeniedSource())
    )
    assert output["mode"] == "not_run"
    assert output["error"] is not None
    assert output["error"]["code"] == "missing_configuration"


def test_hosting_contract_names_msals_configuration_not_values() -> None:
    data = hosting_contract()
    assert "microsoft-agents-authentication-msal" in str(data)
    assert "CONNECTIONS__SERVICE_CONNECTION__SETTINGS__CLIENTSECRET" in str(
        data
    )
    assert "AgentApplication[TurnState]" in str(data)
    assert "start_agent_process" in str(data)


def test_unknown_execution_is_rejected() -> None:
    with pytest.raises(ValueError, match="execution must"):
        asyncio.run(run_m365_agents_demo(execution="typo"))

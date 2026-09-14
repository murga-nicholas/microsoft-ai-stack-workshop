from __future__ import annotations

import asyncio
from dataclasses import dataclass, replace

import pytest

from msai_demo.entra_agent_id_demo import (
    AgentIdentityContract,
    FixtureAgentIdentityPort,
    run_entra_agent_id_demo,
    validate_agent_contract,
)


@dataclass
class ContractSource:
    contract: AgentIdentityContract

    async def read_contract(self) -> AgentIdentityContract:
        return self.contract


class DeniedSource:
    async def read_contract(self) -> AgentIdentityContract:
        message = "Synthetic Graph 403."
        raise PermissionError(message)


def test_offline_validates_contract_without_sdk_or_tokens() -> None:
    output = asyncio.run(run_entra_agent_id_demo())
    assert output["mode"] == "local_contract"
    assert output["status"] == "ok"
    assert output["evidence"]["fixture_id"] == "entra-agent-id-v1"
    assert not output["evidence"]["sdk_invoked"]
    assert not output["evidence"]["network_attempted"]
    data = output["data"]
    assert data is not None
    assert data["validation_failures"] == []
    assert "NOT an Agent ID" in data["azure_identity_demo_contrast"]
    assert data["admin_prerequisites"]
    exchange = data["token_exchange"]
    assert (
        exchange["blueprint_request"]["fmi_path"]
        == data["hierarchy"]["agent_identity"]
    )
    assert "client_assertion" not in exchange["agent_request"]


@pytest.mark.parametrize(
    ("field", "value", "expected"),
    [
        ("blueprint_id", "", "Blueprint ID"),
        ("principal_id", "", "principal required"),
        ("identity_id", "", "identity ID"),
        ("identity_type", "servicePrincipal", "ordinary application"),
        ("identity_id", "fixture-support-blueprint", "distinct objects"),
        ("parent_id", "unrelated-blueprint", "belong to"),
        ("sponsor_id", " ", "sponsor is required"),
        ("exchange_scope", "wrong-scope", "AzureADTokenExchange"),
        ("fmi_path", "other-agent", "select the child"),
        ("resource_scope", "http://resource/.default", "HTTPS"),
        ("resource_scope", "https://resource/wrong", "HTTPS"),
    ],
)
def test_invalid_relationships_are_reported(
    field: str, value: str, expected: str
) -> None:
    contract = asyncio.run(FixtureAgentIdentityPort().read_contract())
    broken = replace(contract, **{field: value})
    failures = validate_agent_contract(broken)
    assert any(expected in failure for failure in failures)
    output = asyncio.run(
        run_entra_agent_id_demo(port=ContractSource(contract=broken))
    )
    assert output["status"] == "blocked"
    assert output["error"] is not None
    assert output["error"]["code"] == "invalid_contract"


def test_disabled_agent_cannot_pass_token_exchange_preconditions() -> None:
    contract = asyncio.run(FixtureAgentIdentityPort().read_contract())
    disabled = replace(contract, enabled=False)
    assert "disabled" in " ".join(validate_agent_contract(disabled))


def test_injected_valid_contract_executes() -> None:
    contract = asyncio.run(FixtureAgentIdentityPort().read_contract())
    output = asyncio.run(
        run_entra_agent_id_demo(port=ContractSource(contract=contract))
    )
    assert output["status"] == "ok"


def test_denied_fixture_is_an_honest_local_contract() -> None:
    output = asyncio.run(run_entra_agent_id_demo(port=DeniedSource()))
    assert output["status"] == "blocked"
    assert output["error"] is not None
    assert output["error"]["code"] == "authorization_denied"
    assert not output["evidence"]["service_executed"]


def test_live_never_reuses_ordinary_app_credentials_as_an_agent_id() -> None:
    output = asyncio.run(
        run_entra_agent_id_demo(execution="live", port=DeniedSource())
    )
    assert output["mode"] == "not_run"
    assert output["error"] is not None
    assert output["error"]["code"] == "missing_configuration"
    assert "blueprint" in " ".join(output["next_steps"])


def test_unknown_execution_is_rejected() -> None:
    with pytest.raises(ValueError, match="execution must"):
        asyncio.run(run_entra_agent_id_demo(execution="typo"))

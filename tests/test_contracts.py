"""Check the shared result contract and its evidence invariants.

Run it:

    uv run pytest tests/test_contracts.py
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from msai_demo import contracts

if TYPE_CHECKING:
    from msai_demo.contracts import DemoResult, Evidence, Mode, Status


def _result(
    *,
    mode: Mode = "local_execution",
    status: Status = "ok",
    record: Evidence | None = None,
) -> DemoResult:
    return contracts.result(
        demo="contract-test",
        technology="Python",
        lane="shared",
        mode=mode,
        status=status,
        headline="Check the result envelope.",
        evidence=record or contracts.evidence(provider="offline"),
    )


def test_evidence_defaults_make_no_execution_claims() -> None:
    assert contracts.evidence(provider="offline") == {
        "provider": "offline",
        "sdk_invoked": False,
        "network_attempted": False,
        "service_executed": False,
        "fixture_id": None,
        "requested_model": None,
        "observed_model": None,
    }


def test_evidence_preserves_explicit_observations() -> None:
    record = contracts.evidence(
        provider="fixture",
        sdk_invoked=True,
        network_attempted=True,
        service_executed=True,
        fixture_id="response-v1",
        requested_model="requested-model",
        observed_model="observed-model",
    )

    assert record == {
        "provider": "fixture",
        "sdk_invoked": True,
        "network_attempted": True,
        "service_executed": True,
        "fixture_id": "response-v1",
        "requested_model": "requested-model",
        "observed_model": "observed-model",
    }


def test_result_has_a_complete_default_envelope() -> None:
    assert _result() == {
        "schema_version": contracts.SCHEMA_VERSION,
        "demo": "contract-test",
        "technology": "Python",
        "lane": "shared",
        "mode": "local_execution",
        "status": "ok",
        "headline": "Check the result envelope.",
        "evidence": contracts.evidence(provider="offline"),
        "data": None,
        "error": None,
        "next_steps": [],
    }


@pytest.mark.parametrize(
    "mode", ["live_model", "live_identity", "live_service"]
)
def test_live_mode_requires_a_network_attempt(mode: Mode) -> None:
    with pytest.raises(ValueError, match="no network was attempted"):
        _result(mode=mode)

    record = contracts.evidence(
        provider="transport-fixture", network_attempted=True
    )
    envelope = _result(mode=mode, status="blocked", record=record)
    assert envelope["mode"] == mode
    assert envelope["evidence"]["service_executed"] is False


@pytest.mark.parametrize(
    "mode", ["local_execution", "local_contract", "not_run", "batch"]
)
def test_non_live_mode_rejects_remote_execution(mode: Mode) -> None:
    record = contracts.evidence(
        provider="offline", service_executed=True, fixture_id="response-v1"
    )
    with pytest.raises(ValueError, match="cannot claim a service executed"):
        _result(mode=mode, record=record)


def test_synthetic_results_must_identify_the_fixture() -> None:
    with pytest.raises(ValueError, match="must name its fixture_id"):
        _result(mode="local_contract")

    envelope = _result(
        mode="local_contract",
        record=contracts.evidence(provider="offline", fixture_id="test-v1"),
    )
    assert envelope["evidence"]["fixture_id"] == "test-v1"


@pytest.mark.parametrize("status", ["ok", "paused", "blocked", "error"])
def test_batch_preserves_children_and_aggregates_failures(
    status: Status,
) -> None:
    child = _result(status=status)
    children = [_result(), child]
    envelope = contracts.batch(
        demo="all", headline="All child results.", children=children
    )

    failed = status in {"blocked", "error"}
    assert envelope["mode"] == "batch"
    assert envelope["status"] == ("error" if failed else "ok")
    assert envelope["children"] == children
    assert envelope["data"] == {
        "total": 2,
        "failed": [child["demo"]] if failed else [],
    }
    assert envelope["evidence"] == contracts.evidence(provider="none")


def test_empty_batch_is_successful() -> None:
    envelope = contracts.batch(demo="all", headline="Empty.", children=[])

    assert envelope["status"] == "ok"
    assert envelope["children"] == []
    assert envelope["data"] == {"total": 0, "failed": []}


def test_missing_configuration_names_prerequisites_without_claims() -> None:
    envelope = contracts.missing_configuration(
        demo="configuration-test",
        technology="Test client",
        lane="current",
        provider="test-provider",
        missing=["FIRST_SETTING", "SECOND_SETTING"],
        next_steps=["Configure both settings."],
    )

    assert envelope["demo"] == "configuration-test"
    assert envelope["lane"] == "current"
    assert envelope["mode"] == "not_run"
    assert envelope["status"] == "blocked"
    assert envelope["headline"] == (
        "Test client needs FIRST_SETTING, SECOND_SETTING."
    )
    assert envelope["error"] == {
        "code": "missing_configuration",
        "message": "Set FIRST_SETTING, SECOND_SETTING to run the live path.",
    }
    assert envelope["next_steps"] == ["Configure both settings."]
    assert envelope["data"] is None
    assert envelope["evidence"] == contracts.evidence(provider="test-provider")


def test_result_retains_data_error_and_next_steps() -> None:
    envelope = contracts.result(
        demo="contract-test",
        technology="Test client",
        lane="legacy",
        mode="local_execution",
        status="error",
        headline="The local validation failed.",
        evidence=contracts.evidence(provider="offline"),
        data={"valid": False},
        error={"code": "validation", "message": "Invalid proposal."},
        next_steps=["Revise the proposal."],
    )

    assert envelope["data"] == {"valid": False}
    assert envelope["error"] == {
        "code": "validation",
        "message": "Invalid proposal.",
    }
    assert envelope["next_steps"] == ["Revise the proposal."]

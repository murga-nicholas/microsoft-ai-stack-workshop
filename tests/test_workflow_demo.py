from __future__ import annotations

import asyncio
from dataclasses import replace

import pytest

from msai_demo import scenario
from msai_demo.offline import ScriptedChatClient
from msai_demo.providers import create_chat_client
from msai_demo.workflow_demo import (
    Proposal,
    ScriptedDraftPort,
    run_workflow_demo,
)


def test_default_offline_run_pauses_and_resumes_real_graph() -> None:
    outcome = asyncio.run(run_workflow_demo())
    assert outcome["mode"] == "local_execution"
    assert outcome["status"] == "ok"
    assert outcome["evidence"]["sdk_invoked"]
    assert not outcome["evidence"]["network_attempted"]
    data = outcome["data"]
    assert data is not None
    assert data["paused_for_approval"]
    assert data["outputs_before_approval"] == 0
    assert data["outputs_after_resume"] == 1
    assert data["restored"]
    assert data["accepted"]
    assert data["proposal"]["cost"] == scenario.price_pilot()
    assert data["proposal"]["approved"]
    assert not data["proposal"]["revised"]
    assert data["storage"] == "InMemoryCheckpointStorage"
    assert data["checkpoint_count"] > 0
    assert data["checkpoint_id"]
    assert data["usage"] is None
    for edge in (
        "draft --> review",
        "review --> approve",
        "review --> revise",
        "approve --> accept",
        "revise --> accept",
    ):
        assert edge in data["graph"]


def test_injected_scripted_client_still_runs_local_with_live_flag() -> None:
    client = ScriptedChatClient(replies=["A scoped and grounded pilot."])
    port = ScriptedDraftPort(client)
    outcome = asyncio.run(run_workflow_demo(execution="live", port=port))
    assert client.turns == 1
    assert outcome["mode"] == "local_execution"
    assert outcome["data"] is not None
    assert outcome["data"]["proposal"]["text"] == (
        "A scoped and grounded pilot."
    )


@pytest.mark.parametrize(
    ("sources", "team"),
    [
        ((), None),
        (("agent-framework-overview",), {"python-engineer": 3.0}),
    ],
)
def test_revision_is_costed_before_the_human_approves(
    sources: tuple[str, ...], team: dict[str, float] | None
) -> None:
    client = create_chat_client("offline", replies=["Draft to revise."])
    port = ScriptedDraftPort(client, cited_sources=sources, team=team)
    outcome = asyncio.run(run_workflow_demo(port=port, decided_by="Ada"))
    data = outcome["data"]
    assert data is not None
    assert data["accepted"]
    assert data["proposal"]["revised"]
    assert data["proposal"]["cost"] == scenario.price_pilot()
    assert data["proposal"]["cited_sources"] == ["agent-framework-overview"]
    assert data["proposal"]["decided_by"] == "Ada"
    assert "Revised scope" in data["proposal"]["text"]


@pytest.mark.parametrize(
    ("approve", "decided_by"), [(False, "Ada"), (True, "  ")]
)
def test_acceptance_requires_an_approval_and_a_name(
    approve: bool, decided_by: str
) -> None:
    outcome = asyncio.run(
        run_workflow_demo(approve=approve, decided_by=decided_by)
    )
    assert outcome["status"] == "blocked"
    data = outcome["data"]
    assert data is not None
    assert not data["accepted"]
    assert data["restored"]
    assert data["failures"] == ["No human approval recorded."]


def test_no_decision_leaves_the_real_workflow_paused() -> None:
    outcome = asyncio.run(run_workflow_demo(approve=None))
    assert outcome["status"] == "paused"
    data = outcome["data"]
    assert data is not None
    assert not data["restored"]
    assert not data["accepted"]
    assert not data["proposal"]["approved"]
    assert data["outputs_before_approval"] == 0


class _SelfApprovingPort(ScriptedDraftPort):
    async def draft(self, brief: str) -> Proposal:
        proposal = await super().draft(brief)
        return replace(proposal, approved=True, decided_by="model")


def test_a_draft_cannot_supply_its_own_approval() -> None:
    outcome = asyncio.run(
        run_workflow_demo(port=_SelfApprovingPort(), approve=None)
    )
    assert outcome["data"] is not None
    assert not outcome["data"]["proposal"]["approved"]
    assert outcome["data"]["proposal"]["decided_by"] == ""


class _UnavailablePort(ScriptedDraftPort):
    def check_available(self) -> None:
        message = "Optional framework runtime is unavailable."
        raise ModuleNotFoundError(message)


def test_missing_sdk_returns_an_explicit_contract_without_fake_resume() -> (
    None
):
    outcome = asyncio.run(run_workflow_demo(port=_UnavailablePort()))
    assert outcome["mode"] == "local_contract"
    assert outcome["status"] == "blocked"
    assert outcome["evidence"]["fixture_id"] == "workflow-missing-sdk-v1"
    assert not outcome["evidence"]["sdk_invoked"]
    assert outcome["error"] is not None
    assert outcome["error"]["code"] == "missing_sdk"
    assert outcome["data"] is not None
    assert not outcome["data"]["restored"]
    assert outcome["data"]["cost"] == scenario.price_pilot()


def test_empty_model_output_is_a_malformed_response() -> None:
    port = ScriptedDraftPort(create_chat_client("offline", replies=["  "]))
    outcome = asyncio.run(run_workflow_demo(port=port))
    assert outcome["status"] == "error"
    assert outcome["error"] is not None
    assert outcome["error"]["code"] == "malformed_response"
    assert outcome["evidence"]["sdk_invoked"]


class _FailingPort(ScriptedDraftPort):
    def __init__(self, error_type: type[Exception]) -> None:
        super().__init__()
        self.error_type = error_type

    async def draft(self, brief: str) -> Proposal:
        del brief
        message = "Private adapter details must not appear in the result."
        raise self.error_type(message)


@pytest.mark.parametrize(
    ("error_type", "code", "status"),
    [
        (PermissionError, "authorization_denied", "blocked"),
        (TimeoutError, "timeout", "error"),
    ],
)
def test_known_local_adapter_failures_are_structured(
    error_type: type[Exception], code: str, status: str
) -> None:
    outcome = asyncio.run(run_workflow_demo(port=_FailingPort(error_type)))
    assert outcome["status"] == status
    assert outcome["mode"] == "local_execution"
    assert outcome["error"] is not None
    assert outcome["error"]["code"] == code
    assert "Private adapter details" not in str(outcome)


def test_unknown_errors_are_not_manufactured_into_success() -> None:
    with pytest.raises(RuntimeError, match="Private adapter details"):
        asyncio.run(run_workflow_demo(port=_FailingPort(RuntimeError)))


def test_unknown_execution_value_is_rejected() -> None:
    with pytest.raises(ValueError, match="execution must be"):
        asyncio.run(run_workflow_demo(execution="typo"))

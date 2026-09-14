from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import pytest

from msai_demo import scenario
from msai_demo.contracts import Evidence, Mode, evidence
from msai_demo.harness_demo import (
    WORKSPACE_ROOT,
    FrameworkHarnessPort,
    HarnessRun,
    MalformedHarnessResponseError,
    _validate_observed,
    _workspace_directory,
    offline_tool_plan,
    run_harness_demo,
)
from msai_demo.offline import ScriptedChatClient
from msai_demo.providers import create_chat_client
from msai_demo.runtime import REPO_ROOT

if TYPE_CHECKING:
    from pathlib import Path


@dataclass
class FailingPort:
    failure: Exception
    provider: str = "injected-boundary"
    mode: Mode = "local_execution"
    configured: bool = True
    record: Evidence = field(
        default_factory=lambda: evidence(provider="injected-boundary")
    )

    async def run(
        self, directory: Path, *, max_iterations: int, max_model_calls: int
    ) -> HarnessRun:
        del directory, max_iterations, max_model_calls
        raise self.failure


class HttpFailureError(Exception):
    def __init__(self, status_code: int) -> None:
        super().__init__("Private provider details must never be returned.")
        self.status_code = status_code


def test_offline_harness_executes_memory_todos_and_approval() -> None:
    before = set(WORKSPACE_ROOT.glob("harness-*"))
    envelope = asyncio.run(run_harness_demo())
    assert envelope["mode"] == "local_execution"
    assert envelope["status"] == "paused"
    assert envelope["evidence"]["sdk_invoked"] is True
    assert envelope["evidence"]["network_attempted"] is False
    payload = envelope["data"]
    assert payload is not None
    assert payload["todos"] == [
        {"title": "Draft the pilot proposal", "complete": True},
        {"title": "Obtain named human approval", "complete": False},
    ]
    assert payload["operating_mode"] == "plan"
    assert payload["pending_tools"] == ["file_access_write"]
    assert payload["shared_write_executed"] is False
    assert payload["model_calls"] == len(offline_tool_plan())
    assert payload["cost"] == scenario.price_pilot()
    assert payload["accepted"] is False
    assert payload["usage"] is None
    assert json.loads(payload["memory"]) == {
        "scenario_id": scenario.SCENARIO_ID,
        "cost": scenario.price_pilot(),
        "human_approved": False,
        "milestones": scenario.plan_summary(),
        "source": "agent-framework-overview",
    }
    assert "session_file_memory" in payload["capabilities"]["enabled"]
    assert "compaction" in payload["capabilities"]["disabled"]
    assert payload["approval_defaults"]["shared_file_read_and_write"] == (
        "always_require"
    )
    assert payload["workspace_cleaned"] is True
    assert set(WORKSPACE_ROOT.glob("harness-*")) == before


def test_scripted_provider_can_be_injected_without_framework_mocks() -> None:
    client = create_chat_client(
        "offline", replies=["Await approval."], tool_plan=offline_tool_plan()
    )
    assert isinstance(client, ScriptedChatClient)
    port = FrameworkHarnessPort(client=client)
    envelope = asyncio.run(run_harness_demo(port=port))
    assert envelope["status"] == "paused"
    assert client.turns == 6


@pytest.mark.parametrize(
    ("execution", "max_iterations", "max_model_calls"),
    [("typo", 3, 12), ("offline", 0, 12), ("offline", 3, 0)],
)
def test_invalid_execution_and_budgets_fail_before_running(
    execution: str, max_iterations: int, max_model_calls: int
) -> None:
    with pytest.raises(ValueError):
        asyncio.run(
            run_harness_demo(
                execution=execution,
                max_iterations=max_iterations,
                max_model_calls=max_model_calls,
            )
        )


def test_missing_configuration_does_not_construct_a_live_client() -> None:
    port = FrameworkHarnessPort(provider="openai", configured=False)
    envelope = asyncio.run(run_harness_demo(execution="live", port=port))
    assert envelope["mode"] == "not_run"
    assert envelope["status"] == "blocked"
    assert envelope["error"] is not None
    assert envelope["error"]["code"] == "missing_configuration"
    assert envelope["evidence"]["network_attempted"] is False


def test_missing_sdk_retains_only_an_explicit_scenario_contract() -> None:
    envelope = asyncio.run(
        run_harness_demo(port=FailingPort(ModuleNotFoundError("SDK absent")))
    )
    assert envelope["mode"] == "local_contract"
    assert envelope["status"] == "blocked"
    assert envelope["evidence"]["sdk_invoked"] is False
    assert envelope["evidence"]["fixture_id"] == "harness-contract-v1"
    assert envelope["data"] is not None
    assert envelope["data"]["cost"] == scenario.price_pilot()
    assert envelope["data"]["capabilities"]["enabled"] == []


@pytest.mark.parametrize(
    ("failure", "expected_code", "expected_status"),
    [
        (HttpFailureError(401), "authorization_denied", "blocked"),
        (HttpFailureError(403), "authorization_denied", "blocked"),
        (HttpFailureError(429), "throttled", "error"),
        (TimeoutError("private timeout details"), "timeout", "error"),
    ],
)
def test_known_boundary_failures_are_safe_and_structured(
    failure: Exception, expected_code: str, expected_status: str
) -> None:
    port = FailingPort(
        failure,
        mode="live_model",
        record=evidence(provider="injected-boundary", network_attempted=True),
    )
    envelope = asyncio.run(run_harness_demo(port=port))
    assert envelope["mode"] == "live_model"
    assert envelope["status"] == expected_status
    assert envelope["error"] is not None
    assert envelope["error"]["code"] == expected_code
    assert "private" not in str(envelope).lower()


def test_unrecognized_errors_are_not_manufactured_success() -> None:
    with pytest.raises(RuntimeError, match="application defect"):
        asyncio.run(
            run_harness_demo(
                port=FailingPort(RuntimeError("application defect"))
            )
        )


def test_wrapped_403_keeps_the_authorization_boundary() -> None:
    wrapped = RuntimeError("Provider wrapper")
    wrapped.__cause__ = HttpFailureError(403)
    envelope = asyncio.run(run_harness_demo(port=FailingPort(wrapped)))
    assert envelope["status"] == "blocked"
    assert envelope["error"] is not None
    assert envelope["error"]["code"] == "authorization_denied"


def test_runaway_tool_loop_is_bounded_before_another_model_call() -> None:
    client = ScriptedChatClient(tool_plan=offline_tool_plan())
    envelope = asyncio.run(
        run_harness_demo(
            port=FrameworkHarnessPort(client=client), max_model_calls=1
        )
    )
    assert envelope["status"] == "error"
    assert envelope["error"] is not None
    assert envelope["error"]["code"] == "iteration_limit"
    assert client.turns == 1


def test_harness_iteration_cap_handles_a_model_that_never_finishes() -> None:
    client = ScriptedChatClient(replies=["Still working."])
    envelope = asyncio.run(
        run_harness_demo(
            port=FrameworkHarnessPort(client=client), max_iterations=2
        )
    )
    assert envelope["status"] == "error"
    assert envelope["error"] is not None
    assert envelope["error"]["code"] == "iteration_limit"
    assert client.turns == 2


def test_pending_approval_without_memory_is_malformed() -> None:
    client = ScriptedChatClient(
        tool_plan=[
            (
                "file_access_write",
                {"file_name": "proposal.md", "content": "Missing plan."},
            )
        ]
    )
    envelope = asyncio.run(
        run_harness_demo(port=FrameworkHarnessPort(client=client))
    )
    assert envelope["status"] == "error"
    assert envelope["error"] is not None
    assert envelope["error"]["code"] == "malformed_response"


@pytest.mark.parametrize("broken", ["todos", "pending_tools", "write"])
def test_observed_state_cannot_claim_an_unproven_approval(broken: str) -> None:
    observed: HarnessRun = {
        "operating_mode": "plan",
        "todos": [{"title": "Approval", "complete": False}],
        "memory": "Plan",
        "pending_tools": ["file_access_write"],
        "model_calls": 1,
        "shared_write_executed": False,
    }
    if broken == "todos":
        observed["todos"] = []
    elif broken == "pending_tools":
        observed["pending_tools"] = ["unexpected"]
    else:
        observed["shared_write_executed"] = True
    with pytest.raises(MalformedHarnessResponseError):
        _validate_observed(observed)


def test_workspace_rejects_paths_outside_the_disposable_root() -> None:
    with pytest.raises(ValueError, match=r"inside \.msai_workspace"):
        _workspace_directory(REPO_ROOT / "src")


@pytest.mark.parametrize(
    "memory", ["not JSON", "[]", "{}", '{"human_approved":true}']
)
def test_malformed_memory_is_rejected_after_real_tool_calls(
    memory: str,
) -> None:
    plan = list(offline_tool_plan())
    plan[2] = (
        "file_memory_write",
        {"file_name": "pilot-plan.md", "content": memory},
    )
    client = ScriptedChatClient(tool_plan=plan)
    envelope = asyncio.run(
        run_harness_demo(port=FrameworkHarnessPort(client=client))
    )
    assert envelope["status"] == "error"
    assert envelope["error"] is not None
    assert envelope["error"]["code"] == "malformed_response"


def test_invented_human_approval_in_memory_is_rejected() -> None:
    memory = json.dumps(
        {"cost": scenario.price_pilot(), "human_approved": True}
    )
    test_malformed_memory_is_rejected_after_real_tool_calls(memory)


def test_http_timeout_survives_the_provider_wrapper() -> None:
    import httpx2

    request = httpx2.Request("POST", "https://example.invalid/model")
    wrapped = RuntimeError("Provider wrapper")
    wrapped.__cause__ = httpx2.ReadTimeout("Timed out", request=request)
    envelope = asyncio.run(run_harness_demo(port=FailingPort(wrapped)))
    assert envelope["error"] is not None
    assert envelope["error"]["code"] == "timeout"

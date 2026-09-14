"""Verify AutoGen's application-owned approval and process recovery.

Run it:
    uv run pytest tests/test_autogen_demo.py
"""

from __future__ import annotations

import asyncio
import json
import os
from importlib import metadata
from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

import pytest

from msai_demo import autogen_demo as demo
from msai_demo import scenario
from msai_demo.resume_worker import ResumeError, ResumeResult, write_json

if TYPE_CHECKING:
    from collections.abc import Mapping

    from autogen_core.models import ChatCompletionClient

    from msai_demo.contracts import Mode


@pytest.fixture(autouse=True)
def isolated_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("ENABLE_INSTRUMENTATION", "false")


class FixtureTeam:
    def __init__(
        self,
        *,
        proposal: str | None = None,
        stop_reason: str = "APPROVE",
        restore: bool = True,
    ) -> None:
        self.proposal = proposal or demo.offline_script()[0]
        self.stop_reason = stop_reason
        self.restore = restore
        self.state: Mapping[str, Any] = {"portable": "fixture"}

    async def run(self, *, task: str) -> SimpleNamespace:
        assert scenario.BRIEF in task
        messages = [
            SimpleNamespace(source="user"),
            SimpleNamespace(source=""),
            SimpleNamespace(
                source=demo.ARCHITECT,
                to_text=lambda: self.proposal,
                models_usage=SimpleNamespace(
                    prompt_tokens=3, completion_tokens=4
                ),
            ),
            SimpleNamespace(source=demo.REVIEWER),
        ]
        return SimpleNamespace(messages=messages, stop_reason=self.stop_reason)

    async def save_state(self) -> Mapping[str, Any]:
        return self.state

    async def load_state(self, state: Mapping[str, Any]) -> None:
        self.state = state if self.restore else {"different": "state"}


class FixturePort:
    sdk_invoked = False

    def __init__(
        self,
        *,
        mode: Mode = "local_contract",
        team: FixtureTeam | None = None,
        failure: Exception | None = None,
    ) -> None:
        self.mode = mode
        self.team = team or FixtureTeam()
        self.failure = failure
        self.closed = False
        self.built = 0

    def build_team(self, *, max_turns: int) -> demo.TeamPort:
        assert max_turns > 0
        self.built += 1
        if self.failure:
            raise self.failure
        return self.team

    async def close(self) -> None:
        self.closed = True


class InProcessResume:
    """Exercise worker code locally without claiming a different PID."""

    async def resume(
        self, directory: Path, approve: bool, *, execution: str
    ) -> ResumeResult:
        return await demo.resume_autogen(
            directory, approve, execution, port=FixturePort()
        )


class FailingResume:
    async def resume(
        self, directory: Path, approve: bool, *, execution: str
    ) -> ResumeResult:
        del directory, approve, execution
        code = "resume_worker_failed"
        raise ResumeError(code)


def _tool_clients() -> tuple[ChatCompletionClient, ChatCompletionClient]:
    from autogen_core import FunctionCall
    from autogen_core.models import CreateResult, ModelInfo, RequestUsage
    from autogen_ext.models.replay import ReplayChatCompletionClient

    info = ModelInfo(
        vision=False,
        function_calling=True,
        json_output=False,
        family="unknown",
        structured_output=False,
    )
    pricing = CreateResult(
        finish_reason="function_calls",
        content=[
            FunctionCall(
                id="pricing-1",
                name="price_support_pilot",
                arguments=json.dumps({"weeks": scenario.PILOT_WEEKS}),
            )
        ],
        usage=RequestUsage(prompt_tokens=7, completion_tokens=3),
        cached=True,
    )
    return (
        ReplayChatCompletionClient([pricing], model_info=info),
        ReplayChatCompletionClient([demo.offline_script()[1]]),
    )


def _turn(text: str, speaker: str = demo.ARCHITECT) -> scenario.ProposalTurn:
    return {
        "index": 0,
        "speaker": speaker,
        "provider": "offline",
        "model": "fixture",
        "text": text,
        "source_event": "fixture",
        "usage": None,
    }


async def _prepare(directory: Path) -> str:
    port = demo.SDKPort("offline")
    try:
        team = port.build_team(max_turns=4)
        await team.run(task=scenario.BRIEF)
        checkpoint_id = await demo.save_team_state(team, directory)
    finally:
        await port.close()
    write_json(
        directory / "run.json",
        {"implementation": "autogen", "execution": "offline", "max_turns": 4},
    )
    demo.save_pending_approval(
        directory, scenario.pilot_proposal(), checkpoint_id
    )
    scenario.EventStore(directory).append("gate_reached")
    return checkpoint_id


def test_version_reader_covers_missing_distribution() -> None:
    def missing(distribution: str) -> str:
        raise metadata.PackageNotFoundError(distribution)

    assert demo.autogen_version() == metadata.version("autogen-agentchat")
    assert demo.autogen_version(reader=missing) == "not installed"


@pytest.mark.parametrize("weeks", [scenario.PILOT_WEEKS, 2])
def test_pricing_tool_uses_shared_rate_card(weeks: int) -> None:
    assert json.loads(
        demo.build_pricing_tool()(weeks)
    ) == scenario.price_pilot(weeks=weeks)


def test_offline_clients_emit_complete_proposal_and_review() -> None:
    from autogen_core.models import UserMessage

    async def exercise() -> None:
        clients = demo.build_offline_clients()
        for client, reply in zip(clients, demo.offline_script(), strict=True):
            assert client.model_info["function_calling"] is False
            response = await client.create(
                [UserMessage(content=scenario.BRIEF, source="user")]
            )
            assert response.content == reply
            await client.close()

    asyncio.run(exercise())
    assert json.loads(demo.offline_script()[0]) == scenario.pilot_proposal()


@pytest.mark.parametrize("with_tools", [False, True])
def test_real_team_and_pricing_tool(with_tools: bool, tmp_path: Path) -> None:
    async def exercise() -> None:
        clients = (
            _tool_clients() if with_tools else demo.build_offline_clients()
        )
        team = demo.build_autogen_team(
            architect_client=clients[0],
            reviewer_client=clients[1],
            with_tools=with_tools,
        )
        turns, reason = await demo.collect_turns(
            team,
            scenario.BRIEF,
            openai_model="architect",
            anthropic_model="reviewer",
        )
        assert "APPROVE" in reason
        assert turns[0]["speaker"] == demo.ARCHITECT
        assert turns[-1]["speaker"] == demo.REVIEWER
        if with_tools:
            assert turns[0]["usage"] == {"input_tokens": 7, "output_tokens": 3}
            assert any(
                str(scenario.price_pilot()["total"]) in turn["text"]
                for turn in turns
            )
            run = await demo._finish_run(
                team,
                tmp_path,
                InProcessResume(),
                turns=turns,
                stop_reason=reason,
                approve=True,
                execution="offline",
                max_turns=4,
                model_a="architect",
                model_r="reviewer",
            )
            assert run["tool_calling"] == "exercised"
        else:
            assert (
                demo._proposal_from_turns(turns) == scenario.pilot_proposal()
            )
        for client in clients:
            await client.close()

    asyncio.run(exercise())


def test_sparse_messages_and_absent_usage_are_preserved() -> None:
    turns, _ = asyncio.run(
        demo.collect_turns(
            FixtureTeam(),
            scenario.BRIEF,
            openai_model="architect",
            anthropic_model="reviewer",
        )
    )
    assert len(turns) == 2
    assert turns[0]["usage"] == {"input_tokens": 3, "output_tokens": 4}
    assert turns[1]["usage"] is None
    assert turns[1]["text"].startswith("namespace(")
    assert (
        demo._usage_of(SimpleNamespace(models_usage=SimpleNamespace())) is None
    )
    assert (
        demo._usage_of(
            SimpleNamespace(models_usage=SimpleNamespace(prompt_tokens=1))
        )
        is None
    )


@pytest.mark.parametrize("payload", ["invalid json", "[]", "null"])
def test_proposal_parser_rejects_invalid_architect_content(
    payload: str,
) -> None:
    assert (
        demo._proposal_from_turns([_turn("{}", demo.REVIEWER), _turn(payload)])
        == {}
    )


@pytest.mark.parametrize("approve", [False, True])
def test_runner_crosses_real_process_boundary_twice(
    tmp_path: Path,
    approve: bool,
) -> None:
    envelope = asyncio.run(
        demo.run_autogen_demo(approve=approve, checkpoint_dir=tmp_path)
    )
    assert envelope["mode"] == "local_contract"
    assert envelope["status"] == "ok"
    assert envelope["evidence"]["sdk_invoked"] is True
    assert envelope["evidence"]["fixture_id"] == demo.FIXTURE_ID
    run = envelope["data"]
    assert run is not None
    recovery = run["recovery"]
    assert recovery["parent_pid"] == os.getpid()
    assert recovery["resume_pid"] != os.getpid()
    assert recovery["second_resume_pid"] != os.getpid()
    assert recovery["second_resume_action_count"] == 0
    assert len(run["actions"]) == int(approve)
    assert run["checks"]["acceptable"] is approve
    for name in (
        "schema_valid",
        "sources_valid",
        "no_action_before_approval",
        "one_action_after_resume",
        "survived_process_boundary",
        "idempotent_second_resume",
    ):
        assert run["checks"][name] is True
    assert {Path(path).name for path in recovery["files_read"]} >= {
        "run.json",
        "team-state.json",
        "pending-approval.json",
    }
    directory = Path(recovery["run_directory"])
    assert directory.is_dir()
    pending = json.loads(
        (directory / "pending-approval.json").read_text("utf-8")
    )
    assert pending["proposal"] == run["proposal"] == scenario.pilot_proposal()
    assert pending["checkpoint_id"] == recovery["checkpoint_id"]
    assert run["application_owned"]
    assert run["tool_calling"].startswith("not exercised:")


@pytest.mark.parametrize("approve", [False, True])
def test_resume_loads_a_new_real_team_and_deduplicates(
    tmp_path: Path, approve: bool
) -> None:
    async def exercise() -> None:
        checkpoint = await _prepare(tmp_path)
        first = await demo.resume_autogen(tmp_path, approve, "offline")
        second = await demo.resume_autogen(tmp_path, approve, "offline")
        assert first["restored"] and second["restored"]
        assert first["checkpoint_id"] == second["checkpoint_id"] == checkpoint
        assert len(first["actions"]) == int(approve)
        assert second["actions"] == []
        assert first["pid"] == os.getpid()

    asyncio.run(exercise())


@pytest.mark.parametrize("problem", ["proposal", "checkpoint", "restored"])
def test_resume_refuses_invalid_disk_state(
    tmp_path: Path, problem: str
) -> None:
    async def exercise() -> None:
        await _prepare(tmp_path)
        pending_path = tmp_path / "pending-approval.json"
        pending = json.loads(pending_path.read_text("utf-8"))
        if problem == "proposal":
            pending["proposal"] = []
        elif problem == "checkpoint":
            pending["checkpoint_id"] = "different-file"
        write_json(pending_path, pending)
        port = FixturePort(team=FixtureTeam(restore=problem != "restored"))
        with pytest.raises((TypeError, ValueError)):
            await demo.resume_autogen(tmp_path, True, "offline", port=port)
        assert scenario.EventStore(tmp_path).actions() == []

    asyncio.run(exercise())


@pytest.mark.parametrize("mode", ["local_contract", "live_model"])
def test_injected_ports_do_not_fabricate_a_process_boundary(
    tmp_path: Path, mode: Mode
) -> None:
    port = FixturePort(mode=mode)
    envelope = asyncio.run(
        demo.run_autogen_demo(
            execution="live",
            port=port,
            resume_port=InProcessResume(),
            checkpoint_dir=tmp_path,
        )
    )
    assert port.closed
    assert envelope["mode"] == mode
    assert envelope["data"] is not None
    assert envelope["data"]["checks"]["survived_process_boundary"] is False
    assert envelope["data"]["checks"]["idempotent_second_resume"] is False


@pytest.mark.parametrize(
    "proposal",
    [
        "invalid",
        '{"scope":"incomplete"}',
        json.dumps(
            {
                **scenario.pilot_proposal(),
                "cited_sections": ["invented-section"],
            }
        ),
    ],
)
def test_invalid_proposal_never_executes_action(
    tmp_path: Path, proposal: str
) -> None:
    port = FixturePort(team=FixtureTeam(proposal=proposal))
    envelope = asyncio.run(
        demo.run_autogen_demo(
            port=port, resume_port=InProcessResume(), checkpoint_dir=tmp_path
        )
    )
    assert envelope["status"] == "blocked"
    assert envelope["data"] is not None
    assert envelope["data"]["actions"] == []
    assert envelope["data"]["checks"]["acceptable"] is False


def test_turn_limit_does_not_claim_approval(tmp_path: Path) -> None:
    port = FixturePort(team=FixtureTeam(stop_reason="turn limit"))
    envelope = asyncio.run(
        demo.run_autogen_demo(port=port, checkpoint_dir=tmp_path)
    )
    assert envelope["status"] == "paused"
    assert envelope["data"] is not None
    assert envelope["data"]["checks"]["acceptable"] is False
    assert envelope["data"]["checks"]["paused_for_approval"] is False
    assert envelope["data"]["actions"] == []


@pytest.mark.parametrize(
    "present", [None, "OPENAI_API_KEY", "ANTHROPIC_API_KEY"]
)
def test_live_preflight_stops_without_both_keys(
    monkeypatch: pytest.MonkeyPatch, present: str | None
) -> None:
    if present:
        monkeypatch.setenv(present, "synthetic-test-key")
    envelope = asyncio.run(demo.run_autogen_demo(execution="live"))
    assert envelope["mode"] == "not_run"
    assert envelope["error"] is not None
    assert envelope["error"]["code"] == "missing_configuration"
    assert "synthetic-test-key" not in json.dumps(envelope)


def test_configured_live_team_stops_before_model_call_at_one_message(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-test-key")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "synthetic-test-key")
    envelope = asyncio.run(
        demo.run_autogen_demo(
            execution="live", max_turns=1, checkpoint_dir=tmp_path
        )
    )
    assert envelope["mode"] == "local_execution"
    assert envelope["status"] == "paused"
    assert envelope["evidence"]["network_attempted"] is False


def test_missing_sdk_returns_honest_fixture_and_closes_port() -> None:
    port = FixturePort(failure=ModuleNotFoundError("autogen_agentchat"))
    envelope = asyncio.run(demo.run_autogen_demo(port=port))
    assert port.closed
    assert envelope["mode"] == "local_contract"
    assert envelope["status"] == "paused"
    assert envelope["evidence"]["sdk_invoked"] is False


@pytest.mark.parametrize("mode", ["local_contract", "live_model"])
def test_subprocess_failure_returns_only_a_safe_code(
    tmp_path: Path, mode: Mode
) -> None:
    envelope = asyncio.run(
        demo.run_autogen_demo(
            port=FixturePort(mode=mode),
            resume_port=FailingResume(),
            checkpoint_dir=tmp_path,
        )
    )
    assert envelope["status"] == "error"
    assert envelope["mode"] == mode
    assert envelope["error"] == {
        "code": "resume_worker_failed",
        "message": "Resume failed safely.",
    }


def test_unexpected_team_failure_is_not_success() -> None:
    port = FixturePort(failure=RuntimeError("broken invariant"))
    with pytest.raises(RuntimeError, match="broken invariant"):
        asyncio.run(demo.run_autogen_demo(port=port))
    assert port.closed


@pytest.mark.parametrize("mode", ["local_contract", "live_model"])
def test_sdk_permission_error_is_structured_and_redacted(mode: Mode) -> None:
    import httpx
    from openai import PermissionDeniedError

    request = httpx.Request("POST", "https://synthetic.invalid/private")
    response = httpx.Response(403, request=request)
    failure = PermissionDeniedError(
        "sensitive provider detail", response=response, body=None
    )
    port = FixturePort(mode=mode, failure=failure)
    envelope = asyncio.run(demo.run_autogen_demo(port=port))
    assert envelope["mode"] == mode
    assert envelope["status"] == "blocked"
    assert envelope["error"] is not None
    assert envelope["error"]["code"] == "authorization_denied"
    assert "synthetic.invalid" not in json.dumps(envelope)
    assert "sensitive provider detail" not in json.dumps(envelope)
    assert envelope["evidence"]["service_executed"] is False
    assert port.closed

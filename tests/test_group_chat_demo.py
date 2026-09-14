"""Verify real checkpoint recovery and honest group-chat evidence."""

from __future__ import annotations

import asyncio
import importlib
import json
import os
from collections import OrderedDict
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

from msai_demo import group_chat_demo as demo
from msai_demo import scenario
from msai_demo.contracts import Mode, evidence, result
from msai_demo.resume_worker import ResumeError

if TYPE_CHECKING:
    from agent_framework import Workflow

    from msai_demo.resume_worker import ResumeResult
    from msai_demo.scenario import ProposalTurn


@pytest.fixture(autouse=True)
def isolated_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENABLE_INSTRUMENTATION", "false")
    for name in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY"):
        monkeypatch.delenv(name, raising=False)


def test_round_robin_and_termination() -> None:
    from agent_framework import Message
    from agent_framework.orchestrations import GroupChatState

    participants = OrderedDict([(demo.ARCHITECT, "A"), (demo.REVIEWER, "R")])
    assert [
        demo.round_robin(
            GroupChatState(
                current_round=i, participants=participants, conversation=[]
            )
        )
        for i in range(3)
    ] == [demo.ARCHITECT, demo.REVIEWER, demo.ARCHITECT]
    for count in range(5):
        conversation = [Message("user", contents=["Brief"])] + [
            Message("assistant", contents=["Draft"]) for _ in range(count)
        ]
        assert demo._three_assistant_turns(conversation) == (count >= 3)


@pytest.mark.parametrize("approve", [False, True])
def test_lane_really_crosses_processes_and_replays_once(
    tmp_path: Path, approve: bool
) -> None:
    sentinel = tmp_path / "prior-run.txt"
    sentinel.write_text("keep", encoding="utf-8")
    run = asyncio.run(
        demo.run_agent_framework_lane(checkpoint_dir=tmp_path, approve=approve)
    )
    assert sentinel.read_text("utf-8") == "keep"
    recovery = run["recovery"]
    assert recovery["parent_pid"] == os.getpid()
    assert recovery["resume_pid"] != os.getpid()
    assert recovery["second_resume_pid"] != os.getpid()
    assert recovery["second_resume_action_count"] == 0
    assert recovery["action_count"] == int(approve)
    assert len(run["actions"]) == int(approve)
    assert run["checks"]["acceptable"] is approve
    assert all(
        value for key, value in run["checks"].items() if key != "acceptable"
    )
    assert run["proposal"] == scenario.pilot_proposal()
    assert run["cost"] == scenario.price_pilot()
    directory = Path(str(recovery["run_directory"]))
    assert {path.name for path in directory.iterdir()} == {
        "run.json",
        "events.sqlite3",
        "checkpoints",
    }
    config = json.loads((directory / "run.json").read_text("utf-8"))
    assert set(config) == {"implementation", "max_rounds", "execution"}
    # Request data stays exclusively in SDK checkpoints. The child
    # discovers and decodes the original pending event on every retry.
    reads: list[str] = []
    checkpoint, request_id, content = asyncio.run(
        demo.load_pending_approval(directory, reads)
    )
    assert checkpoint.checkpoint_id == recovery["checkpoint_id"]
    assert request_id in checkpoint.pending_request_info_events
    assert content.function_call is not None
    assert Path(str(recovery["files_read"][0])).exists()
    # Run the identical entry point in-process too, to cover SDK calls
    # in this interpreter. The separate-process evidence above remains.
    retried = asyncio.run(
        demo.resume_agent_framework(directory, approve, "offline")
    )
    assert retried["actions"] == []


def test_turn_limit_does_not_claim_recovery(tmp_path: Path) -> None:
    run = asyncio.run(
        demo.run_group_chat_demo(
            implementation="agent-framework",
            checkpoint_dir=tmp_path,
            max_rounds=1,
        )
    )
    assert run["status"] == "paused"
    assert run["data"]["approval"]["state"] == "not_requested"
    assert run["data"]["actions"] == []
    assert not run["data"]["checks"]["survived_process_boundary"]


def test_schema_check_uses_actual_transcript() -> None:
    def turn(speaker: str, text: str) -> ProposalTurn:
        return {
            "index": 0,
            "speaker": speaker,
            "text": text,
            "provider": "offline",
            "model": "scripted",
            "source_event": "Message",
            "usage": None,
        }

    invalid = [
        turn(demo.REVIEWER, "{}"),
        turn(demo.ARCHITECT, "broken"),
        turn(demo.ARCHITECT, "[]"),
    ]
    assert demo._proposal_from_turns(invalid) == {}
    valid = turn(demo.ARCHITECT, json.dumps(scenario.pilot_proposal()))
    assert demo._proposal_from_turns([*invalid, valid]) == (
        scenario.pilot_proposal()
    )


def test_record_turn_filters_and_keeps_full_output() -> None:
    from agent_framework import Message, WorkflowEvent

    turns: list[ProposalTurn] = []
    events = [
        WorkflowEvent.started(),
        WorkflowEvent("output"),
        WorkflowEvent("intermediate", executor_id=demo.ARCHITECT),
        WorkflowEvent(
            "intermediate",
            executor_id=demo.ARCHITECT,
            data=Message("assistant", contents=[" \n "]),
        ),
    ]
    for speaker, text in [
        (demo.ARCHITECT, "Draft "),
        (demo.ARCHITECT, "x" * 700),
        (demo.REVIEWER, "Review"),
    ]:
        events.append(
            WorkflowEvent(
                "intermediate",
                executor_id=speaker,
                data=Message("assistant", contents=[text]),
            )
        )
    for event in events:
        demo._record_turn(
            event,
            turns,
            model_a="a",
            model_r="r",
            provider_a="offline",
            provider_r="offline",
        )
    assert len(turns) == 2
    assert turns[0]["text"] == "Draft " + "x" * 700
    assert turns[1]["model"] == "r"
    assert turns[1]["provider"] == "offline"


@pytest.mark.parametrize("content_kind", ["absent", "text", "call", "id"])
def test_checkpoint_validation_rejects_missing_request_data(
    tmp_path: Path, content_kind: str
) -> None:
    from agent_framework import (
        Content,
        FileCheckpointStorage,
        WorkflowCheckpoint,
        WorkflowEvent,
    )

    checkpoint = WorkflowCheckpoint(
        workflow_name="test", graph_signature_hash="x"
    )
    if content_kind != "absent":
        content: object = "not content"
        if content_kind != "text":
            content = Content(
                "function_approval_request",
                id=None if content_kind == "id" else "approval",
                function_call=None
                if content_kind == "call"
                else Content.from_function_call(
                    call_id="c", name="accept_proposal"
                ),
            )
        checkpoint.pending_request_info_events["r"] = WorkflowEvent(
            "request_info", data=content
        )
    storage = FileCheckpointStorage(tmp_path / "checkpoints")
    asyncio.run(storage.save(checkpoint))
    with pytest.raises(ResumeError):
        asyncio.run(demo.load_pending_approval(tmp_path, []))


@pytest.mark.parametrize(
    "implementation", ["autogen", "agent-framework", "both"]
)
def test_envelope_selects_lanes_and_compares_responsibilities(
    tmp_path: Path, implementation: str
) -> None:
    envelope = asyncio.run(
        demo.run_group_chat_demo(
            implementation=implementation, checkpoint_dir=tmp_path
        )
    )
    assert envelope["status"] == "ok"
    assert not envelope["evidence"]["network_attempted"]
    if implementation == "both":
        comparison = envelope["data"]["comparison"]
        assert len(envelope["children"]) == 2
        assert "application_owned_counts" not in comparison
        assert (
            comparison["responsibility_matrix"] == demo.responsibility_matrix()
        )
    else:
        assert envelope["mode"] == "local_contract"
        assert envelope["data"]["implementation"] == implementation


def test_matrix_application_functions_exist() -> None:
    matrix = demo.responsibility_matrix()
    assert [row["concern"] for row in matrix] == [
        "pending approval record",
        "durable state",
        "restart routing",
        "action gate",
        "idempotency",
        "audit event log",
    ]
    for row in matrix:
        for lane in ("autogen", "agent-framework"):
            owner, qualified = row[lane].split(": ", 1)
            assert owner in {"application", "framework"}
            if owner == "application":
                parts = qualified.split(".")
                target: object = importlib.import_module(".".join(parts[:2]))
                for part in parts[2:]:
                    target = getattr(target, part)
                assert callable(target)


def test_compare_handles_missing_payloads() -> None:
    first = result(
        demo="first",
        technology="fixture",
        lane="shared",
        mode="not_run",
        status="blocked",
        headline="No state",
        evidence=evidence(provider="none"),
    )
    second = {**first, "demo": "second"}
    comparison = demo.compare(first, second)
    assert comparison["checks"] == {"first": {}, "second": {}}
    assert comparison["recovery"] == {"first": {}, "second": {}}


def test_configuration_and_invalid_implementation() -> None:
    for names in (set(), {"OPENAI_API_KEY"}, {"ANTHROPIC_API_KEY"}):
        run = asyncio.run(
            demo.run_group_chat_demo(
                execution="live", configured=names.__contains__
            )
        )
        assert run["error"]["code"] == "missing_configuration"
        assert run["mode"] == "not_run"
    with pytest.raises(ValueError, match="Unknown"):
        asyncio.run(demo.run_group_chat_demo(implementation="unknown"))
    assert demo.FrameworkPort("live").mode == "live_model"
    assert demo.FrameworkPort().mode == "local_contract"


class InProcessResume:
    async def resume(
        self, directory: Path, approve: bool, *, execution: str
    ) -> ResumeResult:
        assert execution == "live"
        # This test double never invents process evidence.
        return await demo.resume_agent_framework(directory, approve, "offline")


class ScriptedLivePort:
    mode: Mode = "live_model"

    def build(
        self, directory: Path, max_rounds: int, *, resuming: bool = False
    ) -> Workflow:
        return demo.FrameworkPort().build(
            directory, max_rounds, resuming=resuming
        )


def test_live_routing_is_injectable_without_credentials(
    tmp_path: Path,
) -> None:
    envelope = asyncio.run(
        demo.run_group_chat_demo(
            implementation="agent-framework",
            execution="live",
            configured=lambda _: True,
            checkpoint_dir=tmp_path,
            port=ScriptedLivePort(),
            resume_port=InProcessResume(),
        )
    )
    assert envelope["mode"] == "live_model"
    assert envelope["status"] == "paused"
    assert not envelope["data"]["checks"]["survived_process_boundary"]
    assert envelope["data"]["participants"][0]["provider"] == "openai"


class MissingSdkPort:
    mode: Mode = "local_contract"

    def build(
        self, directory: Path, max_rounds: int, *, resuming: bool = False
    ) -> Workflow:
        del directory, max_rounds, resuming
        raise ImportError


class MalformedProposalPort:
    mode: Mode = "local_contract"

    def build(
        self, directory: Path, max_rounds: int, *, resuming: bool = False
    ) -> Workflow:
        from agent_framework import FileCheckpointStorage

        from msai_demo.providers import create_chat_client

        def factory(provider: str, **kwargs: Any) -> Any:
            kwargs["replies"] = ["malformed proposal"]
            return create_chat_client(provider, **kwargs)

        architect, reviewer = demo.build_participants(
            provider_architect="offline",
            provider_reviewer="offline",
            directory=directory,
            client_factory=factory,
            resuming=resuming,
        )
        return demo.build_group_chat_workflow(
            architect=architect,
            reviewer=reviewer,
            storage=FileCheckpointStorage(directory / "checkpoints"),
            max_rounds=max_rounds,
        )


def test_malformed_proposal_stays_pending_without_action(
    tmp_path: Path,
) -> None:
    envelope = asyncio.run(
        demo.run_group_chat_demo(
            implementation="agent-framework",
            checkpoint_dir=tmp_path,
            port=MalformedProposalPort(),
        )
    )
    assert envelope["status"] == "paused"
    assert not envelope["data"]["checks"]["schema_valid"]
    assert not envelope["data"]["checks"]["acceptable"]
    assert envelope["data"]["actions"] == []
    assert envelope["data"]["approval"]["state"] == "pending"


class FailedResume:
    async def resume(
        self, directory: Path, approve: bool, *, execution: str
    ) -> ResumeResult:
        del directory, approve, execution
        code = "resume_worker_failed"
        raise ResumeError(code)


def test_missing_sdk_and_resume_failure_are_structured(tmp_path: Path) -> None:
    for kwargs, code in [
        ({"port": MissingSdkPort()}, "sdk_missing"),
        ({"resume_port": FailedResume()}, "resume_worker_failed"),
    ]:
        envelope = asyncio.run(
            demo.run_group_chat_demo(
                implementation="agent-framework",
                checkpoint_dir=tmp_path,
                **kwargs,
            )
        )
        assert envelope["status"] == (
            "paused" if code == "sdk_missing" else "error"
        )
        assert envelope["error"]["code"] == code


def test_live_factory_receives_explicit_provider_names(tmp_path: Path) -> None:
    requested: list[str] = []

    def factory(provider: str, **kwargs: Any) -> Any:
        requested.append(provider)
        from msai_demo.providers import create_chat_client

        return create_chat_client("offline", **kwargs)

    demo.build_participants(
        provider_architect="openai",
        provider_reviewer="anthropic",
        directory=tmp_path,
        client_factory=factory,
    )
    assert requested == ["openai", "anthropic"]


class FailingModelPort:
    mode: Mode = "live_model"

    def __init__(self, failure: Exception) -> None:
        self.failure = failure

    def build(
        self, directory: Path, max_rounds: int, *, resuming: bool = False
    ) -> Workflow:
        del directory, max_rounds, resuming
        raise self.failure


def test_parent_provider_failure_is_sanitized(tmp_path: Path) -> None:
    import httpx
    from openai import PermissionDeniedError

    request = httpx.Request("POST", "https://private.invalid/")
    error = PermissionDeniedError(
        "secret endpoint",
        response=httpx.Response(403, request=request),
        body=None,
    )
    envelope = asyncio.run(
        demo.run_group_chat_demo(
            implementation="agent-framework",
            port=FailingModelPort(error),
            checkpoint_dir=tmp_path,
        )
    )
    assert envelope["status"] == "blocked"
    assert envelope["error"]["code"] == "authorization_denied"
    assert envelope["evidence"]["network_attempted"] is True
    assert envelope["evidence"]["service_executed"] is False
    assert "private.invalid" not in json.dumps(envelope)
    assert "secret endpoint" not in json.dumps(envelope)
    with pytest.raises(RuntimeError, match="unknown invariant"):
        asyncio.run(
            demo.run_group_chat_demo(
                implementation="agent-framework",
                port=FailingModelPort(RuntimeError("unknown invariant")),
                checkpoint_dir=tmp_path,
            )
        )

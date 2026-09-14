"""Test the real process transport and measured recovery checks.

Run it:

    uv run pytest tests/test_resume_worker.py
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from dataclasses import dataclass
from typing import TYPE_CHECKING

import pytest

from msai_demo import resume_worker as worker
from msai_demo import scenario

if TYPE_CHECKING:
    from pathlib import Path
    from types import ModuleType


def _resumed(directory: Path, *, pid: int = 123) -> worker.ResumeResult:
    return {
        "pid": pid,
        "files_read": [
            str(directory / "run.json"),
            str(directory / "checkpoint.json"),
        ],
        "checkpoint_id": "paused-checkpoint",
        "actions": [],
        "restored": True,
    }


@dataclass
class Process:
    output: bytes
    returncode: int | None = 0

    async def communicate(self) -> tuple[bytes, bytes]:
        return self.output, b"sensitive endpoint must never be forwarded"


class Spawn:
    def __init__(self, process: Process | OSError) -> None:
        self.process = process
        self.arguments: tuple[str, ...] = ()

    async def __call__(
        self, *arguments: str, stdout: int, stderr: int
    ) -> Process:
        self.arguments = arguments
        assert stdout == asyncio.subprocess.PIPE
        assert stderr == asyncio.subprocess.DEVNULL
        if isinstance(self.process, OSError):
            raise self.process
        return self.process


@pytest.mark.parametrize("approve", [True, False])
def test_transport_passes_only_disk_path_decision_and_mode(
    tmp_path: Path, approve: bool
) -> None:
    expected = _resumed(tmp_path)
    spawn = Spawn(Process(json.dumps(expected).encode()))
    result = asyncio.run(
        worker.SubprocessResumePort(spawn=spawn).resume(
            tmp_path, approve, execution="offline"
        )
    )
    assert result == expected
    assert spawn.arguments == (
        sys.executable,
        "-m",
        "msai_demo.resume_worker",
        str(tmp_path.resolve()),
        "approve" if approve else "reject",
        "--execution",
        "offline",
    )


@pytest.mark.parametrize(
    ("process", "code"),
    [
        (OSError("secret"), "resume_worker_start_failed"),
        (Process(b"secret", 1), "resume_worker_failed"),
        (Process(b"invalid json"), "resume_worker_invalid_output"),
        (Process(b'{"pid":"wrong"}'), "resume_worker_invalid_output"),
    ],
)
def test_transport_sanitizes_failures(
    tmp_path: Path, process: Process | OSError, code: str
) -> None:
    with pytest.raises(worker.ResumeError) as raised:
        asyncio.run(
            worker.SubprocessResumePort(spawn=Spawn(process)).resume(
                tmp_path, True, execution="offline"
            )
        )
    assert raised.value.code == code
    assert "secret" not in str(raised.value)
    assert "sensitive" not in str(raised.value)


def test_real_subprocess_failure_is_structured(tmp_path: Path) -> None:
    with pytest.raises(worker.ResumeError) as raised:
        asyncio.run(
            worker.SubprocessResumePort().resume(
                tmp_path, True, execution="offline"
            )
        )
    assert raised.value.code == "resume_worker_failed"


def test_disk_json_records_actual_reads(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    reads: list[str] = []
    worker.write_json(path, {"state": "paused"})
    assert worker.read_json(path, reads) == {"state": "paused"}
    assert reads == [str(path.resolve())]
    path.write_text("[]", encoding="utf-8")
    with pytest.raises(TypeError, match="JSON object"):
        worker.read_json(path, reads)


@pytest.mark.parametrize(
    ("execution", "configuration", "code"),
    [
        ("auto", {}, "invalid_execution"),
        (
            "offline",
            {"execution": "live"},
            "execution_mismatch",
        ),
        ("offline", {"implementation": "unknown"}, "unknown_implementation"),
    ],
)
def test_worker_validates_mode_before_building_clients(
    tmp_path: Path,
    execution: str,
    configuration: dict[str, object],
    code: str,
) -> None:
    worker.write_json(tmp_path / "run.json", configuration)
    with pytest.raises(worker.ResumeError) as raised:
        asyncio.run(worker.run_worker(tmp_path, True, execution))
    assert raised.value.code == code


def test_worker_records_config_read_and_uses_injected_lane(
    tmp_path: Path,
) -> None:
    worker.write_json(tmp_path / "run.json", {"implementation": "autogen"})

    async def resume(
        directory: Path, approve: bool, execution: str
    ) -> worker.ResumeResult:
        assert directory == tmp_path
        assert not approve
        assert execution == "offline"
        return _resumed(directory, pid=os.getpid())

    result = asyncio.run(
        worker.run_worker(tmp_path, False, "offline", dispatch=resume)
    )
    assert result["pid"] == os.getpid()
    assert result["files_read"] == [
        str(tmp_path / "run.json"),
        str(tmp_path / "checkpoint.json"),
    ]


def test_real_lane_routing_is_lazy_and_uses_persisted_state(
    tmp_path: Path,
) -> None:
    from msai_demo.autogen_demo import resume_autogen
    from msai_demo.group_chat_demo import resume_agent_framework

    assert worker._lane_handler("autogen") is resume_autogen
    assert worker._lane_handler("agent-framework") is resume_agent_framework
    worker.write_json(
        tmp_path / "run.json",
        {"implementation": "agent-framework", "max_rounds": 4},
    )
    with pytest.raises((worker.ResumeError, FileNotFoundError)):
        asyncio.run(worker.run_worker(tmp_path, True, "offline"))


def test_main_prints_exactly_one_json_document(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    worker.write_json(tmp_path / "run.json", {"implementation": "autogen"})

    async def resume(
        directory: Path, approve: bool, execution: str
    ) -> worker.ResumeResult:
        assert approve
        assert execution == "offline"
        print("SDK diagnostic output")
        return _resumed(directory, pid=os.getpid())

    assert (
        worker.main(
            [str(tmp_path), "approve", "--execution", "offline"],
            dispatch=resume,
        )
        == 0
    )
    captured = capsys.readouterr()
    assert json.loads(captured.out)["pid"] == os.getpid()
    assert captured.err == "SDK diagnostic output\n"


def test_main_failure_never_prints_exception_details(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert (
        worker.main([str(tmp_path), "reject", "--execution", "offline"]) == 1
    )
    assert json.loads(capsys.readouterr().out) == {
        "error": {"code": "resume_worker_failed"}
    }


def test_recovery_without_a_gate_claims_no_restart(tmp_path: Path) -> None:
    summary = worker.recovery_summary(tmp_path, os.getpid(), None, None)
    assert summary["resume_pid"] is None
    assert summary["second_resume_pid"] is None
    assert summary["files_read"] == []
    assert summary["second_resume_files_read"] == []
    assert summary["checkpoint_id"] is None
    assert not summary["restored"]
    assert not summary["state_read_from_disk"]
    assert summary["second_resume_action_count"] == 0
    checks = worker.execution_checks(
        scenario.pilot_proposal(), [], os.getpid(), None, None, approve=True
    )
    assert not checks["paused_for_approval"]
    assert not checks["one_action_after_resume"]
    assert not checks["survived_process_boundary"]
    assert not checks["idempotent_second_resume"]


def test_recovery_derives_checks_from_events_and_child_evidence(
    tmp_path: Path,
) -> None:
    store = scenario.EventStore(tmp_path)
    store.append("gate_reached")
    store.append("approval_recorded", approved=True)
    action = store.execute_action(scenario.SCENARIO_ID)
    assert action is not None
    first = _resumed(tmp_path, pid=os.getpid() + 1)
    first["actions"] = [action]
    second = _resumed(tmp_path, pid=os.getpid() + 2)
    summary = worker.recovery_summary(tmp_path, os.getpid(), first, second)
    assert summary["parent_pid"] == os.getpid()
    assert summary["resume_pid"] == first["pid"]
    assert summary["action_count"] == 1
    assert summary["second_resume_action_count"] == 0
    checks = worker.execution_checks(
        scenario.pilot_proposal(),
        store.events(),
        os.getpid(),
        first,
        second,
        approve=True,
    )
    assert all(checks.values())
    second["actions"] = [action]
    assert not worker.execution_checks(
        scenario.pilot_proposal(),
        store.events(),
        os.getpid(),
        first,
        second,
        approve=True,
    )["idempotent_second_resume"]


def test_rejected_and_unordered_events_are_checked(tmp_path: Path) -> None:
    first = _resumed(tmp_path)
    second = _resumed(tmp_path, pid=124)
    events: list[dict[str, object]] = [
        {"name": "gate_reached", "details": {}},
        {"name": "approval_recorded", "details": {"approved": False}},
    ]
    checks = worker.execution_checks(
        scenario.pilot_proposal(), events, 122, first, second, approve=False
    )
    assert checks["one_action_after_resume"]
    assert checks["no_action_before_approval"]
    events.append({"name": "action_executed", "details": {}})
    checks = worker.execution_checks(
        scenario.pilot_proposal(), events, 122, first, second, approve=False
    )
    assert not checks["no_action_before_approval"]
    assert not checks["one_action_after_resume"]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("restored", False),
        ("checkpoint_id", ""),
        ("files_read", ["checkpoint.json"]),
        ("files_read", ["run.json", "events.sqlite3"]),
        ("pid", 1),
    ],
)
def test_insufficient_disk_or_process_evidence_fails(
    tmp_path: Path, field: str, value: object
) -> None:
    first = _resumed(tmp_path)
    second = _resumed(tmp_path, pid=124)
    # JSON validation is the production boundary for these typed fields.
    altered = {**first, field: value}
    first = worker.ResumeResult(**altered)
    checks = worker.execution_checks(
        scenario.pilot_proposal(), [], 1, first, second, approve=True
    )
    assert not checks["survived_process_boundary"]


@pytest.mark.parametrize("provider", ["openai", "anthropic"])
@pytest.mark.parametrize(
    ("name", "http_status", "expected_status", "expected_code"),
    [
        ("AuthenticationError", 401, "error", "authentication_failed"),
        ("PermissionDeniedError", 403, "blocked", "authorization_denied"),
        ("RateLimitError", 429, "error", "rate_limited"),
        ("APITimeoutError", None, "error", "timeout"),
    ],
)
def test_actual_vendor_failures_are_safely_classified(
    provider: str,
    name: str,
    http_status: int | None,
    expected_status: str,
    expected_code: str,
) -> None:
    from importlib import import_module

    sdk = import_module(provider)
    transport = import_module("httpx2" if provider == "openai" else "httpx")
    request = transport.Request("POST", "https://sensitive.invalid/model")
    exception_type = getattr(sdk, name)
    if http_status is None:
        failure = exception_type(request=request)
    else:
        failure = exception_type(
            "secret endpoint and credential",
            response=transport.Response(http_status, request=request),
            body={"private": "secret"},
        )
    result = worker.model_failure(failure)
    assert result is not None
    status, error = result
    assert status == expected_status
    assert error["code"] == expected_code
    assert "secret" not in error["message"]
    assert "sensitive" not in error["message"]


@pytest.mark.parametrize("link", ["__cause__", "__context__"])
def test_vendor_failures_survive_framework_wrappers(link: str) -> None:
    import httpx2
    from openai import PermissionDeniedError

    request = httpx2.Request("POST", "https://example.invalid/model")
    denied = PermissionDeniedError(
        "denied", response=httpx2.Response(403, request=request), body=None
    )
    wrapper = RuntimeError("framework wrapper")
    setattr(wrapper, link, denied)
    classified = worker.model_failure(wrapper)
    assert classified is not None
    assert classified[1]["code"] == "authorization_denied"


def test_unknown_errors_and_cyclic_causes_remain_unknown() -> None:
    unknown = ValueError("application defect")
    assert worker.model_failure(unknown) is None
    unknown.__cause__ = unknown
    assert worker.model_failure(unknown) is None


def test_missing_optional_sdks_do_not_mask_the_original_failure() -> None:
    def missing_sdk(name: str) -> ModuleType:
        raise ImportError(name)

    assert (
        worker.model_failure(ValueError("original"), sdk_loader=missing_sdk)
        is None
    )

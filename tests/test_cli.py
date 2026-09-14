"""Test command routing and output with deterministic local runners.

Run it:

    uv run pytest tests/test_cli.py
"""

from __future__ import annotations

import asyncio
import io
import json
import sys
from dataclasses import dataclass, field
from types import ModuleType
from typing import TYPE_CHECKING

import pytest
from rich.console import Console

from msai_demo import cli
from msai_demo.contracts import DemoResult, Status, evidence, result

if TYPE_CHECKING:
    import argparse


@dataclass
class CliCapture:
    output: io.StringIO = field(default_factory=io.StringIO)
    loaded: list[bool] = field(default_factory=list)
    telemetry: list[bool] = field(default_factory=list)


@pytest.fixture
def cli_capture(monkeypatch: pytest.MonkeyPatch) -> CliCapture:
    capture = CliCapture()
    console = Console(file=capture.output, width=180, color_system=None)

    def load_env() -> list[str]:
        # The CLI must never read the workstation's real .env in a test.
        capture.loaded.append(True)
        return []

    def configure_telemetry(*, enabled: bool) -> str:
        capture.telemetry.append(enabled)
        return "cli-tests"

    monkeypatch.setattr(cli, "Console", lambda: console)
    monkeypatch.setattr(cli, "load_env_file", load_env)
    monkeypatch.setattr(cli, "configure_telemetry", configure_telemetry)
    return capture


def _outcome(name: str = "test-demo", status: Status = "ok") -> DemoResult:
    return result(
        demo=name,
        technology="Offline test runner",
        lane="shared",
        mode="local_execution",
        status=status,
        headline="The injected runner completed locally.",
        evidence=evidence(provider="offline"),
        data={"marker": "local-result"},
    )


def _install_runner(
    monkeypatch: pytest.MonkeyPatch,
    name: str,
    outcome: DemoResult,
) -> list[dict[str, object]]:
    calls: list[dict[str, object]] = []

    async def run(**kwargs: object) -> DemoResult:
        calls.append(kwargs)
        return outcome

    demo = cli.DEMOS_BY_NAME[name]
    module_name = f"msai_demo.{demo.module}"
    module = ModuleType(module_name)
    setattr(module, demo.runner, run)
    monkeypatch.setitem(sys.modules, module_name, module)
    return calls


@pytest.mark.parametrize(
    "command", ["list", "doctor", "all", *(demo.name for demo in cli.DEMOS)]
)
def test_parser_accepts_every_registered_command(command: str) -> None:
    args = cli.build_parser().parse_args([command])
    assert args.command == command
    if command not in {"list", "doctor"}:
        assert args.execution == "offline"
        assert args.format == "pretty"


def test_parser_accepts_doctor_options() -> None:
    args = cli.build_parser().parse_args(
        ["doctor", "--packages", "--demo", "workflow", "--probe"]
    )
    assert args.packages is True
    assert args.demo == "workflow"
    assert args.probe is True


@pytest.mark.parametrize("argv", [[], ["unknown"], ["workflow", "--trace"]])
def test_invalid_usage_exits_two(
    argv: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as caught:
        cli.build_parser().parse_args(argv)
    assert caught.value.code == 2
    assert "usage:" in capsys.readouterr().err


def test_list_renders_every_demo_without_starting_telemetry(
    cli_capture: CliCapture,
) -> None:
    assert cli.main(["list"]) == 0
    rendered = cli_capture.output.getvalue()
    assert "Microsoft AI stack workshop" in rendered
    assert all(demo.name in rendered for demo in cli.DEMOS)
    assert "legacy" in rendered
    assert "current" in rendered
    assert "shared" in rendered
    assert cli_capture.loaded == [True]
    assert cli_capture.telemetry == []


@pytest.mark.parametrize("ready", [False, True])
def test_doctor_forwards_options_and_maps_exit_status(
    monkeypatch: pytest.MonkeyPatch,
    cli_capture: CliCapture,
    ready: bool,
) -> None:
    calls: list[tuple[bool, str | None, bool]] = []

    def run_doctor(
        console: Console,
        *,
        packages_only: bool,
        demo: str | None,
        probe: bool,
    ) -> bool:
        assert console.file is cli_capture.output
        calls.append((packages_only, demo, probe))
        return ready

    module = ModuleType("msai_demo.doctor")
    module.__dict__["run_doctor"] = run_doctor
    monkeypatch.setitem(sys.modules, "msai_demo.doctor", module)
    exit_code = cli.main(
        ["doctor", "--packages", "--demo", "workflow", "--probe"]
    )
    assert exit_code == (0 if ready else 1)
    assert calls == [(True, "workflow", True)]
    assert cli_capture.loaded == [True]
    assert cli_capture.telemetry == []


@pytest.mark.parametrize("output_format", ["json", "pretty"])
def test_single_demo_dispatches_and_renders_the_envelope(
    monkeypatch: pytest.MonkeyPatch,
    cli_capture: CliCapture,
    output_format: str,
) -> None:
    outcome = _outcome("workflow")
    calls = _install_runner(monkeypatch, "workflow", outcome)
    assert cli.main(["workflow", "--format", output_format]) == 0
    assert calls == [{"execution": "offline"}]
    assert cli_capture.loaded == [True]
    assert cli_capture.telemetry == [False]
    rendered = cli_capture.output.getvalue()
    if output_format == "json":
        assert json.loads(rendered) == outcome
    else:
        assert "mode=local_execution" in rendered
        assert outcome["headline"] in rendered
        assert "local-result" in rendered


@pytest.mark.parametrize(
    ("argv", "expected", "telemetry"),
    [
        (
            ["group-chat"],
            {
                "execution": "offline",
                "implementation": "both",
                "max_rounds": 4,
                "approve": True,
            },
            False,
        ),
        (
            [
                "group-chat",
                "--implementation",
                "agent-framework",
                "--max-rounds",
                "2",
                "--decision",
                "reject",
            ],
            {
                "execution": "offline",
                "implementation": "agent-framework",
                "max_rounds": 2,
                "approve": False,
            },
            False,
        ),
        (
            ["autogen", "--max-turns", "3", "--decision", "reject"],
            {"execution": "offline", "max_turns": 3, "approve": False},
            False,
        ),
        (
            ["otel", "--trace", "off"],
            {"execution": "offline", "trace": "off"},
            False,
        ),
        (
            ["otel"],
            {"execution": "offline", "trace": "local"},
            True,
        ),
        (
            ["otel", "--trace", "azure", "--execution", "live"],
            {"execution": "live", "trace": "azure"},
            True,
        ),
    ],
)
def test_demo_specific_options_reach_only_the_matching_runner(
    monkeypatch: pytest.MonkeyPatch,
    cli_capture: CliCapture,
    argv: list[str],
    expected: dict[str, object],
    telemetry: bool,
) -> None:
    calls = _install_runner(monkeypatch, argv[0], _outcome(argv[0]))
    assert cli.main(argv) == 0
    assert calls == [expected]
    assert cli_capture.telemetry == [telemetry]


@pytest.mark.parametrize("name", cli._EXTRA_FLAGS)
def test_all_uses_the_same_extra_defaults_as_each_subcommand(
    monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    calls = _install_runner(monkeypatch, name, _outcome(name))
    parser = cli.build_parser()
    demo = cli.DEMOS_BY_NAME[name]
    asyncio.run(cli._invoke(demo, parser.parse_args([name])))
    asyncio.run(cli._invoke(demo, parser.parse_args(["all"])))
    assert calls[0] == calls[1]


def test_all_dispatches_local_tracing_without_enabling_parent_telemetry(
    monkeypatch: pytest.MonkeyPatch, cli_capture: CliCapture
) -> None:
    calls = {
        demo.name: _install_runner(monkeypatch, demo.name, _outcome(demo.name))
        for demo in cli.DEMOS
    }
    assert cli.main(["all", "--format", "json"]) == 0
    assert calls["otel"] == [{"execution": "offline", "trace": "local"}]
    assert all(len(invocations) == 1 for invocations in calls.values())
    assert cli_capture.telemetry == [False]


def test_all_defaults_capture_real_otel_spans_in_memory() -> None:
    args = cli.build_parser().parse_args(["all"])
    outcome = asyncio.run(cli._invoke(cli.DEMOS_BY_NAME["otel"], args))
    assert outcome["mode"] == "local_execution"
    assert outcome["status"] == "ok"
    assert outcome["evidence"]["network_attempted"] is False
    assert outcome["evidence"]["service_executed"] is False
    data = outcome["data"]
    assert data is not None
    assert data["trace_destination"] == "memory"
    assert data["exported"] is False
    assert {
        span["attributes"]["gen_ai.operation.name"] for span in data["spans"]
    } == {
        "invoke_agent",
        "chat",
        "execute_tool",
    }


def test_missing_demo_module_returns_one_with_an_actionable_message(
    monkeypatch: pytest.MonkeyPatch,
    cli_capture: CliCapture,
) -> None:
    monkeypatch.setitem(sys.modules, "msai_demo.workflow_demo", None)
    assert cli.main(["workflow"]) == 1
    rendered = cli_capture.output.getvalue()
    assert "workflow is not available" in rendered
    assert "msai_demo.workflow_demo" in rendered
    assert cli_capture.telemetry == [False]


@pytest.mark.parametrize("lane", ["legacy", "current", "all"])
def test_all_selects_the_requested_lane_and_includes_shared_demos(
    monkeypatch: pytest.MonkeyPatch,
    cli_capture: CliCapture,
    lane: str,
) -> None:
    calls: list[str] = []
    emitted: list[DemoResult] = []

    async def invoke(demo: cli.Demo, args: argparse.Namespace) -> DemoResult:
        assert args.execution == "offline"
        calls.append(demo.name)
        return _outcome(demo.name)

    def emit(outcome: DemoResult, console: Console, output: str) -> None:
        assert console.file is cli_capture.output
        assert output == "json"
        emitted.append(outcome)

    # Keep lane selection independent of optional, slow demo execution.
    monkeypatch.setattr(cli, "_invoke", invoke)
    monkeypatch.setattr(cli, "_emit", emit)
    assert cli.main(["all", "--lane", lane, "--format", "json"]) == 0
    expected = [
        demo.name
        for demo in cli.DEMOS
        if lane == "all" or demo.lane in {lane, "shared"}
    ]
    assert calls == expected
    assert len(emitted) == 1
    envelope = emitted[0]
    assert envelope["mode"] == "batch"
    assert envelope["status"] == "ok"
    assert envelope["data"] == {"total": len(expected), "failed": []}
    assert [child["demo"] for child in envelope["children"]] == expected
    assert all(name in cli_capture.output.getvalue() for name in expected)
    assert cli_capture.telemetry == [False]


def test_all_skips_unavailable_modules_and_reports_failed_children(
    monkeypatch: pytest.MonkeyPatch,
    cli_capture: CliCapture,
) -> None:
    calls: list[str] = []

    async def invoke(demo: cli.Demo, args: argparse.Namespace) -> DemoResult:
        assert args.execution == "offline"
        calls.append(demo.name)
        if demo.name == "autogen":
            message = "optional-demo-sdk is not installed"
            raise ModuleNotFoundError(message)
        status: Status = "blocked" if demo.name == "group-chat" else "ok"
        return _outcome(demo.name, status)

    monkeypatch.setattr(cli, "_invoke", invoke)
    assert cli.main(["all", "--lane", "legacy"]) == 1
    expected = [
        demo.name for demo in cli.DEMOS if demo.lane in {"legacy", "shared"}
    ]
    assert calls == expected
    rendered = cli_capture.output.getvalue()
    assert "skipped autogen" in rendered
    assert "optional-demo-sdk is not installed" in rendered
    assert f"Ran {len(expected) - 1} demos" in rendered
    assert '"group-chat"' in rendered


@pytest.mark.parametrize(
    ("status", "expected"),
    [("ok", 0), ("paused", 0), ("blocked", 1), ("error", 1)],
)
def test_exit_code_follows_status(status: Status, expected: int) -> None:
    assert cli._exit_code(_outcome(status=status)) == expected


@pytest.mark.parametrize("status", ["ok", "paused", "blocked", "error"])
def test_emit_pretty_includes_errors_and_next_steps(status: Status) -> None:
    outcome = _outcome(status=status)
    outcome["error"] = {
        "code": "missing_configuration",
        "message": "A required setting is absent.",
    }
    outcome["next_steps"] = ["Set the missing variable.", "Retry offline."]
    output = io.StringIO()
    console = Console(file=output, width=160, color_system=None)
    cli._emit(outcome, console, "pretty")
    rendered = output.getvalue()
    assert status in rendered
    assert "missing_configuration: A required setting is absent." in rendered
    assert "next: Set the missing variable." in rendered
    assert "next: Retry offline." in rendered
    assert "local-result" in rendered


def test_emit_json_preserves_error_and_next_steps() -> None:
    outcome = _outcome(status="blocked")
    outcome["error"] = {"code": "blocked", "message": "Approval is pending."}
    outcome["next_steps"] = ["Record the approval decision."]
    output = io.StringIO()
    cli._emit(outcome, Console(file=output, color_system=None), "json")
    assert json.loads(output.getvalue()) == outcome

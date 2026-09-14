from __future__ import annotations

import asyncio
import json
import os
import sys
from typing import TYPE_CHECKING

import pytest

from msai_demo import observability_demo as demo

if TYPE_CHECKING:
    from pathlib import Path

    from opentelemetry.sdk.trace.export import SpanExporter


def span(
    operation: str, span_id: str, parent_id: str | None
) -> demo.SpanRecord:
    return {
        "name": operation,
        "span_id": span_id,
        "parent_id": parent_id,
        "attributes": {"gen_ai.operation.name": operation},
    }


def capture(*, exported: bool = False) -> demo.TraceCapture:
    return {
        "spans": [
            span("invoke_agent", "agent", None),
            span("chat", "chat", "agent"),
            span("execute_tool", "tool", "chat"),
        ],
        "response": "Pilot costed; human approval is still required.",
        "exported": exported,
    }


class TracePort:
    def __init__(self, *, exported: bool = False) -> None:
        self.exported = exported
        self.connection: str | None = None

    async def capture(
        self, *, trace: str, connection_string: str | None
    ) -> demo.TraceCapture:
        assert trace in {"memory", "azure"}
        self.connection = connection_string
        return capture(exported=self.exported)


class Process:
    def __init__(self, *, returncode: int = 0) -> None:
        self.returncode = returncode
        self.killed = False
        self.environment: dict[str, str] = {}

    async def start(self, environment: dict[str, str]) -> demo.CaptureProcess:
        self.environment = environment
        return self

    async def communicate(self) -> tuple[bytes, bytes]:
        return json.dumps(capture()).encode(), b"sensitive child diagnostics"

    def kill(self) -> None:
        self.killed = True


def load_sdk(name: str) -> object:
    assert name
    return object()


def missing_sdk(name: str) -> object:
    raise ModuleNotFoundError(name)


def test_real_sdk_tree_is_local_and_does_not_mutate_parent_environment() -> (
    None
):
    before = dict(os.environ)
    result = asyncio.run(demo.run_observability_demo())
    assert os.environ == before
    assert result["mode"] == "local_execution"
    assert result["status"] == "ok"
    assert result["evidence"]["sdk_invoked"] is True
    assert result["evidence"]["network_attempted"] is False
    data = result["data"]
    assert data is not None
    spans = data["spans"]
    assert {item["attributes"]["gen_ai.operation.name"] for item in spans} == {
        "invoke_agent",
        "chat",
        "execute_tool",
    }
    demo._validate_tree(spans)
    assert data["exported"] is False
    assert data["usage"] is None
    assert data["metrics"] == list(demo.METRICS)
    assert "tool arguments" in data["sensitive_data"]
    assert "gen_ai.tool.call.arguments" not in json.dumps(spans)
    assert "gen_ai.input.messages" not in json.dumps(spans)


def test_memory_mode_does_not_pass_ambient_connection_string() -> None:
    port = TracePort()
    result = asyncio.run(
        demo.run_observability_demo(
            port=port,
            environment={"APPLICATIONINSIGHTS_CONNECTION_STRING": "secret"},
        )
    )
    assert port.connection is None
    assert "secret" not in json.dumps(result)


@pytest.mark.parametrize("exported", [False, True])
def test_explicit_remote_export_reports_actual_outcome(exported: bool) -> None:
    port = TracePort(exported=exported)
    result = asyncio.run(
        demo.run_observability_demo(
            trace="azure",
            port=port,
            environment={"APPLICATIONINSIGHTS_CONNECTION_STRING": "secret"},
        )
    )
    assert port.connection == "secret"
    assert result["mode"] == "live_service"
    assert result["evidence"]["service_executed"] is exported
    assert result["status"] == ("ok" if exported else "error")
    assert "secret" not in json.dumps(result)


def test_remote_export_requires_configuration_before_calling_port() -> None:
    result = asyncio.run(
        demo.run_observability_demo(trace="azure", environment={})
    )
    assert result["mode"] == "not_run"
    assert result["error"] is not None
    assert result["error"]["code"] == "missing_configuration"


def test_unknown_trace_destination_is_rejected() -> None:
    with pytest.raises(ValueError, match="trace must"):
        asyncio.run(demo.run_observability_demo(trace="console"))


def test_missing_optional_sdk_reports_useful_contract() -> None:
    result = asyncio.run(
        demo.run_observability_demo(
            port=demo.LocalObservabilityPort(sdk_loader=missing_sdk)
        )
    )
    assert result["mode"] == "local_contract"
    assert result["status"] == "blocked"
    assert result["evidence"]["fixture_id"] == "otel-contract-v1"
    assert result["evidence"]["sdk_invoked"] is False


def test_worker_receives_only_explicit_export_configuration() -> None:
    worker = Process()
    port = demo.LocalObservabilityPort(
        process_factory=worker.start, sdk_loader=load_sdk
    )
    result = asyncio.run(
        port.capture(trace="azure", connection_string="secret")
    )
    assert result == capture()
    assert (
        worker.environment["APPLICATIONINSIGHTS_CONNECTION_STRING"] == "secret"
    )
    assert worker.environment["MSAI_TRACE_DESTINATION"] == "azure"


def test_worker_failure_never_exposes_stderr() -> None:
    worker = Process(returncode=1)
    port = demo.LocalObservabilityPort(
        process_factory=worker.start, sdk_loader=load_sdk
    )
    with pytest.raises(
        RuntimeError, match="isolated telemetry worker failed"
    ) as exc:
        asyncio.run(port.capture(trace="memory", connection_string=None))
    assert "sensitive child diagnostics" not in str(exc.value)


def test_worker_timeout_kills_and_drains_child() -> None:
    worker = Process()
    port = demo.LocalObservabilityPort(
        process_factory=worker.start, sdk_loader=load_sdk, timeout=0
    )
    with pytest.raises(TimeoutError):
        asyncio.run(port.capture(trace="memory", connection_string=None))
    assert worker.killed is True


def test_exporter_environment_is_scrubbed() -> None:
    environment = {
        "OTEL_EXPORTER_OTLP_ENDPOINT": "https://example.invalid",
        "APPLICATIONINSIGHTS_CONNECTION_STRING": "secret",
        "VS_CODE_EXTENSION_PORT": "4317",
        "MSAI_TRACE_DESTINATION": "azure",
        "ENABLE_SENSITIVE_DATA": "true",
        "PATH": "keep",
    }
    cleaned = demo._isolated_environment(environment)
    assert cleaned == {
        "PATH": "keep",
        "ENABLE_INSTRUMENTATION": "true",
        "ENABLE_CONSOLE_EXPORTERS": "false",
        "ENABLE_SENSITIVE_DATA": "false",
    }


@pytest.mark.parametrize(
    "payload",
    [
        [],
        {},
        {"spans": [None]},
        {"spans": [{}]},
        {"spans": [{"name": "chat"}]},
        {"spans": [{"name": "chat", "span_id": "1", "parent_id": 1}]},
        {"spans": [{"name": "chat", "span_id": "1", "parent_id": None}]},
        {"spans": [], "response": None},
        {"spans": [], "response": "text", "exported": "no"},
    ],
)
def test_malformed_worker_payload_is_rejected(payload: object) -> None:
    with pytest.raises(TypeError):
        demo._decode_capture(json.dumps(payload).encode())


@pytest.mark.parametrize(
    "spans",
    [
        [],
        [span("chat", "chat", None)],
        [span("execute_tool", "tool", None)],
        [
            span("execute_tool", "tool", "parent"),
            span("other", "parent", None),
        ],
        [span("execute_tool", "tool", "chat"), span("chat", "chat", None)],
        [
            span("execute_tool", "tool", "chat"),
            span("chat", "chat", "parent"),
            span("other", "parent", None),
        ],
    ],
)
def test_malformed_span_tree_is_not_reported_as_success(
    spans: list[demo.SpanRecord],
) -> None:
    with pytest.raises(ValueError, match="Expected invoke_agent"):
        demo._validate_tree(spans)


def test_span_without_context_is_rejected() -> None:
    from opentelemetry.sdk.trace import ReadableSpan

    with pytest.raises(ValueError, match="missing its span context"):
        demo._span_record(ReadableSpan("missing-context"))


def test_optional_azure_constructor_uses_the_verified_signature() -> None:
    from types import SimpleNamespace

    from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
        InMemorySpanExporter,
    )

    exporter = InMemorySpanExporter()

    def construct(
        *, connection_string: str, disable_offline_storage: bool
    ) -> SpanExporter:
        assert connection_string == "secret"
        assert disable_offline_storage is True
        return exporter

    def loader(name: str) -> object:
        assert name == "azure.monitor.opentelemetry.exporter"
        return SimpleNamespace(AzureMonitorTraceExporter=construct)

    assert demo._azure_exporter(environment={}) is None
    assert (
        demo._azure_exporter(
            environment={
                "MSAI_TRACE_DESTINATION": "azure",
                "APPLICATIONINSIGHTS_CONNECTION_STRING": "secret",
            },
            sdk_loader=loader,
        )
        is exporter
    )


def run_measured_capture(export_kind: str) -> demo.TraceCapture:
    """Execute a real SDK turn in the test's isolated child process."""
    from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult

    class TestExporter(SpanExporter):
        def export(self, spans: object) -> SpanExportResult:
            assert spans
            if export_kind == "success":
                return SpanExportResult.SUCCESS
            return SpanExportResult.FAILURE

    exporter = None if export_kind == "none" else TestExporter()
    return asyncio.run(demo._capture_turn(exporter))


@pytest.mark.parametrize("export_kind", ["none", "success", "failure"])
def test_typed_worker_with_real_sdk_and_local_exporters(
    export_kind: str, tmp_path: Path
) -> None:
    from coverage import Coverage

    # OTel providers cannot be replaced safely inside pytest's process.
    # Measure the real worker separately and merge its coverage using
    # coverage.py's public data API, without patching the application.
    child_data = tmp_path / ".coverage.worker"
    program = (
        "import json,sys; from coverage import Coverage; "
        "cov=Coverage(data_file=sys.argv[1],branch=True,config_file=False,"
        "source=['msai_demo.observability_demo']); cov.start(); "
        "from tests.test_observability_demo import run_measured_capture; "
        "print(json.dumps(run_measured_capture(sys.argv[2]))); "
        "cov.stop(); cov.save()"
    )

    async def run() -> bytes:
        child = await asyncio.create_subprocess_exec(
            sys.executable,
            "-c",
            program,
            str(child_data),
            export_kind,
            env=demo._isolated_environment(os.environ),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        output, errors = await child.communicate()
        assert child.returncode == 0, errors.decode()
        return output

    capture_result = demo._decode_capture(asyncio.run(run()))
    demo._validate_tree(capture_result["spans"])
    assert capture_result["exported"] is (export_kind == "success")
    current = Coverage.current()
    if current is not None:
        measured = Coverage(data_file=str(child_data), config_file=False)
        measured.load()
        current.get_data().update(measured.get_data())


def test_cli_local_alias_captures_in_memory() -> None:
    result = asyncio.run(
        demo.run_observability_demo(trace="local", port=TracePort())
    )
    assert result["data"] is not None
    assert result["data"]["trace_destination"] == "memory"


def test_cli_off_does_not_start_an_agent_or_exporter() -> None:
    result = asyncio.run(demo.run_observability_demo(trace="off"))
    assert result["mode"] == "local_contract"
    assert result["data"] is not None
    assert result["data"]["exported"] is False
    assert result["evidence"]["sdk_invoked"] is False

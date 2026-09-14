"""Current Agent Framework telemetry, captured in memory by default.

A fresh process keeps OpenTelemetry's process-global providers and
environment-driven exporters out of ordinary workshop commands. The
agent and its costing tool really run; only inference is scripted.

Run it:

    uv run msai-demo otel
    uv run msai-demo otel --trace azure
"""

from __future__ import annotations

import asyncio
import importlib
import json
import os
import sys
from typing import TYPE_CHECKING, Any, Protocol, TypedDict, cast

from msai_demo import scenario
from msai_demo.contracts import (
    DemoResult,
    evidence,
    missing_configuration,
    result,
)

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Mapping

    from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
    from opentelemetry.sdk.trace.export import SpanExporter

DEMO_NAME = "otel"
TECHNOLOGY = "Agent Framework OpenTelemetry GenAI conventions"
METRICS = (
    "gen_ai.client.operation.duration",
    "gen_ai.client.token.usage",
    "agent_framework.function.invocation.duration",
)

# Provider setup is isolated because OTel providers are process-global.
_CAPTURE_PROGRAM = (
    "import asyncio,json; "
    "from msai_demo.observability_demo import _capture_turn,_azure_exporter; "
    "print(json.dumps(asyncio.run(_capture_turn(_azure_exporter()))))"
)


class SpanRecord(TypedDict):
    """A captured SDK span, its parent and GenAI attributes."""

    name: str
    span_id: str
    parent_id: str | None
    attributes: dict[str, object]


class TraceCapture(TypedDict):
    """The safe portion of one isolated telemetry capture."""

    spans: list[SpanRecord]
    response: str
    exported: bool


class _ExporterFactory(Protocol):
    """The optional exporter's constructor signature."""

    def __call__(
        self, *, connection_string: str, disable_offline_storage: bool
    ) -> SpanExporter:
        """Construct the exporter without storing failed batches."""


class _AzureExporterModule(Protocol):
    """Convert the optional Azure package into a typed SDK boundary."""

    AzureMonitorTraceExporter: _ExporterFactory


def _azure_exporter(
    *,
    environment: Mapping[str, str] | None = None,
    sdk_loader: Callable[[str], object] = importlib.import_module,
) -> SpanExporter | None:
    """Construct Azure export only in the explicitly opted-in worker."""
    settings = os.environ if environment is None else environment
    if settings.get("MSAI_TRACE_DESTINATION") != "azure":
        return None
    module = cast(
        "_AzureExporterModule",
        sdk_loader("azure.monitor.opentelemetry.exporter"),
    )
    return module.AzureMonitorTraceExporter(
        connection_string=settings["APPLICATIONINSIGHTS_CONNECTION_STRING"],
        disable_offline_storage=True,
    )


async def _capture_turn(exporter: SpanExporter | None = None) -> TraceCapture:
    """Run once in a fresh process and record the actual SDK spans."""
    from agent_framework import Agent, tool
    from agent_framework.observability import (
        ChatTelemetryLayer,
        configure_otel_providers,
    )
    from opentelemetry import trace
    from opentelemetry.sdk.trace.export import SpanExportResult
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
        InMemorySpanExporter,
    )

    from msai_demo.offline import ScriptedChatClient

    # The scripted provider has no vendor telemetry layer. Reuse the
    # SDK layer so chat spans wrap the genuine tool-calling loop.
    class TracedOfflineClient(  # type: ignore[misc]  # SDK overloads differ.
        ChatTelemetryLayer[Any], ScriptedChatClient
    ):
        """The offline provider with the SDK's chat instrumentation."""

    @tool(approval_mode="never_require")
    def price_support_pilot() -> str:
        """Compute the pilot cost without accepting any work."""
        return json.dumps(scenario.price_pilot())

    memory = InMemorySpanExporter()
    configure_otel_providers(
        exporters=[memory],
        enable_sensitive_data=False,
        enable_console_exporters=False,
        enable_message_events=False,
        service_name="msai-demo-otel",
    )
    provider = cast("TracerProvider", trace.get_tracer_provider())
    try:
        client = TracedOfflineClient(
            replies=["Pilot costed; human approval is still required."],
            tool_plan=[("price_support_pilot", {})],
            otel_provider_name="offline",
        )
        agent = Agent(
            client=client, name="PilotArchitect", tools=price_support_pilot
        )
        reply = await agent.run(scenario.BRIEF)
        provider.force_flush()
        spans = memory.get_finished_spans()
        exported = False
        if exporter is not None:
            exported = exporter.export(spans) == SpanExportResult.SUCCESS
            exporter.shutdown()
        rows = [_span_record(span) for span in spans]
        return {"spans": rows, "response": reply.text, "exported": exported}
    finally:
        provider.shutdown()


def _span_record(span: ReadableSpan) -> SpanRecord:
    """Keep parent links and GenAI attributes from one SDK span."""
    context = span.get_span_context()
    if context is None:
        message = "An SDK span is missing its span context."
        raise ValueError(message)
    return {
        "name": span.name,
        "span_id": format(context.span_id, "016x"),
        "parent_id": (
            format(span.parent.span_id, "016x")
            if span.parent is not None
            else None
        ),
        "attributes": {
            key: value
            for key, value in (span.attributes or {}).items()
            if key.startswith("gen_ai.")
        },
    }


class ObservabilityPort(Protocol):
    """Capture an agent turn; remote export needs explicit opt-in."""

    async def capture(
        self, *, trace: str, connection_string: str | None
    ) -> TraceCapture:
        """Return captured spans and the actual export outcome."""


class CaptureProcess(Protocol):
    """The subprocess interface needed for an isolated capture."""

    @property
    def returncode(self) -> int | None:
        """Return the worker's exit status."""

    async def communicate(self) -> tuple[bytes, bytes]:
        """Drain both worker pipes and wait for termination."""

    def kill(self) -> None:
        """Terminate a worker that exceeded its deadline."""


async def _start_capture(environment: dict[str, str]) -> CaptureProcess:
    """Start the fixed program with pipes, never a shell command."""
    return await asyncio.create_subprocess_exec(
        sys.executable,
        "-c",
        _CAPTURE_PROGRAM,
        env=environment,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )


class LocalObservabilityPort:
    """Own a fresh SDK process so telemetry settings cannot leak."""

    def __init__(
        self,
        *,
        process_factory: Callable[
            [dict[str, str]], Awaitable[CaptureProcess]
        ] = _start_capture,
        sdk_loader: Callable[[str], object] = importlib.import_module,
        timeout: float = 45,
    ) -> None:
        """Accept process and SDK boundaries for failure tests."""
        self._process_factory = process_factory
        self._sdk_loader = sdk_loader
        self._timeout = timeout

    async def capture(
        self, *, trace: str, connection_string: str | None
    ) -> TraceCapture:
        """Run the offline provider with a real in-memory exporter.

        Args:
            trace: ``memory`` or explicitly requested ``azure``.
            connection_string: Optional Azure Monitor configuration.

        Returns:
            Validated, JSON-safe spans with no prompt or tool arguments.
        """
        self._sdk_loader("agent_framework.observability")
        if trace == "azure":
            self._sdk_loader("azure.monitor.opentelemetry.exporter")
        environment = _isolated_environment(os.environ)
        environment["MSAI_TRACE_DESTINATION"] = trace
        if connection_string is not None:
            environment["APPLICATIONINSIGHTS_CONNECTION_STRING"] = (
                connection_string
            )
        process = await self._process_factory(environment)
        try:
            output, _ = await asyncio.wait_for(
                process.communicate(), timeout=self._timeout
            )
        except TimeoutError:
            process.kill()
            await process.communicate()
            raise
        if process.returncode != 0:
            # SDK errors may contain endpoints or credentials. Do not
            # forward child stderr into the workshop result envelope.
            message = "The isolated telemetry worker failed."
            raise RuntimeError(message)
        return _decode_capture(output)


def _isolated_environment(environment: Mapping[str, str]) -> dict[str, str]:
    """Remove every ambient exporter setting before the child starts."""
    cleaned = {
        name: value
        for name, value in environment.items()
        if not name.startswith("OTEL_")
        and name
        not in {
            "APPLICATIONINSIGHTS_CONNECTION_STRING",
            "VS_CODE_EXTENSION_PORT",
            "MSAI_TRACE_DESTINATION",
        }
    }
    cleaned.update(
        ENABLE_INSTRUMENTATION="true",
        ENABLE_SENSITIVE_DATA="false",
        ENABLE_CONSOLE_EXPORTERS="false",
    )
    return cleaned


def _decode_capture(output: bytes) -> TraceCapture:
    """Validate the subprocess boundary before assigning local types."""
    payload: object = json.loads(output)
    if not isinstance(payload, dict):
        message = "Telemetry capture must be an object."
        raise TypeError(message)
    spans = payload.get("spans")
    if not isinstance(spans, list):
        message = "Telemetry capture must contain a span list."
        raise TypeError(message)
    for span in spans:
        if (
            not isinstance(span, dict)
            or not isinstance(span.get("name"), str)
            or not isinstance(span.get("span_id"), str)
            or not isinstance(span.get("parent_id"), (str, type(None)))
            or not isinstance(span.get("attributes"), dict)
        ):
            message = "Telemetry capture contains a malformed span."
            raise TypeError(message)
    if not isinstance(payload.get("response"), str) or not isinstance(
        payload.get("exported"), bool
    ):
        message = "Telemetry capture is missing its response or export status."
        raise TypeError(message)
    return cast("TraceCapture", payload)


def _validate_tree(spans: list[SpanRecord]) -> None:
    """Require the SDK's real agent, chat and nested tool spans."""
    by_id = {span["span_id"]: span for span in spans}
    for tool_span in spans:
        if (
            tool_span["attributes"].get("gen_ai.operation.name")
            != "execute_tool"
        ):
            continue
        chat = by_id.get(tool_span["parent_id"] or "")
        if (
            chat is None
            or chat["attributes"].get("gen_ai.operation.name") != "chat"
        ):
            continue
        agent = by_id.get(chat["parent_id"] or "")
        if (
            agent is not None
            and agent["attributes"].get("gen_ai.operation.name")
            == "invoke_agent"
        ):
            return
    message = "Expected invoke_agent -> chat -> execute_tool span tree."
    raise ValueError(message)


async def run_observability_demo(
    *,
    execution: str = "offline",
    trace: str = "memory",
    port: ObservabilityPort | None = None,
    environment: Mapping[str, str] | None = None,
) -> DemoResult:
    """Capture an offline agent turn, optionally exporting to Azure.

    Args:
        execution: Runner consistency option; inference stays offline.
        trace: ``memory``/``local`` capture; ``azure`` exports;
            ``off`` skips tracing.
        port: Optional adapter for isolated, deterministic tests.
        environment: Configuration override without process mutation.

    Returns:
        The captured tree, GenAI attributes and export evidence.
    """
    del execution
    if trace == "off":
        return result(
            demo=DEMO_NAME,
            technology=TECHNOLOGY,
            lane="current",
            mode="local_contract",
            status="ok",
            headline="Tracing is off; no agent turn or exporter was started.",
            evidence=evidence(provider="none", fixture_id="otel-contract-v1"),
            data={
                "trace_destination": "off",
                "expected_operations": [
                    "invoke_agent",
                    "chat",
                    "execute_tool",
                ],
                "metrics": list(METRICS),
                "exported": False,
            },
            next_steps=[
                "Pass --trace local to capture a real offline agent turn."
            ],
        )
    if trace == "local":
        trace = "memory"
    if trace not in {"memory", "azure"}:
        message = "trace must be 'off', 'local', 'memory' or 'azure'."
        raise ValueError(message)
    settings = os.environ if environment is None else environment
    connection = settings.get(
        "APPLICATIONINSIGHTS_CONNECTION_STRING", ""
    ).strip()
    if trace == "azure" and not connection:
        return missing_configuration(
            demo=DEMO_NAME,
            technology=TECHNOLOGY,
            lane="current",
            provider="azure-monitor",
            missing=["APPLICATIONINSIGHTS_CONNECTION_STRING"],
            next_steps=["Set the connection string and pass --trace azure."],
        )
    selected = port or LocalObservabilityPort()
    try:
        capture = await selected.capture(
            trace=trace,
            connection_string=connection if trace == "azure" else None,
        )
    except ModuleNotFoundError:
        return result(
            demo=DEMO_NAME,
            technology=TECHNOLOGY,
            lane="current",
            mode="local_contract",
            status="blocked",
            headline="Telemetry SDK unavailable; no agent turn or export ran.",
            evidence=evidence(
                provider="offline", fixture_id="otel-contract-v1"
            ),
            data={
                "expected_operations": ["invoke_agent", "chat", "execute_tool"]
            },
            error={
                "code": "missing_sdk",
                "message": "Install the telemetry SDK.",
            },
            next_steps=[
                "Install agent-framework-core and opentelemetry-sdk; "
                "Azure export also needs azure-monitor-opentelemetry-exporter."
            ],
        )
    _validate_tree(capture["spans"])
    remote = trace == "azure"
    return result(
        demo=DEMO_NAME,
        technology=TECHNOLOGY,
        lane="current",
        mode="live_service" if remote else "local_execution",
        status="error" if remote and not capture["exported"] else "ok",
        headline=(
            "Captured invoke_agent -> chat -> execute_tool "
            "on the offline provider."
        ),
        evidence=evidence(
            provider="azure-monitor" if remote else "offline",
            sdk_invoked=True,
            network_attempted=remote,
            service_executed=remote and capture["exported"],
        ),
        data={
            "scenario_id": scenario.SCENARIO_ID,
            "cost": scenario.price_pilot(),
            "spans": capture["spans"],
            "response": capture["response"],
            "trace_destination": trace,
            "exported": capture["exported"],
            "metrics": list(METRICS),
            "usage": None,
            "metrics_note": (
                "The SDK defines these instruments. This demo captures spans; "
                "the scripted provider reports no token counts."
            ),
            "sensitive_data": (
                "ENABLE_SENSITIVE_DATA records prompts, responses and tool "
                "arguments. Keep it off outside development; it is forced "
                "off for this capture."
            ),
            "isolation": (
                "A fresh process prevents ambient exporters or repeated "
                "provider configuration from leaking into ordinary commands."
            ),
        },
        error=(
            {
                "code": "export_failed",
                "message": "Azure Monitor rejected export.",
            }
            if remote and not capture["exported"]
            else None
        ),
    )

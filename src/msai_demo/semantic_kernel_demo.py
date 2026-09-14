"""Semantic Kernel: a maintained legacy runtime with a pinned Azure SDK.

The native plugin body still runs without the optional package. Its
kernel registration is then a named contract fixture. In an isolated
environment with Semantic Kernel installed, the real kernel invokes
that same body and its filter locally. No model call is needed.

Agent Framework moves Kernel to Agent, plugins to tools, filters to
middleware and planners to workflows. New features go there; Semantic
Kernel 1.x continues to receive critical bug and security fixes.

Run it:

    uv run msai-demo semantic-kernel
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from importlib import import_module
from typing import TYPE_CHECKING, ParamSpec, Protocol, TypeVar, cast

from msai_demo import scenario
from msai_demo.contracts import (
    DemoResult,
    Mode,
    evidence,
    missing_configuration,
    result,
)

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

DEMO_NAME = "semantic-kernel"
TECHNOLOGY = "Semantic Kernel 1.44.1 (maintenance mode)"
FIXTURE_ID = "semantic-kernel-plugin-v1"
CONFLICTING_PIN = "azure-ai-projects>=1.0,<2.5"
ISOLATED_COMMAND = (
    'uv run --isolated --with "semantic-kernel>=1.44,<2" --no-project '
    "python -c \"import asyncio, sys; sys.path.insert(0, 'src'); "
    "from msai_demo.semantic_kernel_demo import run_semantic_kernel_demo; "
    'print(asyncio.run(run_semantic_kernel_demo()))"'
)
CONCEPT_MAPPING = {
    "Kernel": "Agent",
    "plugin": "@tool",
    "filter": "middleware",
    "planner": "workflow",
}


@dataclass(frozen=True)
class KernelInvocation:
    """One native invocation, before its value is trusted.

    Attributes:
        value: JSON returned by the plugin, or an invalid SDK value.
        filter_events: Events actually recorded around the body.
    """

    value: object
    filter_events: tuple[str, ...]


class SemanticKernelPort(Protocol):
    """The local native invocation shared by SDK and fixture paths."""

    mode: Mode
    sdk_invoked: bool
    fixture_id: str | None

    async def invoke(self, weeks: int) -> KernelInvocation:
        """Execute the pricing body and return its untrusted value."""


def price_support_pilot(weeks: int = scenario.PILOT_WEEKS) -> str:
    """Cost the pilot with the shared rate card and return JSON.

    Args:
        weeks: Positive pilot length, passed to the shared scenario.

    Returns:
        The complete deterministic cost, ready for a native plugin.
    """
    return json.dumps(scenario.price_pilot(weeks=weeks), sort_keys=True)


class FixtureKernelPort:
    """Run the plugin body; represent SDK registration as a fixture."""

    mode: Mode = "local_contract"
    sdk_invoked = False
    fixture_id: str | None = FIXTURE_ID

    async def invoke(self, weeks: int) -> KernelInvocation:
        """Execute ordinary Python without claiming a kernel ran."""
        return KernelInvocation(price_support_pilot(weeks), ())


class _FunctionResult(Protocol):
    value: object


class _Kernel(Protocol):
    def add_service(self, service: object) -> None:
        """Register a chat connector without invoking it."""

    def add_plugin(self, plugin: object, *, plugin_name: str) -> object:
        """Register a native plugin under its invocation name."""

    def add_filter(
        self,
        filter_type: str,
        callback: Callable[
            [object, Callable[[object], Awaitable[None]]], Awaitable[None]
        ],
    ) -> None:
        """Register a callback around native function invocation."""

    async def invoke(
        self, *, plugin_name: str, function_name: str, weeks: int
    ) -> _FunctionResult | None:
        """Invoke the native pricing function and its filter."""


_Parameters = ParamSpec("_Parameters")
_Return = TypeVar("_Return")


class _FunctionDecorator(Protocol):
    def __call__(
        self, function: Callable[_Parameters, _Return]
    ) -> Callable[_Parameters, _Return]:
        """Mark a Python function as a native kernel function."""


class _ChatConnectorFactory(Protocol):
    def __call__(
        self, *, ai_model_id: str, service_id: str, api_key: str
    ) -> object:
        """Construct a chat connector using explicit inert settings."""


class _KernelModule(Protocol):
    Kernel: Callable[[], _Kernel]


class _FunctionsModule(Protocol):
    kernel_function: _FunctionDecorator


class _ConnectorsModule(Protocol):
    OpenAIChatCompletion: _ChatConnectorFactory


class SdkKernelPort:
    """Invoke a real kernel, native plugin and invocation filter.

    Args:
        kernel: A real Semantic Kernel, or an injected boundary fake.
        kernel_function: The SDK's native function decorator.
        connector: A chat connector that is registered but not called.
    """

    mode: Mode = "local_execution"
    sdk_invoked = True
    fixture_id: str | None = None

    def __init__(
        self,
        *,
        kernel: _Kernel,
        kernel_function: _FunctionDecorator,
        connector: object,
    ) -> None:
        """Register the connector, native plugin and audit filter."""

        class PilotPlugin:
            """Expose deterministic costing to the legacy kernel."""

            @kernel_function
            def price_support_pilot(
                self, weeks: int = scenario.PILOT_WEEKS
            ) -> str:
                """Cost the pilot from the shared rate card."""
                return price_support_pilot(weeks)

        self._kernel = kernel
        self._events: list[str] = []
        kernel.add_service(connector)
        kernel.add_plugin(PilotPlugin(), plugin_name="Pilot")
        # A native invocation runs this filter without using the model.
        kernel.add_filter("function_invocation", self._audit_invocation)

    async def _audit_invocation(
        self,
        context: object,
        call_next: Callable[[object], Awaitable[None]],
    ) -> None:
        """Record events when the kernel enters the filter."""
        self._events.append("before: Pilot.price_support_pilot")
        await call_next(context)
        self._events.append("after: Pilot.price_support_pilot")

    async def invoke(self, weeks: int) -> KernelInvocation:
        """Invoke only the native function; no chat request is sent."""
        self._events.clear()
        response = await self._kernel.invoke(
            plugin_name="Pilot",
            function_name="price_support_pilot",
            weeks=weeks,
        )
        value = None if response is None else response.value
        return KernelInvocation(value, tuple(self._events))


def create_kernel_port(
    *, importer: Callable[[str], object] = import_module
) -> SemanticKernelPort:
    """Use an importable SDK, otherwise execute the contract fixture.

    Args:
        importer: Optional SDK boundary, injectable without patching.

    Returns:
        A local SDK port or the explicitly named contract fixture.

    Raises:
        ModuleNotFoundError: If an SDK dependency is broken. Only an
            absent Semantic Kernel itself permits the fallback.
    """
    try:
        sdk = cast("_KernelModule", importer("semantic_kernel"))
    except ModuleNotFoundError as error:
        if error.name != "semantic_kernel":
            raise
        return FixtureKernelPort()

    # Convert dynamic SDK modules immediately to the narrow contracts.
    functions = cast("_FunctionsModule", importer("semantic_kernel.functions"))
    connectors = cast(
        "_ConnectorsModule",
        importer("semantic_kernel.connectors.ai.open_ai"),
    )
    return SdkKernelPort(
        kernel=sdk.Kernel(),
        kernel_function=functions.kernel_function,
        connector=connectors.OpenAIChatCompletion(
            ai_model_id="unused-offline-model",
            service_id="chat",
            # Explicit inert text prevents environment credentials use.
            api_key="unused-offline-placeholder",
        ),
    )


def _validated_cost(value: object) -> scenario.PilotCost:
    """Require the complete JSON cost to match the shared scenario."""
    if not isinstance(value, str):
        message = "The native pricing plugin must return JSON text."
        raise TypeError(message)
    decoded: object = json.loads(value)
    expected = scenario.price_pilot()
    # JSON comparison also rejects booleans masquerading as integers.
    if json.dumps(decoded, sort_keys=True) != json.dumps(
        expected, sort_keys=True
    ):
        message = "The native pricing result differs from the shared scenario."
        raise ValueError(message)
    return expected


async def run_semantic_kernel_demo(
    *,
    execution: str = "offline",
    port: SemanticKernelPort | None = None,
) -> DemoResult:
    """Show the legacy native plugin and its current replacements.

    Args:
        execution: ``offline`` runs the native body. ``live`` reports
            the missing model adapter before any call.
        port: Injected local invocation port, useful for offline tests.

    Returns:
        Evidence separating actual Python or SDK work from the fixture.

    Raises:
        ValueError: If execution is neither ``offline`` nor ``live``.
    """
    if execution not in {"offline", "live"}:
        message = "execution must be 'offline' or 'live'."
        raise ValueError(message)
    if execution == "live":
        return missing_configuration(
            demo=DEMO_NAME,
            technology=TECHNOLOGY,
            lane="legacy",
            provider="semantic-kernel",
            missing=["an isolated Semantic Kernel model adapter"],
            next_steps=[
                "Use execution='offline' for the native plugin demonstration.",
                "Use Agent Framework provider demos for live model calls.",
            ],
        )

    selected = port if port is not None else create_kernel_port()
    invocation = await selected.invoke(scenario.PILOT_WEEKS)
    record = evidence(
        provider="semantic-kernel",
        sdk_invoked=selected.sdk_invoked,
        fixture_id=selected.fixture_id,
    )
    try:
        cost = _validated_cost(invocation.value)
    except (TypeError, ValueError):
        return result(
            demo=DEMO_NAME,
            technology=TECHNOLOGY,
            lane="legacy",
            mode=selected.mode,
            status="error",
            headline="The native plugin returned an invalid pilot cost.",
            evidence=record,
            error={
                "code": "malformed_response",
                "message": "Expected the complete shared scenario cost JSON.",
            },
        )

    acceptable, failures = scenario.proposal_is_acceptable(
        cost=cost, approved=False, cited_sources=["scenario.rate_card"]
    )
    return result(
        demo=DEMO_NAME,
        technology=TECHNOLOGY,
        lane="legacy",
        mode=selected.mode,
        status="ok",
        headline="The pricing plugin ran; proposal acceptance needs a human.",
        evidence=record,
        data={
            "scenario_id": scenario.SCENARIO_ID,
            "brief": scenario.BRIEF,
            "cost": cost,
            "approved": False,
            "acceptable": acceptable,
            "acceptance_failures": failures,
            "filter_events": list(invocation.filter_events),
            "kernel_contract": {
                "kernel": "Kernel()",
                "connector": "OpenAIChatCompletion",
                "connector_invoked": False,
                "plugin": "@kernel_function Pilot.price_support_pilot",
                "filter": "add_filter('function_invocation', audit_filter)",
                "invocation": (
                    "await kernel.invoke(plugin_name='Pilot', "
                    "function_name='price_support_pilot', "
                    f"weeks={scenario.PILOT_WEEKS})"
                ),
                "synthetic_registration": selected.fixture_id is not None,
            },
            "conflicting_pin": CONFLICTING_PIN,
            "current_dependency": "azure-ai-projects==2.6.0",
            "dependency_lesson": (
                "Semantic Kernel and the current Foundry SDK cannot share "
                "this lockfile. --no-project keeps the isolated command "
                "from resolving the workspace dependencies."
            ),
            "isolated_command": ISOLATED_COMMAND,
            "replacement": "Microsoft Agent Framework",
            "concept_mapping": dict(CONCEPT_MAPPING),
            "migration_reason": (
                "Agent Framework unifies agents, tools and workflows; "
                "new feature work happens there. Semantic Kernel 1.x "
                "still receives critical bug and security fixes."
            ),
        },
    )

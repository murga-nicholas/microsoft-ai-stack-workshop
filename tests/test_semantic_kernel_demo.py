from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from types import SimpleNamespace
from typing import TYPE_CHECKING, ParamSpec, Protocol, TypeVar, cast

import pytest

from msai_demo import scenario
from msai_demo import semantic_kernel_demo as demo

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from msai_demo.contracts import Mode


class _Plugin(Protocol):
    def price_support_pilot(self, weeks: int) -> str: ...


@dataclass
class _FunctionResult:
    value: object


_Parameters = ParamSpec("_Parameters")
_Return = TypeVar("_Return")


def _decorate(
    function: Callable[_Parameters, _Return],
) -> Callable[_Parameters, _Return]:
    return function


class _FakeKernel:
    def __init__(self, *, empty_response: bool = False) -> None:
        self.empty_response = empty_response
        self.services: list[object] = []
        self.plugin: _Plugin
        self.filter_callback: Callable[
            [object, Callable[[object], Awaitable[None]]], Awaitable[None]
        ]
        self.calls: list[int] = []

    def add_service(self, service: object) -> None:
        self.services.append(service)

    def add_plugin(self, plugin: object, *, plugin_name: str) -> object:
        assert plugin_name == "Pilot"
        self.plugin = cast("_Plugin", plugin)
        return plugin

    def add_filter(
        self,
        filter_type: str,
        callback: Callable[
            [object, Callable[[object], Awaitable[None]]], Awaitable[None]
        ],
    ) -> None:
        assert filter_type == "function_invocation"
        self.filter_callback = callback

    async def invoke(
        self, *, plugin_name: str, function_name: str, weeks: int
    ) -> _FunctionResult | None:
        assert plugin_name == "Pilot"
        assert function_name == "price_support_pilot"
        self.calls.append(weeks)
        if self.empty_response:
            return None
        response = _FunctionResult(None)

        async def invoke_body(context: object) -> None:
            assert context is response
            response.value = self.plugin.price_support_pilot(weeks)

        await self.filter_callback(response, invoke_body)
        return response


class _FakeImporter:
    def __init__(self, kernel: _FakeKernel) -> None:
        self.kernel = kernel
        self.imports: list[str] = []
        self.connector_options: dict[str, str] = {}

    def connector(
        self, *, ai_model_id: str, service_id: str, api_key: str
    ) -> object:
        self.connector_options = {
            "ai_model_id": ai_model_id,
            "service_id": service_id,
            "api_key": api_key,
        }
        return self.connector_options

    def __call__(self, name: str) -> object:
        self.imports.append(name)
        return {
            "semantic_kernel": SimpleNamespace(Kernel=lambda: self.kernel),
            "semantic_kernel.functions": SimpleNamespace(
                kernel_function=_decorate
            ),
            "semantic_kernel.connectors.ai.open_ai": SimpleNamespace(
                OpenAIChatCompletion=self.connector
            ),
        }[name]


@dataclass
class _FakePort:
    value: object
    mode: Mode = "local_contract"
    sdk_invoked: bool = False
    fixture_id: str | None = "semantic-kernel-malformed-test-v1"

    async def invoke(self, weeks: int) -> demo.KernelInvocation:
        assert weeks == scenario.PILOT_WEEKS
        return demo.KernelInvocation(self.value, ())


def test_fixture_executes_shared_plugin_without_accepting() -> None:
    response = asyncio.run(
        demo.run_semantic_kernel_demo(port=demo.FixtureKernelPort())
    )
    assert response["demo"] == "semantic-kernel"
    assert response["status"] == "ok"
    assert response["mode"] == "local_contract"
    assert response["evidence"] == {
        "sdk_invoked": False,
        "network_attempted": False,
        "service_executed": False,
        "provider": "semantic-kernel",
        "fixture_id": "semantic-kernel-plugin-v1",
        "requested_model": None,
        "observed_model": None,
    }
    data = response["data"]
    assert data is not None
    assert data["cost"] == scenario.price_pilot()
    assert data["approved"] is False
    assert data["acceptable"] is False
    assert data["acceptance_failures"] == ["No human approval recorded."]
    assert data["filter_events"] == []
    assert data["kernel_contract"]["synthetic_registration"] is True
    assert data["kernel_contract"]["connector_invoked"] is False
    assert data["conflicting_pin"] == "azure-ai-projects>=1.0,<2.5"
    assert data["current_dependency"] == "azure-ai-projects==2.6.0"
    assert data["concept_mapping"] == {
        "Kernel": "Agent",
        "plugin": "@tool",
        "filter": "middleware",
        "planner": "workflow",
    }
    assert '--with "semantic-kernel>=1.44,<2"' in data["isolated_command"]
    assert "--isolated" in data["isolated_command"]
    assert "--no-project" in data["isolated_command"]
    assert "sys.path.insert(0, 'src')" in data["isolated_command"]


def test_default_runner_is_useful_without_credentials() -> None:
    response = asyncio.run(demo.run_semantic_kernel_demo())
    assert response["status"] == "ok"
    assert response["mode"] in {"local_contract", "local_execution"}
    assert response["evidence"]["network_attempted"] is False
    assert response["data"] is not None
    assert response["data"]["cost"] == scenario.price_pilot()


def test_plugin_preserves_scenario_arguments_and_validation() -> None:
    assert json.loads(demo.price_support_pilot(3)) == scenario.price_pilot(
        weeks=3
    )
    with pytest.raises(ValueError, match="weeks must be positive"):
        demo.price_support_pilot(0)


def test_absent_sdk_selects_named_fixture() -> None:
    def absent(name: str) -> object:
        assert name == "semantic_kernel"
        raise ModuleNotFoundError(name=name)

    selected = demo.create_kernel_port(importer=absent)
    assert isinstance(selected, demo.FixtureKernelPort)
    assert selected.fixture_id == "semantic-kernel-plugin-v1"


def test_broken_sdk_dependency_is_not_silently_hidden() -> None:
    def broken(name: str) -> object:
        assert name == "semantic_kernel"
        raise ModuleNotFoundError(name="broken_dependency")

    with pytest.raises(ModuleNotFoundError) as raised:
        demo.create_kernel_port(importer=broken)
    assert raised.value.name == "broken_dependency"


def test_importable_sdk_registers_plugin_connector_and_real_filter() -> None:
    kernel = _FakeKernel()
    importer = _FakeImporter(kernel)
    selected = demo.create_kernel_port(importer=importer)
    response = asyncio.run(demo.run_semantic_kernel_demo(port=selected))
    assert response["mode"] == "local_execution"
    assert response["evidence"]["sdk_invoked"] is True
    assert response["evidence"]["fixture_id"] is None
    assert response["evidence"]["network_attempted"] is False
    assert importer.imports == [
        "semantic_kernel",
        "semantic_kernel.functions",
        "semantic_kernel.connectors.ai.open_ai",
    ]
    assert importer.connector_options == {
        "ai_model_id": "unused-offline-model",
        "service_id": "chat",
        "api_key": "unused-offline-placeholder",
    }
    assert kernel.services == [importer.connector_options]
    assert kernel.calls == [scenario.PILOT_WEEKS]
    assert response["data"] is not None
    assert response["data"]["cost"] == scenario.price_pilot()
    assert (
        response["data"]["kernel_contract"]["synthetic_registration"] is False
    )
    expected_events = (
        "before: Pilot.price_support_pilot",
        "after: Pilot.price_support_pilot",
    )
    assert response["data"]["filter_events"] == list(expected_events)
    # Each invocation owns its own event record; no stale events leak.
    second = asyncio.run(selected.invoke(scenario.PILOT_WEEKS))
    assert second.filter_events == expected_events


def test_none_sdk_result_reports_malformed_response() -> None:
    selected = demo.create_kernel_port(
        importer=_FakeImporter(_FakeKernel(empty_response=True))
    )
    response = asyncio.run(demo.run_semantic_kernel_demo(port=selected))
    assert response["status"] == "error"
    assert response["mode"] == "local_execution"
    assert response["error"] is not None
    assert response["error"]["code"] == "malformed_response"


@pytest.mark.parametrize("payload", [None, 7, "not JSON", "{}", "[]", "null"])
def test_malformed_plugin_output_cannot_become_success(
    payload: object,
) -> None:
    response = asyncio.run(
        demo.run_semantic_kernel_demo(port=_FakePort(payload))
    )
    assert response["status"] == "error"
    assert response["data"] is None
    assert response["error"] is not None
    assert response["error"]["code"] == "malformed_response"


@pytest.mark.parametrize(
    ("field", "value"),
    [("within_budget", 1), ("weeks", float(scenario.PILOT_WEEKS))],
)
def test_cost_values_must_preserve_json_types(
    field: str, value: object
) -> None:
    cost: dict[str, object] = dict(scenario.price_pilot())
    cost[field] = value
    response = asyncio.run(
        demo.run_semantic_kernel_demo(port=_FakePort(json.dumps(cost)))
    )
    assert response["status"] == "error"
    assert response["error"] is not None
    assert response["error"]["code"] == "malformed_response"


def test_live_stops_before_invoking_an_injected_port() -> None:
    response = asyncio.run(
        demo.run_semantic_kernel_demo(
            execution="live", port=_FakePort("invalid if called")
        )
    )
    assert response["mode"] == "not_run"
    assert response["status"] == "blocked"
    assert response["evidence"]["sdk_invoked"] is False
    assert response["evidence"]["network_attempted"] is False
    assert response["error"] is not None
    assert response["error"]["code"] == "missing_configuration"


def test_invalid_execution_is_rejected() -> None:
    with pytest.raises(ValueError, match="execution must be"):
        asyncio.run(demo.run_semantic_kernel_demo(execution="typo"))


def test_unexpected_port_failure_propagates() -> None:
    class DeniedPort(demo.FixtureKernelPort):
        async def invoke(self, weeks: int) -> demo.KernelInvocation:
            assert weeks == scenario.PILOT_WEEKS
            message = "403: synthetic adapter failure"
            raise PermissionError(message)

    # No network path exists here, so do not manufacture live evidence.
    with pytest.raises(PermissionError, match="403"):
        asyncio.run(demo.run_semantic_kernel_demo(port=DeniedPort()))

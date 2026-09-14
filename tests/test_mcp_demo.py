from __future__ import annotations

import asyncio
import json
from typing import cast

import pytest

from msai_demo import scenario
from msai_demo.mcp_demo import (
    PROTOCOL_VERSION,
    TOOL_NAME,
    LocalMCPPort,
    run_mcp_demo,
)


class RewritePort:
    agent_available = False

    def __init__(self, method: str = "", response: str | None = None) -> None:
        self.local = LocalMCPPort()
        self.method = method
        self.response = response

    async def exchange(self, request: str) -> str | None:
        decoded = json.loads(request)
        response = await self.local.exchange(request)
        if decoded["method"] == self.method:
            return self.response
        return response


class FailedPort:
    agent_available = False

    def __init__(self, error: Exception) -> None:
        self.error = error

    async def exchange(self, request: str) -> str | None:
        del request
        raise self.error


def rpc_result(value: object, request_id: int = 2) -> str:
    return json.dumps({"jsonrpc": "2.0", "id": request_id, "result": value})


def test_agent_discovers_and_calls_costing_tool() -> None:
    result = asyncio.run(run_mcp_demo())
    assert result["mode"] == "local_execution"
    assert result["status"] == "ok"
    assert result["evidence"]["sdk_invoked"] is True
    assert result["evidence"]["network_attempted"] is False
    data = result["data"]
    assert data is not None
    assert data["tool_result"]["structuredContent"] == scenario.price_pilot()
    assert data["agent_executed"] is True
    assert data["accept_proposal_executed"] is False
    assert data["protocol_steps"][-1] == "tools/call"
    assert "params._meta" in data["trace_context"]


def test_missing_sdk_still_executes_the_real_protocol() -> None:
    result = asyncio.run(run_mcp_demo(port=RewritePort()))
    assert result["status"] == "ok"
    assert result["evidence"]["sdk_invoked"] is False
    assert result["data"] is not None
    assert result["data"]["agent_executed"] is False
    assert json.loads(result["data"]["agent_reply"]) == scenario.price_pilot()


def test_unconfigured_live_path_never_touches_the_port() -> None:
    result = asyncio.run(
        run_mcp_demo(execution="live", port=FailedPort(AssertionError()))
    )
    assert result["mode"] == "not_run"
    assert result["error"] is not None
    assert result["error"]["code"] == "missing_configuration"


def test_invalid_execution_is_rejected() -> None:
    with pytest.raises(ValueError, match="execution must"):
        asyncio.run(run_mcp_demo(execution="typo"))


@pytest.mark.parametrize(
    ("error", "status", "code"),
    [
        (PermissionError("403"), "blocked", "authorization_denied"),
        (TimeoutError(), "error", "protocol_error"),
        (ValueError(), "error", "protocol_error"),
        (TypeError(), "error", "protocol_error"),
    ],
)
def test_known_transport_errors(
    error: Exception, status: str, code: str
) -> None:
    result = asyncio.run(run_mcp_demo(port=FailedPort(error)))
    assert result["status"] == status
    assert result["error"] is not None
    assert result["error"]["code"] == code


def test_unexpected_programming_errors_are_not_hidden() -> None:
    with pytest.raises(RuntimeError):
        asyncio.run(run_mcp_demo(port=FailedPort(RuntimeError())))


@pytest.mark.parametrize(
    ("method", "response"),
    [
        ("initialize", None),
        ("initialize", "not JSON"),
        ("initialize", "[]"),
        ("initialize", rpc_result({}, 1)),
        ("initialize", '{"jsonrpc":"1.0","id":1}'),
        ("initialize", '{"jsonrpc":"2.0","id":4}'),
        ("initialize", '{"jsonrpc":"2.0","id":1,"error":{}}'),
        ("initialize", '{"jsonrpc":"2.0","id":1}'),
        ("tools/list", rpc_result({"tools": None})),
        ("tools/list", rpc_result({"tools": []})),
        ("tools/list", rpc_result({"tools": [{}, {}]})),
        ("tools/list", rpc_result({"tools": [None]})),
        ("tools/list", rpc_result({"tools": [{}]})),
        ("tools/call", rpc_result({"isError": True}, 3)),
        ("tools/call", rpc_result({"isError": False}, 3)),
    ],
)
def test_malformed_protocol_responses(
    method: str, response: str | None
) -> None:
    result = asyncio.run(
        run_mcp_demo(port=RewritePort(method=method, response=response))
    )
    assert result["status"] == "error"
    assert result["error"] is not None
    assert result["error"]["code"] == "protocol_error"


def test_failed_tool_call_cannot_be_hidden_by_an_agent_reply() -> None:
    port = RewritePort("tools/call", rpc_result({"isError": True}, 3))
    port.agent_available = True
    result = asyncio.run(run_mcp_demo(port=port))
    assert result["status"] == "error"
    assert result["evidence"]["sdk_invoked"] is True


async def send(
    port: LocalMCPPort,
    method: str,
    params: object = None,
    version: str = "2.0",
) -> dict[str, object]:
    response = await port.exchange(
        json.dumps(
            {"jsonrpc": version, "id": 1, "method": method, "params": params}
        )
    )
    return cast("dict[str, object]", json.loads(response or "{}"))


def test_server_requires_initialization_and_rejects_unknown_methods() -> None:
    async def check() -> None:
        port = LocalMCPPort()
        assert "error" in await send(port, "tools/list", version="1.0")
        assert await send(port, "notifications/initialized") == {}
        assert "error" in await send(port, "tools/list")
        initialized = await send(port, "initialize")
        assert PROTOCOL_VERSION in json.dumps(initialized)
        await send(port, "notifications/initialized")
        assert "error" in await send(port, "unknown/method")

    asyncio.run(check())


@pytest.mark.parametrize(
    ("name", "weeks"),
    [("unknown", 6), (TOOL_NAME, True), (TOOL_NAME, "6"), (TOOL_NAME, 0)],
)
def test_server_rejects_invalid_tool_arguments(
    name: str, weeks: object
) -> None:
    async def check() -> None:
        port = LocalMCPPort()
        await send(port, "initialize")
        await send(port, "notifications/initialized")
        response = await send(
            port, "tools/call", {"name": name, "arguments": {"weeks": weeks}}
        )
        assert response["error"] == {
            "code": -32602,
            "message": "Invalid costing arguments.",
        }

    asyncio.run(check())


def test_server_rejects_undeclared_tool_arguments() -> None:
    async def check() -> None:
        port = LocalMCPPort()
        await send(port, "initialize")
        await send(port, "notifications/initialized")
        response = await send(
            port,
            "tools/call",
            {
                "name": TOOL_NAME,
                "arguments": {"weeks": scenario.PILOT_WEEKS, "approved": True},
            },
        )
        assert "error" in response

    asyncio.run(check())

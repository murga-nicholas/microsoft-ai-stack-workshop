"""MCP: a current protocol for discovering and calling agent tools.

The local server exchanges real JSON-RPC messages with a client. An
Agent Framework agent receives the discovered schema and calls the
tool through that client. Only its token generation is scripted.

The optional ``mcp`` package is not installed in the workshop. This
small in-process transport teaches the wire protocol without claiming
to exercise the SDK's stdio, HTTP or WebSocket transport wrappers.

Run it:

    uv run msai-demo mcp
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from importlib.util import find_spec
from typing import TYPE_CHECKING, Protocol, cast

from msai_demo import scenario
from msai_demo.contracts import (
    DemoResult,
    evidence,
    missing_configuration,
    result,
)

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

DEMO_NAME = "mcp"
TECHNOLOGY = "Model Context Protocol in Agent Framework"
PROTOCOL_VERSION = "2025-06-18"
TOOL_NAME = "price_support_pilot"


@dataclass
class _Execution:
    """Track SDK execution even when a later protocol check fails."""

    sdk_invoked: bool = False


class MCPPort(Protocol):
    """The local JSON-RPC transport and agent SDK availability seam."""

    agent_available: bool

    async def exchange(self, request: str) -> str | None:
        """Exchange JSON text; notifications have no response."""


class LocalMCPPort:
    """Execute a deliberately small MCP server inside this process.

    This supports initialization, discovery and one read-only tool.
    It is a teaching endpoint, not a general-purpose MCP server.
    """

    def __init__(self) -> None:
        """Start a new isolated protocol session without credentials."""
        self.agent_available = find_spec("agent_framework") is not None
        self._initialized = False
        self._ready = False

    async def exchange(self, request: str) -> str | None:
        """Decode, handle and encode one actual protocol message."""
        message = _object(json.loads(request))
        if message.get("jsonrpc") != "2.0":
            return _error(message.get("id"), -32600, "Invalid request.")
        method = message.get("method")
        request_id = message.get("id")
        if method == "initialize":
            self._initialized = True
            return _reply(
                request_id,
                {
                    "protocolVersion": PROTOCOL_VERSION,
                    "capabilities": {"tools": {"listChanged": False}},
                    "serverInfo": {"name": "workshop-costing", "version": "1"},
                },
            )
        if method == "notifications/initialized":
            self._ready = self._initialized
            return None
        if not self._ready:
            return _error(request_id, -32002, "Initialize the session first.")
        if method == "tools/list":
            return _reply(request_id, {"tools": [_tool_schema()]})
        if method == "tools/call":
            return self._call(request_id, _object(message.get("params")))
        return _error(request_id, -32601, "Method not found.")

    def _call(self, request_id: object, params: dict[str, object]) -> str:
        """Validate the tool arguments before doing the arithmetic."""
        arguments = _object(params.get("arguments"))
        weeks = arguments.get("weeks")
        if (
            params.get("name") != TOOL_NAME
            or set(arguments) != {"weeks"}
            or type(weeks) is not int
            or weeks <= 0
        ):
            return _error(request_id, -32602, "Invalid costing arguments.")
        cost = scenario.price_pilot(weeks=weeks)
        return _reply(
            request_id,
            {
                "content": [{"type": "text", "text": json.dumps(cost)}],
                "structuredContent": dict(cost),
                "isError": False,
            },
        )


def _object(value: object) -> dict[str, object]:
    """Narrow a decoded JSON object at the untyped boundary."""
    if not isinstance(value, dict):
        message = "Expected a JSON object."
        raise TypeError(message)
    return cast("dict[str, object]", value)


def _reply(request_id: object, payload: dict[str, object]) -> str:
    """Serialize a JSON-RPC success response."""
    return json.dumps({"jsonrpc": "2.0", "id": request_id, "result": payload})


def _error(request_id: object, code: int, message: str) -> str:
    """Serialize a JSON-RPC failure without running the tool."""
    return json.dumps(
        {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": code, "message": message},
        }
    )


def _tool_schema() -> dict[str, object]:
    """Describe the one tool offered by the server."""
    return {
        "name": TOOL_NAME,
        "description": "Cost the support pilot using the shared rate card.",
        "inputSchema": {
            "type": "object",
            "properties": {"weeks": {"type": "integer", "minimum": 1}},
            "required": ["weeks"],
            "additionalProperties": False,
        },
    }


async def _request(
    port: MCPPort,
    method: str,
    params: dict[str, object],
    request_id: int,
) -> dict[str, object]:
    """Validate response correlation before trusting a server result."""
    response = await port.exchange(
        json.dumps(
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "method": method,
                "params": params,
            }
        )
    )
    payload = _object(json.loads(response or "null"))
    if (
        payload.get("jsonrpc") != "2.0"
        or payload.get("id") != request_id
        or "error" in payload
    ):
        message = "MCP returned an invalid or unsuccessful response."
        raise ValueError(message)
    return _object(payload.get("result"))


async def _agent_turn(
    schema: dict[str, object],
    invoke: Callable[[int], Awaitable[str]],
    execution: _Execution,
) -> str:
    """Bridge the discovered schema into the real tool-calling loop."""
    from agent_framework import Agent, FunctionTool

    from msai_demo.providers import create_chat_client

    execution.sdk_invoked = True
    discovered = FunctionTool(
        name=str(schema["name"]),
        description=str(schema["description"]),
        input_model=_object(schema["inputSchema"]),
        func=invoke,
    )
    agent = Agent(
        name="PilotCostingClient",
        client=create_chat_client(
            "offline",
            replies=["Costing received. Human approval is still required."],
            tool_plan=[(discovered.name, {"weeks": scenario.PILOT_WEEKS})],
        ),
        instructions="Call the discovered costing tool before replying.",
        tools=[discovered],
    )
    response = await agent.run(scenario.BRIEF)
    return response.text


async def _exchange(port: MCPPort, execution: _Execution) -> dict[str, object]:
    """Initialize, discover and call across the serialized boundary."""
    initialized = await _request(
        port,
        "initialize",
        {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {},
            "clientInfo": {"name": "workshop-client", "version": "1"},
        },
        1,
    )
    if initialized.get("protocolVersion") != PROTOCOL_VERSION:
        message = "The server selected an unsupported MCP protocol version."
        raise ValueError(message)
    await port.exchange(
        json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"})
    )
    discovery = await _request(port, "tools/list", {}, 2)
    tools = discovery.get("tools")
    if not isinstance(tools, list) or len(tools) != 1:
        message = "The workshop requires exactly one discovered costing tool."
        raise ValueError(message)
    schema = _object(tools[0])
    if schema != _tool_schema():
        message = "The discovered tool does not match the allowed contract."
        raise ValueError(message)
    calls: list[dict[str, object]] = []

    async def invoke(weeks: int) -> str:
        response = await _request(
            port,
            "tools/call",
            {"name": TOOL_NAME, "arguments": {"weeks": weeks}},
            3,
        )
        expected = scenario.price_pilot(weeks=weeks)
        if (
            response.get("isError") is not False
            or response.get("structuredContent") != expected
        ):
            message = "The MCP costing result failed validation."
            raise ValueError(message)
        calls.append(response)
        return json.dumps(response["structuredContent"])

    if port.agent_available:
        reply = await _agent_turn(schema, invoke, execution)
    else:
        reply = await invoke(scenario.PILOT_WEEKS)
    if len(calls) != 1:
        message = "The agent did not complete the discovered tool call."
        raise ValueError(message)
    return {
        "scenario_id": scenario.SCENARIO_ID,
        "protocol_version": PROTOCOL_VERSION,
        "transport": "in-process serialized JSON-RPC",
        "protocol_steps": [
            "initialize",
            "notifications/initialized",
            "tools/list",
            "tools/call",
        ],
        "discovered_tools": [schema],
        "tool_result": calls[0],
        "agent_reply": reply,
        "agent_executed": port.agent_available,
        "model_invoked": False,
        "accept_proposal_executed": False,
    }


async def run_mcp_demo(
    *,
    execution: str = "offline",
    port: MCPPort | None = None,
) -> DemoResult:
    """Execute MCP discovery and a deterministic costing tool call.

    Args:
        execution: ``offline`` for the local protocol demonstration.
            ``live`` reports the absent remote integration.
        port: Optional serialized transport for deterministic tests.

    Returns:
        The protocol exchange and the framework integration choices.

    Raises:
        ValueError: If execution is neither offline nor live.
    """
    if execution not in {"offline", "live"}:
        message = "execution must be offline or live."
        raise ValueError(message)
    if execution == "live":
        return missing_configuration(
            demo=DEMO_NAME,
            technology=TECHNOLOGY,
            lane="current",
            provider="mcp",
            missing=["authenticated remote MCP transport and model port"],
            next_steps=[
                "Connect an MCP transport and configure a live provider.",
                "Use offline to execute the local protocol without keys.",
            ],
        )
    selected = port or LocalMCPPort()
    progress = _Execution()
    try:
        payload = await _exchange(selected, progress)
    except (PermissionError, TimeoutError, TypeError, ValueError) as exc:
        denied = isinstance(exc, PermissionError)
        return result(
            demo=DEMO_NAME,
            technology=TECHNOLOGY,
            lane="current",
            mode="local_execution",
            status="blocked" if denied else "error",
            headline="The local MCP exchange did not complete.",
            evidence=evidence(
                provider="in-process MCP", sdk_invoked=progress.sdk_invoked
            ),
            error={
                "code": "authorization_denied" if denied else "protocol_error",
                "message": "Check transport access and the MCP response.",
            },
        )
    payload.update(
        {
            "integration": (
                "FunctionTool uses the discovered inputSchema. The optional "
                "mcp package is unnecessary for this in-process transport."
            ),
            "local_transports": [
                "MCPStdioTool",
                "MCPStreamableHTTPTool",
                "MCPWebsocketTool",
            ],
            "hosted": (
                "client.get_mcp_tool(name='costing', "
                "url='https://your-server.example/mcp')"
            ),
            "trace_context": (
                "Agent Framework inserts W3C trace context in tools/call "
                "params._meta only for client-opened transports. The local "
                "client owns those requests; hosted MCP is called by the "
                "model service, so this process cannot inject its metadata. "
                "This custom transport does not demonstrate that SDK hook."
            ),
            "sdk_note": (
                "When Agent Framework is absent, the same protocol still "
                "runs directly and agent_executed is false."
            ),
        }
    )
    return result(
        demo=DEMO_NAME,
        technology=TECHNOLOGY,
        lane="current",
        mode="local_execution",
        status="ok",
        headline="Discovered an MCP tool and executed the pilot costing.",
        evidence=evidence(
            provider="offline",
            sdk_invoked=progress.sdk_invoked,
        ),
        data=payload,
    )

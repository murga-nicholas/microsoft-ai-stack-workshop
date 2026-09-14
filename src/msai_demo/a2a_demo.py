"""A2A: delegate a task to another agent using a current protocol.

A small local endpoint serves an agent card, accepts a task and
returns its completed costing artifact. Requests and replies cross a
serialized JSON boundary. No model, socket or Azure service is used.

The endpoint implements a teaching subset of A2A 0.3.0. The Foundry
A2A tool is a separate preview integration, shown as configuration.

Run it:

    uv run msai-demo a2a
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Protocol, cast

from msai_demo import scenario
from msai_demo.contracts import (
    DemoResult,
    evidence,
    missing_configuration,
    result,
)

DEMO_NAME = "a2a"
TECHNOLOGY = "Agent2Agent (A2A)"
CARD_PATH = "/.well-known/agent-card.json"
TASK_PATH = "/a2a"


@dataclass(frozen=True)
class A2AResponse:
    """An HTTP-shaped response from the injected in-process endpoint.

    Attributes:
        status_code: HTTP status represented by the endpoint.
        body: Serialized JSON, decoded only by the client.
    """

    status_code: int
    body: str


class A2APort(Protocol):
    """The endpoint boundary, preserving method, path and JSON bytes."""

    async def request(
        self, method: str, path: str, body: str = ""
    ) -> A2AResponse:
        """Route a request without an external network call."""


class LocalA2APort:
    """Run a small A2A agent endpoint with isolated task storage.

    The endpoint owns task state and artifacts. It completes drafting
    only; accepting a proposal remains a separate human-gated action.
    """

    def __init__(self) -> None:
        """Create empty task storage for this demonstration."""
        self._tasks: dict[str, dict[str, object]] = {}

    async def request(
        self, method: str, path: str, body: str = ""
    ) -> A2AResponse:
        """Serve discovery and the A2A JSON-RPC task methods."""
        if method == "GET" and path == CARD_PATH:
            return A2AResponse(200, json.dumps(_agent_card()))
        if method != "POST" or path != TASK_PATH:
            return A2AResponse(404, json.dumps({"error": "Not found."}))
        request = _object(json.loads(body))
        request_id = request.get("id")
        if request.get("jsonrpc") != "2.0":
            return _rpc_error(request_id, -32600, "Invalid request.")
        operation = request.get("method")
        params = _object(request.get("params"))
        if operation == "message/send":
            return self._submit(request_id, params)
        task_id = str(params.get("id"))
        if operation in {"tasks/get", "tasks/cancel"}:
            if task_id not in self._tasks:
                return _rpc_error(request_id, -32001, "Task not found.")
            if operation == "tasks/cancel":
                return _rpc_error(
                    request_id, -32002, "Completed tasks cannot be canceled."
                )
            return _rpc_result(request_id, self._tasks[task_id])
        return _rpc_error(request_id, -32601, "Method not found.")

    def _submit(
        self, request_id: object, params: dict[str, object]
    ) -> A2AResponse:
        """Record working state, then calculate the artifact."""
        message = _object(params.get("message"))
        parts = message.get("parts")
        if (
            message.get("role") != "user"
            or not isinstance(message.get("messageId"), str)
            or not isinstance(parts, list)
            or not parts
        ):
            return _rpc_error(request_id, -32602, "Invalid message.")
        part = _object(parts[0])
        if part.get("kind") != "text" or not isinstance(part.get("text"), str):
            return _rpc_error(request_id, -32602, "A text part is required.")
        # Continuations must not restart a completed task.
        if "taskId" in message:
            return _rpc_error(request_id, -32602, "Task is not continuable.")
        task_id = f"pilot-task-{len(self._tasks) + 1}"
        working: dict[str, object] = {
            "kind": "task",
            "id": task_id,
            "contextId": scenario.SCENARIO_ID,
            "status": {"state": "working"},
            "history": [message],
        }
        self._tasks[task_id] = working
        response = _rpc_result(request_id, working)
        cost = scenario.price_pilot()
        acceptable, failures = scenario.proposal_is_acceptable(
            cost=cost,
            approved=False,
            cited_sources=["agent-framework-overview"],
        )
        artifact: dict[str, object] = {
            "artifactId": f"{task_id}-costing",
            "name": "pilot-proposal-draft",
            "parts": [
                {
                    "kind": "data",
                    "data": {
                        "cost": dict(cost),
                        "acceptable": acceptable,
                        "acceptance_failures": failures,
                        "approved": False,
                    },
                }
            ],
        }
        self._tasks[task_id] = {
            **working,
            "status": {"state": "completed"},
            "artifacts": [artifact],
        }
        return response


def _agent_card() -> dict[str, object]:
    """Advertise only the endpoint capabilities implemented here."""
    return {
        "protocolVersion": "0.3.0",
        "name": "Support pilot costing agent",
        "description": "Draft a costed pilot; never accept work.",
        "url": "http://workshop.local/a2a",
        "preferredTransport": "JSONRPC",
        "version": "1.0.0",
        "capabilities": {"streaming": False, "pushNotifications": False},
        "defaultInputModes": ["text/plain"],
        "defaultOutputModes": ["application/json"],
        "skills": [
            {
                "id": "price-support-pilot",
                "name": "Cost the support pilot",
                "description": "Use the shared illustrative rate card.",
                "tags": ["costing", "support-pilot"],
            }
        ],
    }


def _object(value: object) -> dict[str, object]:
    """Validate objects as they leave the untyped JSON boundary."""
    if not isinstance(value, dict):
        message = "Expected a JSON object."
        raise TypeError(message)
    return cast("dict[str, object]", value)


def _rpc_result(request_id: object, value: dict[str, object]) -> A2AResponse:
    """Encode a JSON-RPC result for the corresponding request."""
    return A2AResponse(
        200,
        json.dumps({"jsonrpc": "2.0", "id": request_id, "result": value}),
    )


def _rpc_error(request_id: object, code: int, message: str) -> A2AResponse:
    """Encode an A2A or JSON-RPC error with its standard code."""
    return A2AResponse(
        200,
        json.dumps(
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {"code": code, "message": message},
            }
        ),
    )


async def _read(
    port: A2APort, method: str, path: str, body: str = ""
) -> dict[str, object]:
    """Check the transport status before interpreting a response."""
    response = await port.request(method, path, body)
    if response.status_code in {401, 403}:
        message = "The A2A endpoint denied access."
        raise PermissionError(message)
    if response.status_code != 200:
        message = "The A2A endpoint returned an unexpected status."
        raise ValueError(message)
    return _object(json.loads(response.body))


async def _rpc(
    port: A2APort,
    operation: str,
    params: dict[str, object],
    request_id: int,
) -> dict[str, object]:
    """Exchange one correlated A2A task request."""
    response = await _read(
        port,
        "POST",
        TASK_PATH,
        json.dumps(
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "method": operation,
                "params": params,
            }
        ),
    )
    if (
        response.get("jsonrpc") != "2.0"
        or response.get("id") != request_id
        or "error" in response
    ):
        message = "The A2A JSON-RPC response failed validation."
        raise ValueError(message)
    return _object(response.get("result"))


async def _exchange(port: A2APort) -> dict[str, object]:
    """Discover an agent, delegate drafting and fetch its artifact."""
    card = await _read(port, "GET", CARD_PATH)
    if card != _agent_card():
        message = "The local agent card does not match the allowed contract."
        raise ValueError(message)
    working = await _rpc(
        port,
        "message/send",
        {
            "message": {
                "kind": "message",
                "role": "user",
                "messageId": "pilot-request-1",
                "parts": [{"kind": "text", "text": scenario.BRIEF}],
            }
        },
        1,
    )
    if (
        working.get("kind") != "task"
        or not _identifier(working.get("id"))
        or working.get("contextId") != scenario.SCENARIO_ID
        or working.get("status") != {"state": "working"}
    ):
        message = "The endpoint did not acknowledge a working task."
        raise ValueError(message)
    completed = await _rpc(port, "tasks/get", {"id": working.get("id")}, 2)
    if (
        completed.get("id") != working.get("id")
        or completed.get("kind") != "task"
        or completed.get("contextId") != working.get("contextId")
        or completed.get("status") != {"state": "completed"}
    ):
        message = "The delegated drafting task did not complete."
        raise ValueError(message)
    artifacts = completed.get("artifacts")
    if not isinstance(artifacts, list) or len(artifacts) != 1:
        message = "The completed task must contain one costing artifact."
        raise ValueError(message)
    artifact = _object(artifacts[0])
    if not _identifier(artifact.get("artifactId")):
        message = "The costing artifact requires a nonempty artifactId."
        raise ValueError(message)
    parts = artifact.get("parts")
    if not isinstance(parts, list) or len(parts) != 1:
        message = "The costing artifact must contain one data part."
        raise ValueError(message)
    part = _object(parts[0])
    if part.get("kind") != "data":
        message = "The costing artifact requires a data part."
        raise ValueError(message)
    data = _object(part.get("data"))
    cost = scenario.price_pilot()
    acceptable, failures = scenario.proposal_is_acceptable(
        cost=cost, approved=False, cited_sources=["agent-framework-overview"]
    )
    if (
        data.get("cost") != cost
        or data.get("approved") is not False
        or data.get("acceptable") is not acceptable
        or data.get("acceptance_failures") != failures
    ):
        message = "The returned artifact violates the costing contract."
        raise ValueError(message)
    return {
        "scenario_id": scenario.SCENARIO_ID,
        "agent_card_path": CARD_PATH,
        "agent_card": card,
        "transport": "in-process routed JSON requests; no HTTP socket",
        "protocol_steps": ["GET agent card", "message/send", "tasks/get"],
        "task_states": ["working", "completed"],
        "task": completed,
        "artifact": artifact,
        "accept_proposal_executed": False,
        "comparison": {
            "mcp": "Call a named tool with arguments and receive its result.",
            "a2a": (
                "Delegate a task to an agent that owns its status, "
                "execution and artifacts."
            ),
        },
        "foundry_preview": (
            "FoundryChatClient.get_a2a_tool("
            "base_url='https://your-agent.example', "
            "agent_card_path='/.well-known/agent-card.json', "
            "project_connection_id='<configured connection>')"
        ),
        "agent_service_integration": (
            "Agent Framework can consume an A2A agent service with tasks "
            "and sessions. That integration and Foundry hosting are not "
            "invoked by this standalone local protocol endpoint."
        ),
        "sdk_note": (
            "No optional A2A SDK is required or invoked. This is a "
            "teaching subset of A2A 0.3.0, not a production server."
        ),
    }


def _identifier(value: object) -> bool:
    """Require an actual nonempty protocol identifier."""
    return isinstance(value, str) and bool(value.strip())


async def run_a2a_demo(
    *,
    execution: str = "offline",
    port: A2APort | None = None,
) -> DemoResult:
    """Run a complete local task delegation without credentials.

    Args:
        execution: ``offline`` executes the local endpoint. ``live``
            reports the missing hosted agent integration.
        port: Optional endpoint seam for deterministic tests.

    Returns:
        The exchanged task, status and costing artifact.

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
            provider="a2a",
            missing=["authenticated A2A agent service port"],
            next_steps=[
                "Publish an A2A endpoint and configure its authentication.",
                "Create the Foundry connection for the preview hosted tool.",
            ],
        )
    selected = port or LocalA2APort()
    try:
        payload = await _exchange(selected)
    except (PermissionError, TimeoutError, TypeError, ValueError) as exc:
        denied = isinstance(exc, PermissionError)
        return result(
            demo=DEMO_NAME,
            technology=TECHNOLOGY,
            lane="current",
            mode="local_execution",
            status="blocked" if denied else "error",
            headline="The local A2A exchange did not complete.",
            evidence=evidence(provider="in-process A2A"),
            error={
                "code": "authorization_denied" if denied else "protocol_error",
                "message": "Check endpoint access and the task response.",
            },
        )
    return result(
        demo=DEMO_NAME,
        technology=TECHNOLOGY,
        lane="current",
        mode="local_execution",
        status="ok",
        headline="A local A2A agent completed a costed proposal draft.",
        evidence=evidence(provider="in-process A2A"),
        data=payload,
    )

from __future__ import annotations

import asyncio
import json
from typing import cast

import pytest

from msai_demo import scenario
from msai_demo.a2a_demo import (
    CARD_PATH,
    TASK_PATH,
    A2AResponse,
    LocalA2APort,
    run_a2a_demo,
)


class RewritePort:
    def __init__(self, phase: str, body: str, status_code: int = 200) -> None:
        self.local = LocalA2APort()
        self.phase = phase
        self.body = body
        self.status_code = status_code

    async def request(
        self, method: str, path: str, body: str = ""
    ) -> A2AResponse:
        response = await self.local.request(method, path, body)
        phase = "card" if method == "GET" else json.loads(body)["method"]
        if phase == self.phase:
            return A2AResponse(self.status_code, self.body)
        return response


class FailedPort:
    def __init__(self, error: Exception) -> None:
        self.error = error

    async def request(
        self, method: str, path: str, body: str = ""
    ) -> A2AResponse:
        del method, path, body
        raise self.error


def result_body(value: object, request_id: int = 2) -> str:
    return json.dumps({"jsonrpc": "2.0", "id": request_id, "result": value})


def completed_task(**updates: object) -> dict[str, object]:
    task: dict[str, object] = {
        "kind": "task",
        "id": "pilot-task-1",
        "contextId": scenario.SCENARIO_ID,
        "status": {"state": "completed"},
        "artifacts": [
            {
                "artifactId": "pilot-task-1-costing",
                "parts": [
                    {
                        "kind": "data",
                        "data": {
                            "cost": scenario.price_pilot(),
                            "approved": False,
                            "acceptable": False,
                            "acceptance_failures": [
                                "No human approval recorded."
                            ],
                        },
                    }
                ],
            }
        ],
    }
    task.update(updates)
    return task


def test_local_task_status_and_artifact_without_optional_sdk() -> None:
    result = asyncio.run(run_a2a_demo())
    assert result["mode"] == "local_execution"
    assert result["status"] == "ok"
    assert result["evidence"]["sdk_invoked"] is False
    assert result["evidence"]["network_attempted"] is False
    data = result["data"]
    assert data is not None
    assert data["agent_card_path"] == CARD_PATH
    assert data["agent_card"]["protocolVersion"] == "0.3.0"
    assert data["task_states"] == ["working", "completed"]
    draft = data["artifact"]["parts"][0]["data"]
    assert draft["cost"] == scenario.price_pilot()
    assert draft["approved"] is False
    assert draft["acceptable"] is False
    assert draft["acceptance_failures"] == ["No human approval recorded."]
    assert data["accept_proposal_executed"] is False
    assert "get_a2a_tool" in data["foundry_preview"]


def test_live_never_contacts_the_injected_endpoint() -> None:
    result = asyncio.run(
        run_a2a_demo(execution="live", port=FailedPort(AssertionError()))
    )
    assert result["mode"] == "not_run"
    assert result["error"] is not None
    assert result["error"]["code"] == "missing_configuration"


def test_invalid_execution_is_rejected() -> None:
    with pytest.raises(ValueError, match="execution must"):
        asyncio.run(run_a2a_demo(execution="typo"))


@pytest.mark.parametrize("status", [401, 403])
def test_authentication_and_authorization_boundaries(status: int) -> None:
    result = asyncio.run(run_a2a_demo(port=RewritePort("card", "{}", status)))
    assert result["status"] == "blocked"
    assert result["error"] is not None
    assert result["error"]["code"] == "authorization_denied"
    assert result["evidence"]["network_attempted"] is False


@pytest.mark.parametrize("error", [TimeoutError(), ValueError(), TypeError()])
def test_known_failures_are_reported(error: Exception) -> None:
    result = asyncio.run(run_a2a_demo(port=FailedPort(error)))
    assert result["status"] == "error"


def test_programming_errors_propagate() -> None:
    with pytest.raises(RuntimeError):
        asyncio.run(run_a2a_demo(port=FailedPort(RuntimeError())))


@pytest.mark.parametrize(
    ("phase", "body", "status_code"),
    [
        ("card", "{}", 404),
        ("card", "not JSON", 200),
        ("card", "[]", 200),
        ("card", "{}", 200),
        ("message/send", '{"jsonrpc":"1.0","id":1}', 200),
        ("message/send", '{"jsonrpc":"2.0","id":4}', 200),
        ("message/send", '{"jsonrpc":"2.0","id":1,"error":{}}', 200),
        ("message/send", '{"jsonrpc":"2.0","id":1}', 200),
        ("message/send", result_body({}, 1), 200),
        ("tasks/get", result_body(completed_task(id="wrong")), 200),
        ("tasks/get", result_body(completed_task(status={})), 200),
        ("tasks/get", result_body(completed_task(artifacts=None)), 200),
        ("tasks/get", result_body(completed_task(artifacts=[])), 200),
        ("tasks/get", result_body(completed_task(artifacts=[{}])), 200),
        (
            "tasks/get",
            result_body(completed_task(artifacts=[{"parts": []}])),
            200,
        ),
        (
            "tasks/get",
            result_body(completed_task(artifacts=[{"parts": [{}]}])),
            200,
        ),
        (
            "tasks/get",
            result_body(completed_task(artifacts=[{"parts": [{"data": {}}]}])),
            200,
        ),
        (
            "tasks/get",
            result_body(
                completed_task(
                    artifacts=[
                        {
                            "parts": [
                                {
                                    "data": {
                                        "cost": scenario.price_pilot(),
                                        "approved": True,
                                    }
                                }
                            ]
                        }
                    ]
                )
            ),
            200,
        ),
    ],
)
def test_untrusted_endpoint_responses(
    phase: str, body: str, status_code: int
) -> None:
    result = asyncio.run(
        run_a2a_demo(port=RewritePort(phase, body, status_code))
    )
    assert result["status"] == "error"
    assert result["error"] is not None
    assert result["error"]["code"] == "protocol_error"


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("kind", None),
        ("id", None),
        ("id", ""),
        ("contextId", None),
        ("status", None),
    ],
)
def test_working_task_requires_protocol_fields(
    key: str, value: object
) -> None:
    working: dict[str, object] = {
        "kind": "task",
        "id": "pilot-task-1",
        "contextId": scenario.SCENARIO_ID,
        "status": {"state": "working"},
    }
    working[key] = value
    result = asyncio.run(
        run_a2a_demo(port=RewritePort("message/send", result_body(working, 1)))
    )
    assert result["status"] == "error"


@pytest.mark.parametrize(
    ("section", "key", "value"),
    [
        ("task", "kind", None),
        ("task", "contextId", None),
        ("artifact", "artifactId", None),
        ("artifact", "artifactId", " "),
        ("artifact", "parts", None),
        ("artifact", "parts", []),
        ("part", "kind", None),
        ("part", "data", None),
        ("data", "cost", None),
        ("data", "approved", True),
        ("data", "approved", None),
        ("data", "acceptable", True),
        ("data", "acceptance_failures", []),
    ],
)
def test_completed_artifact_requires_schema_and_acceptance_invariants(
    section: str, key: str, value: object
) -> None:
    task = completed_task()
    artifact = cast("list[dict[str, object]]", task["artifacts"])[0]
    part = cast("list[dict[str, object]]", artifact["parts"])[0]
    data = cast("dict[str, object]", part["data"])
    sections = {"task": task, "artifact": artifact, "part": part, "data": data}
    sections[section][key] = value
    result = asyncio.run(
        run_a2a_demo(port=RewritePort("tasks/get", result_body(task)))
    )
    assert result["status"] == "error"


async def request(
    port: LocalA2APort,
    operation: str,
    params: object,
    version: str = "2.0",
) -> dict[str, object]:
    response = await port.request(
        "POST",
        TASK_PATH,
        json.dumps(
            {
                "jsonrpc": version,
                "id": 1,
                "method": operation,
                "params": params,
            }
        ),
    )
    return cast("dict[str, object]", json.loads(response.body))


def test_endpoint_routes_and_task_lifecycle_errors() -> None:
    async def check() -> None:
        port = LocalA2APort()
        assert (await port.request("GET", "/missing")).status_code == 404
        assert (await port.request("POST", "/missing")).status_code == 404
        assert "error" in await request(port, "unknown", {}, version="1.0")
        assert "error" in await request(port, "unknown", {})
        assert "error" in await request(port, "tasks/get", {"id": "missing"})
        await request(
            port,
            "message/send",
            {
                "message": {
                    "role": "user",
                    "messageId": "request-1",
                    "parts": [{"kind": "text", "text": scenario.BRIEF}],
                }
            },
        )
        response = await request(port, "tasks/cancel", {"id": "pilot-task-1"})
        assert response["error"] == {
            "code": -32002,
            "message": "Completed tasks cannot be canceled.",
        }

    asyncio.run(check())


@pytest.mark.parametrize(
    "updates",
    [
        {"role": "assistant"},
        {"messageId": None},
        {"parts": None},
        {"parts": []},
        {"parts": [{"kind": "data"}]},
        {"parts": [{"kind": "text", "text": None}]},
        {"taskId": "pilot-task-1"},
    ],
)
def test_endpoint_validates_user_messages(updates: dict[str, object]) -> None:
    async def check() -> None:
        message: dict[str, object] = {
            "role": "user",
            "messageId": "request-1",
            "parts": [{"kind": "text", "text": scenario.BRIEF}],
        }
        message.update(updates)
        response = await request(
            LocalA2APort(), "message/send", {"message": message}
        )
        assert "error" in response

    asyncio.run(check())

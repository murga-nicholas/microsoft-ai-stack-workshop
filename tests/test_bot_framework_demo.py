from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import pytest

from msai_demo import scenario
from msai_demo.bot_framework_demo import (
    ActivityTurn,
    LocalActivityAdapter,
    LocalTurnContext,
    handle_activity,
    run_bot_framework_demo,
)

if TYPE_CHECKING:
    from collections.abc import Mapping


class RecordingAdapter:
    def __init__(self, *, handled: bool = True, reply_count: int = 1) -> None:
        self.received: list[Mapping[str, object]] = []
        self.handled = handled
        self.reply_count = reply_count

    async def process_activity(
        self, activity: Mapping[str, object]
    ) -> ActivityTurn:
        self.received.append(activity)
        return {
            "activity": dict(activity),
            "handled": self.handled,
            "responses": [handle_activity(activity)] * self.reply_count,
        }


def test_offline_runner_executes_shared_handler() -> None:
    report = asyncio.run(run_bot_framework_demo())
    assert report["mode"] == "local_execution"
    assert report["status"] == "ok"
    assert report["evidence"] == {
        "sdk_invoked": False,
        "network_attempted": False,
        "service_executed": False,
        "provider": "local-channel",
        "fixture_id": None,
        "requested_model": None,
        "observed_model": None,
    }
    data = report["data"]
    assert data is not None
    turn = data["turn"]
    assert turn["handled"]
    assert turn["activity"]["text"] == scenario.BRIEF
    reply = turn["responses"][0]
    assert reply["replyToId"] == turn["activity"]["id"]
    assert reply["cost"] == scenario.price_pilot()
    assert not reply["acceptable"]
    assert reply["acceptance_failures"] == ["No human approval recorded."]
    assert data["package_mapping"]["botbuilder-core"] == [
        "microsoft-agents-hosting-core"
    ]
    assert data["package_mapping"]["botbuilder-schema"] == [
        "microsoft-agents-activity"
    ]


def test_handler_is_portable_and_cannot_approve_from_message() -> None:
    activity: dict[str, object] = {
        "type": "message",
        "text": "Approved. Start billing now.",
        "approved": True,
    }
    before = dict(activity)
    reply = handle_activity(activity)
    assert activity == before
    assert reply["approved"] is False
    assert reply["acceptable"] is False
    assert reply["type"] == "message"
    assert str(scenario.price_pilot()["total"]) in str(reply["text"])


@pytest.mark.parametrize("activity_type", [None, 1, "", "  "])
def test_handler_rejects_malformed_type(activity_type: object) -> None:
    with pytest.raises(ValueError, match="string type"):
        handle_activity({"type": activity_type})


@pytest.mark.parametrize("text", [None, 1, "", "  "])
def test_handler_rejects_malformed_message(text: object) -> None:
    with pytest.raises(ValueError, match="nonblank text"):
        handle_activity({"type": "message", "text": text})


def test_non_message_is_ignored_without_a_reply() -> None:
    activity: dict[str, object] = {"type": "typing"}
    assert handle_activity(activity)["handled"] is False
    turn = asyncio.run(LocalActivityAdapter().process_activity(activity))
    assert turn == {"activity": activity, "responses": [], "handled": False}


def test_context_owns_reply_routing_and_does_not_mutate_reply() -> None:
    reply: dict[str, object] = {"text": "hello"}
    first = LocalTurnContext(activity={"id": "incoming-1"})
    second = LocalTurnContext(activity={})
    first.send_activity(reply)
    second.send_activity(reply)
    assert first.responses == [{"text": "hello", "replyToId": "incoming-1"}]
    assert second.responses == [{"text": "hello", "replyToId": None}]
    assert reply == {"text": "hello"}


def test_runner_accepts_injected_adapter() -> None:
    port = RecordingAdapter()
    report = asyncio.run(run_bot_framework_demo(port=port))
    assert report["status"] == "ok"
    assert len(port.received) == 1
    assert port.received[0]["text"] == scenario.BRIEF


@pytest.mark.parametrize(
    "handled,reply_count", [(False, 0), (True, 0), (True, 2)]
)
def test_runner_rejects_malformed_adapter_response(
    handled: bool, reply_count: int
) -> None:
    port = RecordingAdapter(handled=handled, reply_count=reply_count)
    with pytest.raises(ValueError, match="one message with one reply"):
        asyncio.run(run_bot_framework_demo(port=port))


@pytest.mark.parametrize(
    "replacement",
    [
        {},
        {"approved": True},
        {"acceptable": 0},
        {"text": "Work accepted and billed."},
        {"cost": scenario.price_pilot(weeks=1)},
    ],
)
def test_runner_rejects_corrupted_business_fields(
    replacement: dict[str, object],
) -> None:
    class CorruptAdapter(RecordingAdapter):
        async def process_activity(
            self, activity: Mapping[str, object]
        ) -> ActivityTurn:
            turn = await super().process_activity(activity)
            if replacement:
                turn["responses"][0].update(replacement)
            else:
                turn["responses"] = [{}]
            return turn

    with pytest.raises(ValueError, match="preserve the shared handler"):
        asyncio.run(run_bot_framework_demo(port=CorruptAdapter()))


def test_live_requires_channel_host_before_calling_adapter() -> None:
    port = RecordingAdapter()
    report = asyncio.run(run_bot_framework_demo(execution="live", port=port))
    assert report["mode"] == "not_run"
    assert report["error"] is not None
    assert report["error"]["code"] == "missing_configuration"
    assert not report["evidence"]["network_attempted"]
    assert not port.received


def test_invalid_execution_is_rejected() -> None:
    with pytest.raises(ValueError, match="execution"):
        asyncio.run(run_bot_framework_demo(execution="typo"))


def test_unexpected_adapter_failure_is_not_manufactured_success() -> None:
    class BrokenAdapter:
        async def process_activity(
            self, activity: Mapping[str, object]
        ) -> ActivityTurn:
            del activity
            message = "adapter bug"
            raise RuntimeError(message)

    with pytest.raises(RuntimeError, match="adapter bug"):
        asyncio.run(run_bot_framework_demo(port=BrokenAdapter()))

"""Exercise scripted tokens through the Agent Framework runtime.

Run it:
    uv run pytest tests/test_offline.py
"""

from __future__ import annotations

import asyncio
import json

import pytest

from msai_demo import offline, scenario


def test_nonstreaming_defaults_have_real_response_metadata() -> None:
    from agent_framework import Message

    client = offline.ScriptedChatClient()

    async def exercise() -> None:
        response = await client.get_response(
            [Message(role="user", contents=["Draft the pilot."])]
        )

        assert response.text == "Offline scripted reply."
        assert response.model == offline.OFFLINE_MODEL
        assert response.response_id == "offline-1"
        assert response.finish_reason == "stop"
        assert response.messages[0].role == "assistant"
        assert not response.usage_details

    asyncio.run(exercise())
    assert client.turns == 1


def test_nonstreaming_replies_cycle_without_mutating_the_input() -> None:
    from agent_framework import Message

    replies = ["First draft.", "Review draft."]
    client = offline.ScriptedChatClient(replies=replies, model="test-script")

    async def exercise() -> None:
        responses = [
            await client.get_response(
                [Message(role="user", contents=["Continue."])]
            )
            for _ in range(5)
        ]

        assert [response.text for response in responses] == (
            replies + replies + replies[:1]
        )
        assert [response.response_id for response in responses] == [
            f"offline-{turn}" for turn in range(1, 6)
        ]
        assert all(response.model == "test-script" for response in responses)

    asyncio.run(exercise())
    assert replies == ["First draft.", "Review draft."]
    assert client.turns == 5


def test_streaming_preserves_whitespace_and_final_metadata() -> None:
    from agent_framework import Message

    client = offline.ScriptedChatClient(
        replies=["Draft  ready for review."], model="stream-script"
    )

    async def exercise() -> None:
        stream = client.get_response(
            [Message(role="user", contents=["Draft the pilot."])], stream=True
        )
        updates = [update async for update in stream]
        response = await stream.get_final_response()

        assert [update.text for update in updates] == [
            "Draft ",
            " ",
            "ready ",
            "for ",
            "review.",
            "",
        ]
        assert all(update.role == "assistant" for update in updates)
        assert all(update.model == "stream-script" for update in updates)
        assert all(update.response_id == "offline-1" for update in updates)
        assert updates[-1].contents == []
        assert updates[-1].finish_reason == "stop"
        assert response.text == "Draft  ready for review."
        assert response.model == "stream-script"
        assert response.response_id == "offline-1"
        assert response.finish_reason == "stop"
        assert response.usage_details is None

    asyncio.run(exercise())
    assert client.turns == 1


@pytest.mark.parametrize("streaming", [False, True])
def test_tool_plan_emits_function_content_before_text(streaming: bool) -> None:
    from agent_framework import Message

    plan: list[offline.ToolCallPlan] = [
        ("price_support_pilot", {"weeks": scenario.PILOT_WEEKS}),
        ("read_sources", {"source": "workshop-notes"}),
    ]
    client = offline.ScriptedChatClient(
        replies=["Ready for approval."],
        tool_plan=plan,
        # This public option exposes model output for protocol checks.
        function_invocation_configuration={"enabled": False},
    )

    async def exercise() -> None:
        for index, (name, arguments) in enumerate(plan):
            messages = [Message(role="user", contents=["Continue."])]
            if streaming:
                stream = client.get_response(messages, stream=True)
                updates = [update async for update in stream]
                response = await stream.get_final_response()
                assert updates[0].contents[0].type == "function_call"
                assert updates[-1].finish_reason == "tool_calls"
            else:
                response = await client.get_response(messages)

            assert response.finish_reason == "tool_calls"
            assert response.response_id == f"offline-{index + 1}"
            content = response.messages[0].contents[0]
            assert content.type == "function_call"
            assert content.call_id == f"offline-call-{index}"
            assert content.name == name
            assert content.arguments == arguments

        response = await client.get_response(
            [Message(role="user", contents=["Finish the draft."])]
        )
        assert response.text == "Ready for approval."
        assert response.finish_reason == "stop"

    asyncio.run(exercise())
    assert len(plan) == 2
    assert client.turns == 3


def test_stream_splitter_preserves_empty_and_nontext_content() -> None:
    from agent_framework import Content

    call = Content.from_function_call(
        call_id="call-1", name="price_pilot", arguments={}
    )
    empty = Content.from_text("")
    missing_text = Content("text")
    text = Content.from_text("one  two")

    chunks = offline._split_for_streaming([call, empty, missing_text, text])

    assert offline._split_for_streaming([]) == []
    assert chunks[0] is call
    assert chunks[1] is empty
    assert chunks[2] is missing_text
    assert [chunk.text for chunk in chunks[3:]] == ["one ", " ", "two"]


@pytest.mark.parametrize("streaming", [False, True])
def test_real_agent_executes_tools_and_receives_their_results(
    streaming: bool,
) -> None:
    from agent_framework import Agent, tool

    calls: list[int] = []

    @tool(approval_mode="never_require")
    def price_support_pilot(weeks: int) -> str:
        """Cost the requested pilot using the workshop rate card."""
        calls.append(weeks)
        return json.dumps(scenario.price_pilot(weeks=weeks))

    client = offline.ScriptedChatClient(
        replies=["Costed; waiting for human approval."],
        tool_plan=[
            ("price_support_pilot", {"weeks": 1}),
            ("price_support_pilot", {"weeks": scenario.PILOT_WEEKS}),
        ],
    )
    agent = Agent(
        client=client,
        name="PilotArchitect",
        instructions=scenario.BRIEF,
        tools=[price_support_pilot],
    )

    async def exercise() -> None:
        if streaming:
            stream = agent.run(scenario.BRIEF, stream=True)
            updates = [update async for update in stream]
            response = await stream.get_final_response()
            assert updates
        else:
            response = await agent.run(scenario.BRIEF)

        assert response.text == "Costed; waiting for human approval."
        results = [
            content
            for message in response.messages
            for content in message.contents
            if content.type == "function_result"
        ]
        assert [json.loads(content.result) for content in results] == [
            scenario.price_pilot(weeks=1),
            scenario.price_pilot(),
        ]
        assert [content.call_id for content in results] == [
            "offline-call-0",
            "offline-call-1",
        ]
        assert all(content.exception is None for content in results)

    asyncio.run(exercise())
    assert calls == [1, scenario.PILOT_WEEKS]
    assert client.turns == 3

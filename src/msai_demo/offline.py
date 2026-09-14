"""A scripted chat client so every demo runs without credentials.

This is **not** a stub and it does not fake results. It is a real Agent
Framework chat client: it plugs into the same
``FunctionInvocationLayer``/``ChatMiddlewareLayer``/``BaseChatClient``
stack that ``OpenAIChatClient`` uses, so the framework genuinely runs
its tool-calling loop, its middleware and its orchestrations against
it. Only the token generation is replaced by a fixed script.

That distinction is the whole point. When a demo prints
``"mode": "offline_scripted"`` the orchestration you are watching is
the real one; when it prints ``"mode": "live"`` the tokens came from a
model too.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from agent_framework import (
    BaseChatClient,
    ChatMiddlewareLayer,
    ChatResponse,
    ChatResponseUpdate,
    Content,
    FinishReasonLiteral,
    Message,
    ResponseStream,
)
from agent_framework._tools import FunctionInvocationLayer

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Awaitable, Mapping, Sequence

OFFLINE_MODEL: str = "scripted-offline-1"

ToolCallPlan = tuple[str, dict[str, Any]]


class ScriptedChatClient(
    FunctionInvocationLayer[Any],
    ChatMiddlewareLayer,
    BaseChatClient,
):
    """Replay a fixed script through the real Agent Framework stack.

    Args:
        replies: Text replies, used in order and then repeated.
        tool_plan: Tool calls to emit before the first text reply, as
            ``(tool_name, arguments)`` pairs. The framework executes
            them for real and feeds the results back.
        model: Name reported as the model, for traces and payloads.
    """

    def __init__(
        self,
        *,
        replies: Sequence[str] = (),
        tool_plan: Sequence[ToolCallPlan] = (),
        model: str = OFFLINE_MODEL,
        **kwargs: Any,
    ) -> None:
        """Build a client that replays ``replies`` and ``tool_plan``."""
        super().__init__(**kwargs)
        self.model = model
        self._replies: list[str] = list(replies) or ["Offline scripted reply."]
        self._pending_tools: list[ToolCallPlan] = list(tool_plan)
        self.turns: int = 0
        self._text_turns: int = 0

    def _next_contents(
        self,
    ) -> tuple[list[Content], FinishReasonLiteral]:
        """Return the contents for this turn and a finish reason."""
        if self._pending_tools:
            name, arguments = self._pending_tools.pop(0)
            call = Content.from_function_call(
                call_id=f"offline-call-{self.turns}",
                name=name,
                arguments=arguments,
            )
            return [call], "tool_calls"

        reply = self._replies[self._text_turns % len(self._replies)]
        self._text_turns += 1
        return [Content.from_text(reply)], "stop"

    def _inner_get_response(
        self,
        *,
        messages: Sequence[Message],
        stream: bool,
        options: Mapping[str, Any],
        **kwargs: Any,
    ) -> (
        Awaitable[ChatResponse[Any]]
        | ResponseStream[ChatResponseUpdate, ChatResponse[Any]]
    ):
        """Produce the next scripted response.

        Args:
            messages: Conversation so far. Recorded, never inspected,
                so the script stays deterministic.
            stream: Whether the caller asked for streaming.
            options: Chat options from the caller.
            **kwargs: Client-specific extras, ignored here.

        Returns:
            An awaitable response, or a response stream.
        """
        del messages, options, kwargs
        contents, finish_reason = self._next_contents()
        self.turns += 1
        response_id = f"offline-{self.turns}"

        if not stream:
            return self._single(contents, finish_reason, response_id)

        async def _updates() -> AsyncIterator[ChatResponseUpdate]:
            for chunk in _split_for_streaming(contents):
                yield ChatResponseUpdate(
                    contents=[chunk],
                    role="assistant",
                    model=self.model,
                    response_id=response_id,
                )
            yield ChatResponseUpdate(
                contents=[],
                role="assistant",
                model=self.model,
                response_id=response_id,
                finish_reason=finish_reason,
            )

        return ResponseStream(
            _updates(),
            finalizer=ChatResponse.from_updates,
        )

    async def _single(
        self,
        contents: list[Content],
        finish_reason: FinishReasonLiteral,
        response_id: str,
    ) -> ChatResponse[Any]:
        """Wrap one scripted turn as a complete chat response."""
        return ChatResponse(
            messages=Message(role="assistant", contents=contents),
            model=self.model,
            response_id=response_id,
            finish_reason=finish_reason,
        )


def _split_for_streaming(contents: list[Content]) -> list[Content]:
    """Split text content into word chunks so streaming looks real."""
    chunks: list[Content] = []
    for content in contents:
        if content.type != "text" or not content.text:
            chunks.append(content)
            continue
        words = content.text.split(" ")
        for position, word in enumerate(words):
            suffix = "" if position == len(words) - 1 else " "
            chunks.append(Content.from_text(word + suffix))
    return chunks

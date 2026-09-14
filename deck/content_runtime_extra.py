"""Provider families, protocols and the exact installed class MRO."""

from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING

import components as C
import diagrams as D
import research_facts as R
import theme as T
from theme import P, plain, text_box, write

if TYPE_CHECKING:
    from facts import Facts
    from pptx.presentation import Presentation
    from pptx.slide import Slide

USE_Y = 7132320


def _text(
    slide: Slide,
    text: str,
    *,
    x: int,
    y: int,
    w: int,
    h: int = 365760,
    size: float = 14,
    colour: str = P.muted,
    bold: bool = False,
) -> None:
    box = text_box(slide, x=x, y=y, w=w, h=h)
    write(box, plain(text), size=size, colour=colour, bold=bold)


def slide_client_family(prs: Presentation, facts: Facts) -> None:
    """Three distinct families with shared public-class layers."""
    del facts
    slide = T.content_slide(
        prs,
        eyebrow="class families",
        title="Every provider plugs into the same client family",
        deck="Provider clients share the chat contract. Agents and teams "
        "belong to separate class families.",
        number=16,
        accent=P.teal,
    )
    C.run_strip(slide, "agent-framework")
    # Raw class inheritance, followed by explicit public-class
    # composition badges.
    D.draw(
        slide,
        D.Schema(
            nodes=[
                D.Node(
                    "base",
                    "BaseChatClient",
                    col=9,
                    row=0,
                    width=15,
                    height=2.5,
                    colour=P.blue,
                ),
                D.Node(
                    "openai",
                    "RawOpenAIChatClient",
                    col=0,
                    row=3.5,
                    width=16,
                    height=2.5,
                    colour=P.blue,
                ),
                D.Node(
                    "anthropic",
                    "RawAnthropicClient",
                    col=18,
                    row=3.5,
                    width=16,
                    height=2.5,
                    colour=P.violet,
                ),
                D.Node(
                    "foundry",
                    "RawFoundryChatClient",
                    col=0,
                    row=7,
                    width=16,
                    height=2.5,
                    colour=P.teal,
                ),
            ],
            edges=[
                D.Edge("base", "openai"),
                D.Edge("base", "anthropic"),
                D.Edge("openai", "foundry", side="v"),
            ],
        ),
        x=T.MARGIN_L,
        y=T.Y_BODY,
    )
    badge_w = 2468880
    for index, (name, raw, accent) in enumerate(
        (
            ("OpenAIChatClient", "RawOpenAIChatClient", P.blue),
            ("FoundryChatClient", "RawFoundryChatClient", P.teal),
            ("AnthropicClient", "RawAnthropicClient", P.violet),
        )
    ):
        left = T.MARGIN_L + index * (badge_w + 137160)
        C.card(slide, x=left, y=5029200, w=badge_w, h=1691640)
        _text(
            slide,
            name,
            x=left + 91440,
            y=5120640,
            w=badge_w - 182880,
            size=15,
            colour=accent,
            bold=True,
        )
        _text(
            slide,
            raw,
            x=left + 91440,
            y=5504688,
            w=badge_w - 182880,
            h=365760,
            size=15,
            colour=P.ink_soft,
        )
        for row, layer in enumerate(
            ("+ function invocation", "+ chat middleware", "+ chat telemetry")
        ):
            T.rounded(
                slide,
                x=left + 91440,
                y=5870448 + row * 246888,
                w=badge_w - 182880,
                h=237744,
                fill=P.wash,
                line=P.rule,
                radius=0,
            )
            _text(
                slide,
                layer,
                x=left + 137160,
                y=5870448 + row * 246888,
                w=badge_w - 274320,
                h=237744,
                size=15,
            )
    # Agent subclasses and their public layers are a second independent
    # family.
    ax = 9677400
    D.draw(
        slide,
        D.Schema(
            nodes=[
                D.Node(
                    "base",
                    "BaseAgent",
                    col=4,
                    row=0,
                    width=11,
                    height=2.5,
                    colour=P.blue,
                ),
                D.Node(
                    "raw",
                    "RawAgent",
                    col=4,
                    row=3.5,
                    width=11,
                    height=2.5,
                    colour=P.blue,
                ),
                D.Node(
                    "agent",
                    "Agent",
                    col=0,
                    row=7,
                    width=7,
                    height=2.5,
                    colour=P.teal,
                ),
                D.Node(
                    "foundryraw",
                    "RawFoundryAgent",
                    col=9,
                    row=7,
                    width=12,
                    height=2.5,
                    colour=P.teal,
                ),
                D.Node(
                    "foundry",
                    "FoundryAgent",
                    col=9,
                    row=10.5,
                    width=12,
                    height=2.5,
                    colour=P.teal,
                ),
            ],
            edges=[
                D.Edge("base", "raw", side="v"),
                D.Edge("raw", "agent"),
                D.Edge("raw", "foundryraw"),
                D.Edge("foundryraw", "foundry", side="v"),
            ],
        ),
        x=ax,
        y=T.Y_BODY,
    )
    _text(
        slide,
        "Agent and FoundryAgent add:\nagent middleware + agent telemetry",
        x=ax,
        y=5791200,
        w=4800600,
        h=640080,
        size=14,
    )
    # Legacy comparison remains faint so it does not imply a cross-
    # library parent.
    bx = 14828520
    _text(
        slide,
        "AUTOGEN",
        x=bx,
        y=T.Y_BODY - 182880,
        w=1965960,
        colour=P.faint,
        bold=True,
    )
    for top, names in (
        (T.Y_BODY + 137160, ("ChatAgent", "BaseChatAgent", "AssistantAgent")),
        (
            T.Y_BODY + 1828800,
            ("Team", "BaseGroupChat", "RoundRobin\nGroupChat"),
        ),
    ):
        D.draw(
            slide,
            D.Schema(
                nodes=[
                    D.Node(
                        str(i),
                        name,
                        col=0,
                        row=i * 2.8,
                        width=8.5,
                        height=2.5,
                        kind="note",
                        colour=P.faint,
                    )
                    for i, name in enumerate(names)
                ],
                edges=[D.Edge("0", "1", side="v"), D.Edge("1", "2", side="v")],
            ),
            x=bx,
            y=top,
        )
    _text(
        slide,
        "Simplified: public classes use multiple inheritance. Exact method "
        "resolution order is in the appendix.",
        x=T.MARGIN_L,
        y=6797040,
        w=T.CONTENT_W,
        h=320040,
    )
    C.use_case(
        slide,
        who="Python developer needs another provider",
        steps=(
            "Pick a compatible client",
            "Configure endpoint and credentials",
            "Rerun agent and tests",
        ),
        result="Agent code unchanged; provider behaviour verified.",
        x=T.MARGIN_L,
        y=USE_Y,
        w=T.CONTENT_W,
        accent=P.teal,
    )


def slide_mcp(prs: Presentation, facts: Facts) -> None:
    """MCP tool discovery and the supplied tools catalog capture."""
    del facts
    slide = T.content_slide(
        prs,
        eyebrow="MCP tools",
        title="MCP gives an agent tools it did not have to write",
        deck="MCP is a protocol for discovering and calling tools supplied "
        "by a server.",
        number=19,
        accent=P.violet,
    )
    C.run_strip(slide, "mcp")
    D.draw(
        slide,
        D.Schema(
            nodes=[
                D.Node(
                    "agent",
                    "your agent",
                    col=0,
                    row=0,
                    width=12,
                    height=2.7,
                    colour=P.teal,
                ),
                D.Node(
                    "client",
                    "MCP client",
                    col=18,
                    row=0,
                    width=12,
                    height=2.7,
                    colour=P.violet,
                ),
                D.Node(
                    "server",
                    "MCP server",
                    col=18,
                    row=7,
                    width=12,
                    height=2.7,
                    colour=P.blue,
                ),
                D.Node(
                    "result",
                    "tool result",
                    col=0,
                    row=7,
                    width=12,
                    height=2.7,
                    kind="note",
                    colour=P.faint,
                ),
            ],
            edges=[
                D.Edge("agent", "client", side="h"),
                D.Edge(
                    "client", "server", "tools/list + tools/call", side="v"
                ),
                D.Edge("server", "result", side="h"),
            ],
        ),
        x=T.MARGIN_L,
        y=T.Y_BODY + 228600,
    )
    _text(
        slide,
        "The tool server exposes capabilities. Your application controls "
        "which tools the agent can use.",
        x=T.MARGIN_L,
        y=5532120,
        w=6858000,
        h=914400,
        size=16,
    )
    C.screenshot(
        slide,
        str(T.ASSETS / "foundry_tools_catalog.jpg"),
        x=9250680,
        y=T.Y_BODY,
        w=7543800,
        h=3261360,
        caption=f"Foundry tools catalog - {R.FOUNDRY_TOOLS_CAPTURE_COUNT:,} "
        f"tools visible in this capture, "
        f"{R.CAPTURE_DATE}; most are MCP servers",
    )
    C.use_case(
        slide,
        who="Developer needs test ideas for a GitHub issue",
        steps=(
            "Connect GitHub MCP server",
            "Discover tools",
            "Fetch issue",
            "Draft test cases",
        ),
        result="Reviewable test cases.",
        x=T.MARGIN_L,
        y=USE_Y,
        w=T.CONTENT_W,
        accent=P.violet,
    )


def slide_a2a(prs: Presentation, facts: Facts) -> None:
    """A2A task discovery, delegation and lifecycle."""
    del facts
    slide = T.content_slide(
        prs,
        eyebrow="A2A delegation",
        title="A2A hands a task to someone else's agent",
        deck="A2A lets independent agents exchange a task, follow its state "
        "and return an artifact.",
        number=20,
        accent=P.violet,
    )
    C.run_strip(slide, "a2a")
    diagram_y = T.Y_BODY + 182880
    D.draw(
        slide,
        D.Schema(
            nodes=[
                D.Node(
                    "agent",
                    "your agent",
                    col=0,
                    row=0,
                    width=9,
                    height=2.7,
                    colour=P.teal,
                ),
                D.Node(
                    "client",
                    "A2A client",
                    col=12,
                    row=0,
                    width=9,
                    height=2.7,
                    colour=P.violet,
                ),
                D.Node(
                    "remote",
                    "remote agent",
                    col=34,
                    row=0,
                    width=10,
                    height=2.7,
                    colour=P.blue,
                ),
                D.Node(
                    "artifact",
                    "task + artifact",
                    col=54,
                    row=0,
                    width=12,
                    height=2.7,
                    kind="state",
                    colour=P.blue,
                ),
            ],
            edges=[
                D.Edge("agent", "client", side="h"),
                D.Edge(
                    "remote", "artifact", "owns status + artifacts", side="h"
                ),
            ],
        ),
        x=T.MARGIN_L,
        y=diagram_y,
    )
    # Separate request and return lanes between the same node faces.
    client_right = T.MARGIN_L + 21 * D.UNIT_X
    remote_left = T.MARGIN_L + 34 * D.UNIT_X
    for offset, reverse in ((137160, False), (365760, True)):
        T.line(
            slide,
            x=client_right,
            y=diagram_y + offset,
            w=remote_left - client_right,
            h=0,
            colour=P.faint,
            reverse=reverse,
        )
    for label, offset in (
        ("message/send, tasks/get", -182880),
        ("status + artifacts", 411480),
    ):
        _text(
            slide,
            label,
            x=client_right + 91440,
            y=diagram_y + offset,
            w=remote_left - client_right - 91440,
            h=274320,
        )
    _text(
        slide,
        "Discover /.well-known/agent-card.json; send the task; follow "
        "working \u2192 completed; collect the artifact.",
        x=T.MARGIN_L,
        y=4114800,
        w=T.CONTENT_W,
        h=411480,
        size=15,
    )
    C.table(
        slide,
        ("", "MCP", "A2A"),
        (
            ("Unit of work", "A tool call", "A task"),
            (
                "Operations",
                "tools/list, tools/call",
                "message/send, tasks/get",
            ),
            (
                "Lifecycle",
                "Request \u2192 response",
                "working \u2192 completed (or another terminal state)",
            ),
            ("Discovery", "tools/list", "/.well-known/agent-card.json"),
        ),
        x=T.MARGIN_L,
        y=4572000,
        w=T.CONTENT_W,
        widths=(1.7, 3.0, 4.5),
        row_h=411480,
        size=15,
    )
    C.use_case(
        slide,
        who="Support assistant needs specialist log analysis",
        steps=(
            "Discover diagnostics agent",
            "Send the task",
            "Follow status",
            "Collect report",
        ),
        result="A specialist answer without sharing code.",
        x=T.MARGIN_L,
        y=USE_Y,
        w=T.CONTENT_W,
        accent=P.violet,
    )


@lru_cache(maxsize=1)
def installed_mros() -> dict[str, tuple[str, ...]]:
    """Inspect installed classes without constructing any clients."""
    from agent_framework import Agent, Executor, Workflow
    from agent_framework.anthropic import AnthropicClient
    from agent_framework.foundry import FoundryAgent, FoundryChatClient
    from agent_framework.openai import OpenAIChatClient
    from autogen_agentchat.agents import AssistantAgent
    from autogen_agentchat.teams import RoundRobinGroupChat

    from msai_demo.offline import ScriptedChatClient

    return {
        cls.__name__: tuple(base.__name__ for base in cls.__mro__)
        for cls in (
            OpenAIChatClient,
            FoundryChatClient,
            AnthropicClient,
            Agent,
            FoundryAgent,
            Workflow,
            Executor,
            AssistantAgent,
            RoundRobinGroupChat,
            ScriptedChatClient,
        )
    }


def slide_mro(prs: Presentation, facts: Facts) -> None:
    """Factor repeated exact MRO suffixes for legibility."""
    del facts
    slide = T.content_slide(
        prs,
        eyebrow="class hierarchy appendix",
        title="Exact method resolution order",
        deck="Read left to right. These chains are inspected from the "
        "installed Python packages at build time.",
        number=40,
        accent=P.blue,
    )
    mros = installed_mros()
    tails = {
        "[C]": ("SerializationMixin", "ABC", "Generic", "object"),
        "[A]": ("SerializationMixin", "Generic", "object"),
        "[G]": (
            "ABC",
            "TaskRunner",
            "Protocol",
            "ComponentBase",
            "ComponentToConfig",
            "ComponentLoader",
            "Component",
            "ComponentFromConfig",
            "ComponentSchemaType",
            "Generic",
            "object",
        ),
    }
    rows = []
    for name, mro in mros.items():
        chain = mro[1:]
        for marker, tail in tails.items():
            if chain[-len(tail) :] == tail:
                chain = (*chain[: -len(tail)], marker)
                break
        rows.append((name, " \u2192 ".join(chain)))
    C.table(
        slide,
        ("Class", "Bases in resolution order (shared suffixes below)"),
        rows,
        x=T.MARGIN_L,
        y=T.Y_BODY,
        w=T.CONTENT_W,
        widths=(2.0, 9.8),
        row_h=365760,
        size=14,
        mono_columns=(0,),
    )
    top = 7391400
    for marker, chain in tails.items():
        text = f"{marker} = " + " \u2192 ".join(chain)
        _text(
            slide,
            text,
            x=T.MARGIN_L,
            y=top,
            w=T.CONTENT_W,
            h=548640 if marker == "[G]" else 320040,
            size=14,
        )
        top += 548640 if marker == "[G]" else 320040
    _text(
        slide,
        "GroupChatBuilder.build() \u2192 Workflow. ScriptedChatClient has no "
        "ChatTelemetryLayer.",
        x=T.MARGIN_L,
        y=8705088,
        w=T.CONTENT_W,
        h=411480,
        size=14,
        colour=P.ink_soft,
        bold=True,
    )

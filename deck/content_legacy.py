"""Legacy frameworks and the application logic that carries forward."""

from __future__ import annotations

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

CODE_W = 7635240
RIGHT_X = 9345168
RIGHT_W = 7498080
USE_Y = 7040880


def _text(
    slide: Slide,
    text: str,
    *,
    x: int,
    y: int,
    w: int,
    h: int = 548640,
    size: float = 14,
    colour: str = P.muted,
    bold: bool = False,
) -> None:
    box = text_box(slide, x=x, y=y, w=w, h=h)
    write(box, plain(text), size=size, colour=colour, bold=bold)


def slide_section(prs: Presentation, facts: Facts) -> None:
    """Divider for the four legacy technologies."""
    del facts
    T.section_slide(
        prs,
        index="02",
        eyebrow="the legacy estate",
        title_lines=["What you already", "built still works"],
        deck="Understand the existing application before choosing a "
        "migration path.",
        bullets=(
            "AutoGen: agents that alternate turns",
            "Semantic Kernel: plugins, connectors and filters",
            "Bot Framework to Microsoft 365 Agents SDK",
            "prompt flow becomes a typed workflow",
        ),
        number=9,
        accent=P.amber,
    )


def slide_autogen(prs: Presentation, facts: Facts) -> None:
    """AutoGen's team pattern and persistent state."""
    slide = T.content_slide(
        prs,
        eyebrow="autogen",
        title="AutoGen invented this pattern, and it still works",
        deck="AutoGen coordinates conversational agents with a team, a "
        "stopping rule and saved state.",
        number=10,
        accent=P.amber,
    )
    C.run_strip(slide, "autogen")
    D.draw(
        slide,
        D.Schema(
            nodes=[
                D.Node(
                    "task",
                    "task",
                    col=0,
                    row=3,
                    width=7,
                    height=2.7,
                    colour=P.blue,
                ),
                D.Node(
                    "team",
                    "RoundRobinGroupChat",
                    col=10,
                    row=3,
                    width=15,
                    height=2.7,
                    colour=P.amber,
                ),
                D.Node(
                    "writer",
                    "writer agent",
                    col=29,
                    row=0,
                    width=12,
                    height=2.7,
                    colour=P.coral,
                ),
                D.Node(
                    "reviewer",
                    "reviewer agent",
                    col=29,
                    row=6,
                    width=12,
                    height=2.7,
                    colour=P.violet,
                ),
                D.Node(
                    "state",
                    "saved team state",
                    col=10,
                    row=11,
                    width=15,
                    height=2.7,
                    kind="state",
                    colour=P.amber,
                ),
            ],
            edges=[
                D.Edge("task", "team", side="h"),
                D.Edge("team", "writer", "turn 0"),
                D.Edge("team", "reviewer", "turn 1"),
                D.Edge("team", "state", "save_state()", side="v"),
            ],
            caption="The framework owns turn-taking and team state. Your "
            "app owns acceptance and business actions.",
        ),
        x=T.MARGIN_L,
        y=T.Y_BODY,
    )
    C.table(
        slide,
        ("Concept", "What it does"),
        (
            ("AssistantAgent", "Instructions, a model client and tools"),
            ("Round-robin team", "Alternate writer and reviewer turns"),
            ("Termination", "APPROVE or the maximum turn count"),
            ("save_state / load_state", "Persist and reload the conversation"),
            ("Application gate", "Ask the human before accepting work"),
        ),
        x=11658600,
        y=T.Y_BODY,
        w=5187240,
        widths=(2.1, 3.0),
        row_h=548640,
        size=14,
    )
    C.use_case(
        slide,
        who="Bid team needs a reviewed draft",
        steps=(
            "Writer drafts",
            "Reviewer challenges",
            "Alternate until APPROVE or limit",
        ),
        result="A draft for a human to check.",
        x=T.MARGIN_L,
        y=USE_Y,
        w=T.CONTENT_W,
        accent=P.amber,
    )
    C.source_note(
        slide,
        f"Installed autogen-agentchat {facts.autogen_version}; last release "
        f"{facts.autogen_last_release}. "
        "Source: installed package metadata and recorded research in "
        "deck/facts.py.",
    )


def slide_semantic_kernel(prs: Presentation, facts: Facts) -> None:
    """Map kernel concepts to the full agent middleware boundaries."""
    del facts
    slide = T.content_slide(
        prs,
        eyebrow="semantic kernel",
        title="Semantic Kernel is in maintenance, and it has a ceiling",
        deck="A Kernel holds plugins and model connectors, with filters "
        "around invocations.",
        number=11,
        accent=P.amber,
    )
    C.run_strip(slide, "semantic-kernel")
    for left, current in ((T.MARGIN_L, False), (RIGHT_X, True)):
        colour = P.teal if current else P.amber
        D.draw(
            slide,
            D.Schema(
                nodes=[
                    D.Node(
                        "request",
                        "request",
                        col=0,
                        row=2,
                        width=6,
                        height=2.7,
                        colour=P.faint,
                    ),
                    D.Node(
                        "owner",
                        "Agent" if current else "Kernel",
                        col=8,
                        row=2,
                        width=8,
                        height=2.7,
                        colour=colour,
                    ),
                    D.Node(
                        "tool",
                        "@tool" if current else "@kernel_function",
                        col=19,
                        row=0,
                        width=13,
                        height=2.7,
                        colour=P.coral,
                    ),
                    D.Node(
                        "client",
                        "ChatClient" if current else "chat connector",
                        col=19,
                        row=5,
                        width=13,
                        height=2.7,
                        colour=P.blue,
                    ),
                ],
                edges=[
                    D.Edge("request", "owner", side="h"),
                    D.Edge("owner", "tool"),
                    D.Edge("owner", "client"),
                ],
            ),
            x=left,
            y=T.Y_BODY,
        )
        _text(
            slide,
            "Middleware at agent, tool and model boundaries"
            if current
            else "Filters wrap invocations",
            x=left,
            y=4663440,
            w=CODE_W,
            h=365760,
            colour=colour,
            bold=True,
        )
    C.table(
        slide,
        ("Semantic Kernel", "Agent Framework", "What changes for you"),
        (
            ("Kernel", "Agent", "Owns tools, session and middleware"),
            (
                "@kernel_function",
                "@tool",
                "Schema inferred from the signature",
            ),
            (
                "Connector",
                "ChatClient",
                "One client contract across providers",
            ),
            (
                "Filter",
                "Middleware",
                "Typed interception of agent runs, tool calls and model calls",
            ),
            ("Planner", "Workflow", "An explicit graph you can test"),
        ),
        x=T.MARGIN_L,
        y=5120640,
        w=T.CONTENT_W,
        widths=(2.1, 2.1, 6.0),
        row_h=292608,
        size=14,
        mono_columns=(0, 1),
    )
    C.use_case(
        slide,
        who="Helpdesk developer needs ticket status",
        steps=(
            "User gives ticket number",
            "Kernel calls lookup plugin",
            "Model words the answer",
        ),
        result="A readable status reply.",
        x=T.MARGIN_L,
        y=USE_Y,
        w=T.CONTENT_W,
        accent=P.amber,
    )
    C.source_note(
        slide,
        "Tested dependency constraint: semantic-kernel 1.44.1 pins "
        "azure-ai-projects<2.5. "
        "Full compatibility table is in the appendix.",
    )


def slide_channel(prs: Presentation, facts: Facts) -> None:
    """Change the adapter while preserving the handler."""
    del facts
    slide = T.content_slide(
        prs,
        eyebrow="the channel",
        title="The adapter changes. Your handler does not.",
        deck="Bot Framework and Microsoft 365 Agents SDK carry channel "
        "activities into an application handler.",
        number=12,
        accent=P.amber,
    )
    C.run_strip(slide, "bot-framework", "m365-agents")
    D.draw(
        slide,
        D.Schema(
            nodes=[
                D.Node(
                    "oldin",
                    "channel activity",
                    col=0,
                    row=0,
                    width=12,
                    height=2.7,
                    colour=P.faint,
                ),
                D.Node(
                    "oldadapter",
                    "BotFrameworkAdapter",
                    col=17,
                    row=0,
                    width=19,
                    height=2.7,
                    colour=P.amber,
                ),
                D.Node(
                    "oldhandler",
                    "handle_activity()",
                    col=43,
                    row=0,
                    width=18,
                    height=2.7,
                    colour=P.teal,
                ),
                D.Node(
                    "newin",
                    "channel activity",
                    col=0,
                    row=5.5,
                    width=12,
                    height=2.7,
                    colour=P.faint,
                ),
                D.Node(
                    "newadapter",
                    "AgentApplication",
                    col=17,
                    row=5.5,
                    width=19,
                    height=2.7,
                    colour=P.blue,
                ),
                D.Node(
                    "newhandler",
                    "handle_activity()",
                    col=43,
                    row=5.5,
                    width=18,
                    height=2.7,
                    colour=P.teal,
                ),
            ],
            edges=[
                D.Edge("oldin", "oldadapter", side="h"),
                D.Edge("oldadapter", "oldhandler", side="h"),
                D.Edge("newin", "newadapter", side="h"),
                D.Edge("newadapter", "newhandler", side="h"),
            ],
            caption="The Azure Bot registration stays. Assess "
            "authentication, state and channels when moving the adapter.",
        ),
        x=T.MARGIN_L,
        y=T.Y_BODY,
    )
    C.table(
        slide,
        ("Bot Framework package", "Microsoft 365 Agents SDK package"),
        (
            (
                "botbuilder-core / botbuilder-schema",
                "microsoft-agents-hosting-core / microsoft-agents-activity",
            ),
            (
                "botbuilder-integration-aiohttp",
                "microsoft-agents-hosting-aiohttp",
            ),
            ("botframework-connector", "microsoft-agents-authentication-msal"),
        ),
        x=T.MARGIN_L,
        y=5513832,
        w=T.CONTENT_W,
        widths=(1.0, 1.4),
        row_h=320040,
        size=14,
        mono_columns=(0, 1),
    )
    half = (T.CONTENT_W - 274320) // 2
    C.use_case(
        slide,
        who="Employee asks an existing Bot Framework bot for ticket status",
        steps=(
            "Message",
            "Adapter",
            "Handler queries tickets",
            "Channel reply",
        ),
        result="Ticket status in the existing channel.",
        x=T.MARGIN_L,
        y=USE_Y,
        w=half,
        accent=P.amber,
    )
    C.use_case(
        slide,
        who="Teams user asks the Microsoft 365 agent for ticket status",
        steps=(
            "Activity",
            "AgentApplication routes",
            "Same handler",
            "Teams reply",
        ),
        result="The same business answer in Teams.",
        x=T.MARGIN_L + half + 274320,
        y=USE_Y,
        w=half,
        accent=P.teal,
    )


def slide_prompt_flow(prs: Presentation, facts: Facts) -> None:
    """Microsoft's concept mapping from prompt flow to typed code."""
    del facts
    slide = T.content_slide(
        prs,
        eyebrow="prompt flow",
        title="prompt flow retires; its graph becomes a workflow",
        deck="prompt flow connects prompt and Python nodes. Its replacement "
        "is a code-defined Agent Framework workflow.",
        number=13,
        accent=P.amber,
    )
    C.run_strip(slide, "promptflow", "workflow")
    C.table(
        slide,
        ("prompt flow", "Migration", "Agent Framework / evaluation"),
        (
            ("Flow: YAML / visual graph", "\u2192", "WorkflowBuilder"),
            ("Node", "\u2192", "Executor with @handler"),
            ("LLM node", "\u2192", "FoundryChatClient().as_agent()"),
            ("If node", "\u2192", "add_edge(condition=...)"),
            ("Parallel nodes", "\u2192", "add_fan_out_edges"),
            ("Evaluation flow", "\u2192", "azure-ai-evaluation evaluators"),
            ("Tracing", "\u2192", "OpenTelemetry"),
        ),
        x=T.MARGIN_L,
        y=T.Y_BODY,
        w=10424160,
        widths=(2.9, 1.2, 4.0),
        row_h=457200,
        size=15,
        mono_columns=(2,),
    )
    C.card(slide, x=12344400, y=T.Y_BODY, w=4419600, h=3383280)
    _text(
        slide,
        "RETIREMENT",
        x=12618720,
        y=T.Y_BODY + 228600,
        w=3870960,
        size=14,
        colour=P.coral,
        bold=True,
    )
    _text(
        slide,
        f"Retires {R.PROMPT_FLOW_RETIREMENT}",
        x=12618720,
        y=3904488,
        w=3870960,
        size=19,
        colour=P.ink,
        bold=True,
    )
    _text(
        slide,
        R.PROMPT_FLOW_RUNTIME_STATUS,
        x=12618720,
        y=4498848,
        w=3870960,
        h=822960,
        size=15,
    )
    _text(
        slide,
        R.PROMPT_FLOW_EDITOR_STATUS,
        x=12618720,
        y=5504688,
        w=3870960,
        h=822960,
        size=15,
    )
    C.use_case(
        slide,
        who="Support analyst needs repeatable ticket classification",
        steps=(
            "Load ticket text",
            "Run prompt and Python steps",
            "Validate category",
        ),
        result="The same pipeline, now a typed workflow you can evaluate.",
        x=T.MARGIN_L,
        y=USE_Y,
        w=T.CONTENT_W,
        accent=P.amber,
    )
    C.source_note(
        slide,
        "Source: Microsoft Learn, prompt flow migration overview. The "
        "repository command reports its recorded mode.",
    )


def slide_cost_of_staying(prs: Presentation, facts: Facts) -> None:
    """The evidence slide: three constraints, each reproducible."""
    del facts
    slide = T.content_slide(
        prs,
        eyebrow="compatibility appendix",
        title="Compatibility constraints in tested versions",
        deck=(
            "Three dependency constraints you inherit by keeping the "
            "legacy packages - plus one current adapter to avoid. Each "
            "line was read from PyPI metadata and reproduced with uv lock."
        ),
        number=17,
        accent=P.coral,
    )

    C.table(
        slide,
        ("Legacy package", "Pin it carries", "Current", "What it costs you"),
        (
            (
                "semantic-kernel 1.44.1",
                "azure-ai-projects<2.5",
                "2.6.0",
                "No shared lockfile with the current Foundry SDK",
            ),
            (
                "semantic-kernel[autogen]",
                "autogen-agentchat<0.4",
                "0.7.5",
                "Its AutoGen bridge is three generations behind",
            ),
            (
                "promptflow-tracing 1.18.5",
                "opentelemetry-sdk<1.39",
                "API >=1.39",
                "No shared lockfile with Agent Framework",
            ),
        ),
        x=T.MARGIN_L,
        y=T.Y_BODY,
        w=T.CONTENT_W,
        widths=(2.5, 2.3, 1.3, 3.6),
        row_h=548640,
        size=15,
        mono_columns=(0, 1, 2),
        accents=(P.coral, P.coral, P.coral),
    )

    C.table(
        slide,
        ("Other dependency facts", "Pin", "Current", "Do this"),
        (
            (
                "agent-framework-foundry-local",
                "foundry-local-sdk<0.5.2",
                "2.0.1",
                "Call the OpenAI-compatible local endpoint",
            ),
            (
                "autogen-ext[openai] 0.7.5",
                "openai>=1.93",
                "3.13.0",
                "Nothing: AutoGen and Agent Framework coexist",
            ),
        ),
        x=T.MARGIN_L,
        y=T.Y_BODY + 2560320,
        w=T.CONTENT_W,
        widths=(2.5, 2.3, 1.3, 3.6),
        row_h=548640,
        size=15,
        mono_columns=(0, 1, 2),
        accents=(P.amber, P.teal),
    )

    C.callout(
        slide,
        "The last row is the good news: you do not have to migrate "
        "everything at once. AutoGen and Agent Framework install side "
        "by side, which is why the comparison can run both.",
        x=T.MARGIN_L,
        y=T.Y_BODY + 4480560,
        w=T.CONTENT_W,
        accent=P.teal,
    )
    C.source_note(
        slide,
        "PyPI metadata API, read 2026-09-14. Reproduce every row with: "
        "uv lock  (see docs/research.md section 3.5).",
    )

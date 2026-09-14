"""Agent Framework architecture and illustrative jobs."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

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
    """Divider for the current runtime."""
    del facts
    T.section_slide(
        prs,
        index="03",
        eyebrow="Microsoft Agent Framework",
        title_lines=["Agents become", "parts of a workflow"],
        deck="A Python runtime for agents, typed workflows and the tools "
        "around them.",
        bullets=(
            "Agent and provider class families",
            "Workflow and harness",
            "MCP tools and A2A delegation",
            "Traces that explain the decision",
        ),
        number=14,
        accent=P.teal,
    )


def slide_agent(prs: Presentation, facts: Facts) -> None:
    """The agent's four building blocks and a real API excerpt."""
    del facts
    slide = T.content_slide(
        prs,
        eyebrow="the agent",
        title="An agent is a client, instructions, tools and a session",
        deck="An Agent combines a model client, instructions, callable "
        "tools and conversation state.",
        number=15,
        accent=P.teal,
    )
    C.run_strip(slide, "agent-framework")
    T.code_panel(slide, x=T.MARGIN_L, y=T.Y_BODY, w=CODE_W, h=3291840)
    D.panel_label(
        slide,
        "API excerpt - agent_framework_demo.py (abridged)",
        x=T.MARGIN_L + 274320,
        y=T.Y_BODY + 182880,
        w=CODE_W - 548640,
    )
    lines = (
        "agent = Agent(",
        "    client=client,",
        '    name="PilotArchitect",',
        "    instructions=instructions,",
        "    tools=build_pricing_tool(),",
        "    context_providers=[InMemoryHistoryProvider()],",
        ")",
        "session = agent.create_session()",
        "await agent.run(q1, session=session)",
        "await agent.run(q2, session=session)",
    )
    D.code_lines(
        slide,
        [[(line, P.code_fg)] for line in lines],
        x=T.MARGIN_L + 274320,
        y=T.Y_BODY + 594360,
        w=CODE_W - 548640,
        h=2560320,
        size=14,
    )
    D.draw(
        slide,
        D.Schema(
            nodes=[
                D.Node(
                    "user",
                    "question",
                    col=0,
                    row=3.2,
                    width=7,
                    height=2.7,
                    colour=P.faint,
                ),
                D.Node(
                    "agent",
                    "Agent",
                    col=9,
                    row=3.2,
                    width=9,
                    height=3.2,
                    colour=P.teal,
                    sub="instructions",
                ),
                D.Node(
                    "client",
                    "ChatClient",
                    col=21,
                    row=0,
                    width=11,
                    height=2.7,
                    colour=P.blue,
                ),
                D.Node(
                    "tools",
                    "@tool functions",
                    col=21,
                    row=6.4,
                    width=11,
                    height=2.7,
                    colour=P.coral,
                ),
                D.Node(
                    "session",
                    "AgentSession",
                    col=9,
                    row=10,
                    width=11,
                    height=2.8,
                    kind="state",
                    colour=P.teal,
                ),
            ],
            edges=[
                D.Edge("user", "agent", side="h"),
                D.Edge("agent", "client"),
                D.Edge("agent", "tools"),
                D.Edge("agent", "session", side="v"),
            ],
            caption="Your process owns the tool loop and session. The "
            "client calls the model.",
        ),
        x=RIGHT_X,
        y=T.Y_BODY,
    )
    _text(
        slide,
        "Offline mode: the scripted client drives the real tool loop "
        "without an API key.",
        x=T.MARGIN_L,
        y=6583680,
        w=T.CONTENT_W,
        colour=P.ink_soft,
        bold=True,
    )
    C.use_case(
        slide,
        who="New employee needs a leave-policy answer",
        steps=(
            "Ask the agent",
            "Call policy-search tool",
            "Answer from passages",
        ),
        result="An answer with a source reference.",
        x=T.MARGIN_L,
        y=USE_Y,
        w=T.CONTENT_W,
        accent=P.teal,
    )


def slide_workflow(prs: Presentation, facts: Facts) -> None:
    """A typed workflow, its gate and the recorded local evidence."""
    slide = T.content_slide(
        prs,
        eyebrow="the workflow",
        title="The graph checks eligibility, then waits for a human decision",
        deck="A Workflow connects typed executors with edges, conditions "
        "and persisted approval requests.",
        number=17,
        accent=P.teal,
    )
    C.run_strip(slide, "workflow")
    D.draw(
        slide,
        D.Schema(
            nodes=[
                D.Node(
                    "draft",
                    "draft",
                    col=0,
                    row=3,
                    width=8,
                    height=2.7,
                    colour=P.blue,
                ),
                D.Node(
                    "review",
                    "review",
                    col=11,
                    row=3,
                    width=8,
                    height=2.7,
                    colour=P.teal,
                ),
                D.Node(
                    "switch",
                    "eligible?",
                    col=22,
                    row=2,
                    width=10,
                    height=4.6,
                    kind="decision",
                    colour=P.coral,
                ),
                D.Node(
                    "approve",
                    "approve",
                    col=36,
                    row=0,
                    width=11,
                    height=2.7,
                    colour=P.coral,
                ),
                D.Node(
                    "revise",
                    "revise",
                    col=36,
                    row=6,
                    width=11,
                    height=2.7,
                    colour=P.amber,
                ),
                D.Node(
                    "accept",
                    "accept",
                    col=53,
                    row=3,
                    width=11,
                    height=2.7,
                    colour=P.teal,
                ),
            ],
            edges=[
                D.Edge("draft", "review", side="h"),
                D.Edge("review", "switch", side="h"),
                D.Edge("switch", "approve", "Case"),
                D.Edge("switch", "revise", "Default"),
                D.Edge("approve", "accept"),
                D.Edge("revise", "accept"),
            ],
        ),
        x=T.MARGIN_L,
        y=T.Y_BODY,
    )
    _text(
        slide,
        "Both branches request a named human decision before acceptance.",
        x=T.MARGIN_L,
        y=4892040,
        w=T.CONTENT_W,
        colour=P.ink_soft,
        bold=True,
    )
    T.code_panel(slide, x=T.MARGIN_L, y=5394960, w=CODE_W, h=1371600)
    D.code_lines(
        slide,
        [
            [(line, P.code_fg)]
            for line in (
                "WorkflowBuilder(start_executor=draft,",
                "                checkpoint_storage=storage)",
                "    .add_edge(draft, review)",
                "await ctx.request_info(proposal, HumanDecision)",
            )
        ],
        x=T.MARGIN_L + 228600,
        y=5577840,
        w=CODE_W - 457200,
        h=1097280,
        size=14,
    )
    run = facts.demo_run("workflow")
    _text(
        slide,
        f"Recorded: outputs before approval = "
        f"{run['outputs_before_approval']}; "
        f"checkpoints = {run['checkpoint_count']}; "
        f"restored = {str(run['restored']).lower()}.",
        x=RIGHT_X,
        y=5394960,
        w=RIGHT_W,
        h=548640,
    )
    _text(
        slide,
        "Agent Framework workflows are code. Foundry portal Workflows "
        "(preview) "
        f"retire {R.FOUNDRY_WORKFLOWS_RETIREMENT}.",
        x=RIGHT_X,
        y=6035040,
        w=RIGHT_W,
        h=640080,
    )
    C.use_case(
        slide,
        who="Merchandiser needs reviewed product copy",
        steps=(
            "Draft",
            "Check required fields",
            "Pause for approval",
            "Publish after approval",
        ),
        result="A controlled update.",
        x=T.MARGIN_L,
        y=USE_Y,
        w=T.CONTENT_W,
        accent=P.teal,
    )


def slide_harness(prs: Presentation, facts: Facts) -> None:
    """The long-task bundle and its context controls."""
    del facts
    slide = T.content_slide(
        prs,
        eyebrow="the harness",
        title="When the task outlives one context window",
        deck="create_harness_agent() composes an Agent with planning, file "
        "memory, compaction and approval.",
        number=18,
        accent=P.teal,
    )
    C.run_strip(slide, "harness")
    C.table(
        slide,
        ("Capability", "SDK default", "Why it matters"),
        (
            ("Todo tracking", "on", "The plan is state"),
            ("Plan / execute modes", "on", "Separate planning and action"),
            ("Session file memory", "on", "Keep findings outside context"),
            ("Compaction", "token limit", "Bounds context growth per call"),
            ("Tool auto-approval", "on", "Apply standing approval rules"),
            ("OpenTelemetry", "on", "Inspect the run"),
            (
                "Shared files / children",
                "opt-in",
                "Scope access and delegation",
            ),
        ),
        x=T.MARGIN_L,
        y=T.Y_BODY,
        w=CODE_W,
        widths=(2.5, 1.3, 3.6),
        row_h=411480,
        size=14,
    )
    D.draw(
        slide,
        D.Schema(
            nodes=[
                D.Node(
                    "todo",
                    "todos + plan",
                    col=0,
                    row=0,
                    width=12,
                    height=2.7,
                    colour=P.blue,
                ),
                D.Node(
                    "memory",
                    "file memory",
                    col=20,
                    row=0,
                    width=12,
                    height=2.7,
                    kind="state",
                    colour=P.blue,
                ),
                D.Node(
                    "agent",
                    "harness Agent",
                    col=10,
                    row=5.5,
                    width=12,
                    height=2.7,
                    colour=P.teal,
                ),
                D.Node(
                    "compact",
                    "compaction",
                    col=0,
                    row=11,
                    width=12,
                    height=2.7,
                    colour=P.amber,
                ),
                D.Node(
                    "approval",
                    "approval",
                    col=20,
                    row=10.4,
                    width=12,
                    height=4,
                    kind="decision",
                    colour=P.coral,
                ),
            ],
            edges=[
                D.Edge("agent", key)
                for key in ("todo", "memory", "compact", "approval")
            ],
        ),
        x=RIGHT_X,
        y=T.Y_BODY,
    )
    _text(
        slide,
        "This demo disables compaction for a short deterministic lesson; "
        "telemetry is opt-in.",
        x=RIGHT_X,
        y=6035040,
        w=RIGHT_W,
        h=548640,
    )
    _text(
        slide,
        "A virtual path is not a sandbox. The demo writes into "
        ".msai_workspace/ and gates irreversible tools.",
        x=T.MARGIN_L,
        y=6638544,
        w=T.CONTENT_W,
        h=365760,
    )
    C.use_case(
        slide,
        who="Analyst needs a multi-document briefing",
        steps=(
            "Create a todo list",
            "Read documents",
            "Save findings to files",
            "Assemble report",
        ),
        result="A draft backed by persistent notes.",
        x=T.MARGIN_L,
        y=USE_Y,
        w=T.CONTENT_W,
        accent=P.teal,
    )


def slide_observability(prs: Presentation, facts: Facts) -> None:
    """A real recorded span tree and the controls that govern export."""
    slide = T.content_slide(
        prs,
        eyebrow="observability",
        title="A useful trace explains the whole decision",
        deck="OpenTelemetry connects the agent, model and tool spans so a "
        "developer can follow one answer.",
        number=21,
        accent=P.teal,
    )
    C.run_strip(slide, "otel --trace local")
    spans = facts.spans
    depths = _span_depths(spans)
    ordered = sorted(spans, key=lambda span: depths[span["span_id"]])
    colours = {"invoke_agent": P.teal, "chat": P.blue, "execute_tool": P.coral}
    nodes = [
        D.Node(
            span["span_id"],
            str(span["name"]),
            col=depths[span["span_id"]] * 4,
            row=index * 4.1,
            width=23,
            height=3.2,
            colour=colours.get(
                str(span["attributes"].get("gen_ai.operation.name")), P.blue
            ),
            mono=True,
        )
        for index, span in enumerate(ordered)
    ]
    edges = [
        D.Edge(str(span["parent_id"]), str(span["span_id"]), side="v")
        for span in ordered
        if span["parent_id"]
    ]
    D.draw(slide, D.Schema(nodes=nodes, edges=edges), x=T.MARGIN_L, y=T.Y_BODY)
    _text(
        slide,
        f"Recorded offline: {len(spans)} spans; "
        f"exported={str(facts.otel['exported']).lower()}; "
        f"token usage: {facts.otel['usage'] or 'not reported'}.",
        x=T.MARGIN_L,
        y=6286500,
        w=CODE_W,
        h=640080,
    )
    C.table(
        slide,
        ("Control", "Default / destination"),
        (
            ("ENABLE_INSTRUMENTATION", "true in SDK; demo opts in"),
            ("ENABLE_SENSITIVE_DATA", "false; prompts and tool args"),
            ("ENABLE_CONSOLE_EXPORTERS", "false; stdout when enabled"),
            ("OTEL_EXPORTER_OTLP_ENDPOINT", "unset; your OTLP collector"),
            ("APPLICATIONINSIGHTS_...", "unset; Azure Monitor opt-in"),
        ),
        x=RIGHT_X,
        y=T.Y_BODY,
        w=RIGHT_W,
        widths=(3.2, 3.0),
        row_h=502920,
        size=14,
        mono_columns=(0,),
    )
    _text(
        slide,
        "Ordinary commands force instrumentation off. Only --trace turns it "
        "on. "
        "Sensitive data stays off outside development.",
        x=RIGHT_X,
        y=6260592,
        w=RIGHT_W,
        h=640080,
        colour=P.ink_soft,
        bold=True,
    )
    C.use_case(
        slide,
        who="Developer investigates a slow answer",
        steps=(
            "Find the trace",
            "Inspect model and tool spans",
            "Spot the slow step",
        ),
        result="One component to fix.",
        x=T.MARGIN_L,
        y=USE_Y,
        w=T.CONTENT_W,
        accent=P.teal,
    )


def _span_depths(spans: list[dict[str, Any]]) -> dict[str, int]:
    """Return each span's distance from the root of its trace."""
    parents = {span["span_id"]: span["parent_id"] for span in spans}
    depths: dict[str, int] = {}
    for span_id, parent in parents.items():
        depth, cursor = 0, parent
        while cursor in parents:
            depth += 1
            cursor = parents[cursor]
        depths[span_id] = depth
    return depths

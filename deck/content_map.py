"""Slides 7-11: the map of the stack, before any single product.

Architects need the shape of the thing before the API names. Five
layers, one decision rule, one repository, one readiness command.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import components as C
import diagrams as D
import theme as T
from theme import P

if TYPE_CHECKING:
    from facts import Facts
    from pptx.presentation import Presentation

LAYERS = (
    (
        "Channel",
        "Microsoft 365 Agents SDK",
        "Teams, Copilot, web - where the user actually is",
        P.violet,
    ),
    (
        "Runtime",
        "Microsoft Agent Framework",
        "agents, workflows, harness, orchestrations",
        P.teal,
    ),
    (
        "Managed runtime",
        "Foundry Agent Service",
        "the service owns the agent, its versions and its tools",
        P.sky,
    ),
    (
        "Models and knowledge",
        "Foundry Models · AI Search · Foundry IQ",
        "inference, retrieval, grounding, citations",
        P.blue,
    ),
    (
        "Control plane",
        "Entra · guardrails · observability · evaluation",
        "identity, policy, traces, scores - adopt on day one",
        P.coral,
    ),
)


def slide_section(prs: Presentation, facts: Facts) -> None:
    """Divider for the map section."""
    del facts
    T.section_slide(
        prs,
        index="01",
        eyebrow="the map",
        title_lines=["Five layers,", "five responsibilities"],
        deck=(
            "Complementary layers, not a ladder you are obliged to "
            "climb end to end."
        ),
        bullets=(
            "What each layer owns, and which failure it prevents",
            "The platform decision, before any SDK detail",
            "Choose the lowest abstraction that still meets the need",
            "Two reference architectures: today, and the target",
        ),
        number=7,
    )


def slide_stack_map(prs: Presentation, facts: Facts) -> None:
    """One stack, five responsibilities."""
    del facts
    slide = T.content_slide(
        prs,
        eyebrow="stack map",
        title="One stack, five responsibilities",
        deck=(
            "Each layer owns a different failure mode. Pick the layer "
            "that matches the risk you actually have."
        ),
        number=8,
    )

    for index, (role, product, detail, colour) in enumerate(LAYERS):
        top = T.Y_BODY + index * 1097280
        C.layer_row(
            slide,
            top=top,
            colour=colour,
            role=role,
            product=product,
            detail=detail,
            x=T.MARGIN_L,
            w=T.COL_MAIN_W,
        )

    C.rail(
        slide,
        title="Read it downwards",
        lines=(
            "The channel layer decides who can talk to the agent.",
            "The runtime layer decides what the agent may do, and what "
            "happens when a human has to decide.",
            "The managed layer moves that runtime into a service with "
            "versions, private networking and a support contract.",
            "The control plane is the only layer to adopt on day one, "
            "whatever else you choose.",
        ),
        h=5486400,
    )


def slide_decision(prs: Presentation, facts: Facts) -> None:
    """The one rule that keeps a platform choice defensible."""
    del facts
    slide = T.content_slide(
        prs,
        eyebrow="decision",
        title="Choose the lowest abstraction that still meets the need",
        deck=(
            "Every step upwards buys capability and bills you in runtime "
            "behaviour you now have to own, test and observe."
        ),
        number=9,
    )

    C.steps(
        slide,
        (
            (
                "1",
                "A model call",
                "One request. No tools, no state. Reach for it when a "
                "single classification or rewrite is the whole job.",
            ),
            (
                "2",
                "An Agent Framework agent",
                "Tools, a session, middleware. Reach for it when the "
                "agent loop IS the workflow.",
            ),
            (
                "3",
                "An Agent Framework workflow",
                "Typed graph, conditional edges, checkpoints, approval. "
                "Reach for it when you must pause, resume or replay.",
            ),
            (
                "4",
                "Foundry Agent Service",
                "Versioned agents, private networking, server-side "
                "execution. Reach for it when the platform, not your "
                "process, should own the agent.",
            ),
        ),
        x=T.MARGIN_L,
        y=T.Y_BODY,
        w=T.COL_MAIN_W,
        step_h=1188720,
    )

    C.rail(
        slide,
        title="One rule on the harness",
        lines=(
            "create_harness_agent() sits beside step 2, not above it.",
            "Right when the task outlives one context window.",
            "Wrong when you can write the control flow down: use a "
            "workflow instead.",
            "If a plain function does the job, write the function.",
        ),
        accent=P.amber,
    )

    C.callout(
        slide,
        "More abstraction means more runtime behaviour to own, test and "
        "observe.",
        x=T.MARGIN_L,
        y=T.Y_BODY + 5120640,
        w=T.COL_MAIN_W,
    )


def slide_platform_decision(prs: Presentation, facts: Facts) -> None:
    """Four independent choices, not one."""
    del facts
    slide = T.content_slide(
        prs,
        eyebrow="platform decision",
        title="Runtime, channel and cloud service are separate choices",
        deck=(
            "The most expensive mistake here is bundling them. You can "
            "adopt Agent Framework without Foundry, and Foundry without "
            "Teams."
        ),
        number=40,
    )

    C.table(
        slide,
        (
            "Choice",
            "Option",
            "Pick it when",
            "Prerequisite",
        ),
        (
            (
                "Runtime",
                "Agent Framework",
                "You want code-first agents and workflows you can test",
                "Python 3.10+, nothing else",
            ),
            (
                "Runtime",
                "Foundry Agent Service",
                "The platform should own agent versions and networking",
                "A Foundry project and RBAC",
            ),
            (
                "Channel",
                "Microsoft 365 Agents SDK",
                "The user is in Teams, Copilot or a web chat",
                "An Azure Bot registration",
            ),
            (
                "Knowledge",
                "Azure AI Search",
                "You design the index, queries and refresh",
                "A search service and an index",
            ),
            (
                "Knowledge",
                "Foundry IQ",
                "Agents need a managed, permission-aware knowledge base",
                "AI Search plus configured knowledge sources",
            ),
            (
                "Inference",
                "Foundry Models",
                "You want one catalogue, routing and quotas",
                "A Foundry project",
            ),
            (
                "Inference",
                "Foundry Local",
                "Inference must stay on the device",
                "Local SDK and a cached model",
            ),
        ),
        x=T.MARGIN_L,
        y=T.Y_BODY,
        w=T.CONTENT_W,
        widths=(1.3, 2.5, 4.5, 3.0),
        row_h=502920,
        size=14,
        accents=(
            P.teal,
            P.sky,
            P.violet,
            P.blue,
            P.sky,
            P.blue,
            P.sky,
        ),
    )

    C.callout(
        slide,
        "Only one row is mandatory on day one, and it is not on this "
        "table: instrument the thing. Traces and an evaluation set are "
        "what make every other row reversible.",
        x=T.MARGIN_L,
        y=T.Y_BODY + 4480560,
        w=T.CONTENT_W,
        accent=P.coral,
    )


def slide_architectures(prs: Presentation, facts: Facts) -> None:
    """Two reference architectures: what ran today, and the target."""
    del facts
    slide = T.content_slide(
        prs,
        eyebrow="reference architecture",
        title="Start on the laptop. Move the boundary when you must.",
        deck=(
            "Row A runs offline in this room, with optional remote models. "
            "Row B is an illustrative Azure target whose identity, state "
            "and service boundaries still need validation."
        ),
        number=0,
        accent=P.sky,
    )
    C.run_strip(slide, "agent-framework")

    def node(
        key: str, label: str, col: float, row: float, **extra: object
    ) -> D.Node:
        return D.Node(
            key, label, col=col, row=row, width=12, height=3.4, **extra
        )

    D.draw(
        slide,
        D.Schema(
            nodes=[
                node(
                    "cli",
                    "msai-demo",
                    0,
                    0,
                    colour=P.teal,
                    mono=True,
                    sub="your process",
                ),
                node(
                    "af",
                    "Agent Framework",
                    16.5,
                    0,
                    colour=P.teal,
                    sub="agent or workflow",
                ),
                node(
                    "prov",
                    "Model clients",
                    33,
                    0,
                    colour=P.coral,
                    sub="scripted or remote",
                ),
                node(
                    "cp1",
                    "Disk checkpoints",
                    16.5,
                    4.8,
                    kind="state",
                    colour=P.blue,
                ),
                node(
                    "m365",
                    "M365 Agents SDK",
                    0,
                    13.1,
                    colour=P.violet,
                    sub="channel",
                ),
                node(
                    "af2",
                    "Agent Framework",
                    16.5,
                    13.1,
                    colour=P.teal,
                    sub="application / runtime",
                ),
                D.Node(
                    "fm",
                    "Models and knowledge",
                    col=35,
                    row=13.1,
                    width=26.5,
                    height=3.4,
                    colour=P.sky,
                    sub="Foundry models, Search / Foundry IQ",
                ),
                D.Node(
                    "entra",
                    "Microsoft Entra ID",
                    col=49.5,
                    row=17.7,
                    width=12,
                    height=2.3,
                    colour=P.coral,
                ),
                D.Node(
                    "cp2",
                    "durable checkpoints",
                    col=16.5,
                    row=17.7,
                    width=12,
                    height=2.3,
                    kind="state",
                    colour=P.blue,
                ),
            ],
            edges=[
                D.Edge("cli", "af", "task", side="h"),
                D.Edge("af", "prov", "request", side="h", dashed=True),
                D.Edge("af", "cp1", "state", side="v"),
                D.Edge("m365", "af2", "activity", side="h"),
                D.Edge("af2", "fm", "request", side="h", dashed=True),
                D.Edge("af2", "cp2", "state", side="v", dashed=True),
            ],
            boundaries=[
                D.Boundary(
                    "A - local orchestration; optional remote models; no "
                    "Azure required",
                    col=-1.2,
                    row=-1.2,
                    width=47.4,
                    height=10.0,
                    colour=P.teal,
                ),
                D.Boundary(
                    "B - illustrative Azure target, not a deployed system",
                    col=-1.2,
                    row=10.6,
                    width=63.9,
                    height=10.0,
                    colour=P.sky,
                ),
                D.Boundary(
                    "identity + RBAC, tracing",
                    col=15.3,
                    row=12.5,
                    width=47.4,
                    height=8.1,
                    colour=P.coral,
                ),
            ],
        ),
        x=T.MARGIN_L + 182880,
        y=T.Y_BODY + 91440,
    )

    # Match D.draw's normalization while keeping row A unchanged. Route
    # token traffic below the model interface, on two distinct paths.
    canvas = D.Canvas(
        x=T.MARGIN_L + 182880 + int(1.2 * D.UNIT_X),
        y=T.Y_BODY + 91440 + int(1.2 * D.UNIT_Y),
    )
    for label, turn, runtime_row, entra_row, returning in (
        ("token request", 31.0, 16.2, 17.9, False),
        ("token issuance", 29.5, 16.4, 19.3, True),
    ):
        T.line(
            slide,
            x=canvas.left(28.5),
            y=canvas.top(runtime_row),
            w=canvas.width(turn - 28.5),
            h=0,
            colour=P.coral,
            dashed=True,
            arrow=returning,
            reverse=returning,
        )
        T.line(
            slide,
            x=canvas.left(turn),
            y=canvas.top(runtime_row),
            w=0,
            h=canvas.height(entra_row - runtime_row),
            colour=P.coral,
            dashed=True,
            arrow=False,
        )
        T.line(
            slide,
            x=canvas.left(turn),
            y=canvas.top(entra_row),
            w=canvas.width(49.5 - turn),
            h=0,
            colour=P.coral,
            dashed=True,
            arrow=not returning,
        )
        box = T.text_box(
            slide,
            x=canvas.left(33),
            y=canvas.top(entra_row - 1.2),
            w=canvas.width(16),
            h=canvas.height(1.3),
        )
        T.write(box, T.plain(label), size=14, colour=P.coral)

    T.line(
        slide,
        x=canvas.left(30.5),
        y=canvas.top(14.8),
        w=0,
        h=canvas.height(0.1),
        colour=P.coral,
        arrow=False,
    )
    guardrails = T.text_box(
        slide,
        x=canvas.left(28.8),
        y=canvas.top(14.9),
        w=canvas.width(6),
        h=canvas.height(1.2),
    )
    T.write(guardrails, T.plain("guardrails"), size=14, colour=P.coral)

    C.use_case(
        slide,
        who="Architect plans a policy assistant",
        steps=(
            "Channel and runtime",
            "Model and retrieval",
            "Identity and telemetry",
        ),
        result="A design with explicit boundaries.",
        x=T.MARGIN_L,
        y=T.Y_BODY + 4206240,
        w=T.CONTENT_W,
        accent=P.sky,
    )

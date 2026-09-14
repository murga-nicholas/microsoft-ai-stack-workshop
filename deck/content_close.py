"""The close: operating cost, blast radius, and the way out.

Everything up to here was evidence. These two slides turn it into a
choice somebody in the room can actually make on Monday.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import components as C
import theme as T
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from theme import P, plain, text_box, write

if TYPE_CHECKING:
    from facts import Facts
    from pptx.presentation import Presentation

RIGHT_X = 9345168
RIGHT_W = 7498080


def slide_operations(prs: Presentation, facts: Facts) -> None:
    """Cost and blast radius as design-time decisions."""
    del facts
    slide = T.content_slide(
        prs,
        eyebrow="operations",
        title="Cost and blast radius are decided at design time",
        deck=(
            "Both are architecture, not accounting. You find out about "
            "them in a design review or in an incident review."
        ),
        number=42,
        accent=P.coral,
    )

    C.steps(
        slide,
        (
            (
                "1",
                "Context is the bill",
                "Every turn resends the window, and a group chat "
                "broadcasts to every participant. Compaction and file "
                "memory are cost controls, not features.",
            ),
            (
                "2",
                "Bound every loop",
                "max_rounds, a turn cap, a tool-call limit. A runaway "
                "agent should become a handled error, not an invoice.",
            ),
            (
                "3",
                "Blast radius equals tool permissions",
                "Not the good intentions in the system prompt. Deny by "
                "default; gate the irreversible behind an approval.",
            ),
            (
                "4",
                "Treat retrieved text as untrusted",
                "Documents, tool output and other agents' replies all "
                "re-enter the prompt as text a model may obey.",
            ),
            (
                "5",
                "Measure per trace, not per month",
                "gen_ai.client.token.usage sliced by tag, release and "
                "tenant. An invoice is too late to be a control.",
            ),
        ),
        x=T.MARGIN_L,
        y=T.Y_BODY,
        w=T.COL_MAIN_W,
        step_h=1005840,
        accent=P.coral,
    )

    C.rail(
        slide,
        title="The sentence to remember",
        lines=(
            "An agent without a call budget is an unbounded loop "
            "holding a credit card.",
            "",
            "An agent without an approval gate is an unbounded loop "
            "holding a signature.",
            "",
            "This repository bounds both, in code you can read in one "
            "sitting.",
        ),
        accent=P.coral,
        h=5486400,
    )


def slide_close(prs: Presentation, facts: Facts) -> None:
    """Thank you, and the decision to take away."""
    slide = T.new_slide(prs)
    T.set_background(slide, "bg_closing.jpeg")
    T.add_logo(slide, dark=True, section=True)

    head = text_box(slide, x=T.MARGIN_L, y=2286000, w=12801600, h=1188720)
    write(head, plain("Thank you"), size=58, colour=P.on_dark, bold=True)

    line = text_box(slide, x=T.MARGIN_L, y=3474720, w=9601200, h=914400)
    write(
        line,
        plain(
            "Start with a job the user understands, then choose the "
            "smallest system that can deliver it."
        ),
        size=22,
        colour=P.on_dark_soft,
        line_spacing=1.3,
    )

    takeaways = (
        (
            "1",
            "Start from the job, not the brand.",
            "Name the user, steps and reviewable result.",
        ),
        (
            "2",
            "New agent code goes on Agent Framework.",
            "Use the lineage to plan existing-system migrations.",
        ),
        (
            "3",
            "Adopt identity, guardrails, traces and evaluation on day one.",
            "",
        ),
        (
            "4",
            "Check the lineage before you trust a sample.",
            "Confirm the package, endpoint and current API.",
        ),
    )
    for index, (number, title, detail) in enumerate(takeaways):
        top = 4663440 + index * 731520
        badge = T.rounded(
            slide,
            x=T.MARGIN_L,
            y=top,
            w=384048,
            h=384048,
            fill=P.teal,
            line=None,
            radius=50000,
        )
        badge.text_frame.vertical_anchor = MSO_ANCHOR.MIDDLE
        write(
            badge,
            plain(number),
            size=13,
            colour=P.on_dark,
            bold=True,
            align=PP_ALIGN.CENTER,
        )
        box = text_box(
            slide,
            x=T.MARGIN_L + 548640,
            y=top - 27432,
            w=9052560,
            h=640080,
        )
        write(
            box,
            [
                (f"{title}  ", {"bold": True, "colour": P.on_dark}),
                (detail, {"colour": "B9C8E6"}),
            ],
            size=15,
            colour=P.on_dark_soft,
        )

    panel = T.rounded(
        slide,
        x=11430000,
        y=2286000,
        w=5486400,
        h=5029200,
        fill=P.on_dark,
        line=None,
        alpha=10000,
    )
    panel.text_frame.text = ""

    label = text_box(slide, x=11887200, y=2697480, w=4572000, h=347472)
    write(
        label,
        plain("TAKE IT WITH YOU"),
        size=13,
        colour=P.on_dark_faint,
        bold=True,
    )

    rows = (
        ("REPOSITORY", "microsoft-ai-stack-workshop"),
        ("DECK", "microsoft_ai_stack.pptx"),
        ("RESEARCH", "docs/research.md"),
        ("RUN IT", "uv sync --frozen --group legacy"),
        ("", "uv run msai-demo doctor"),
        ("", "uv run msai-demo group-chat"),
    )
    for index, (key, value) in enumerate(rows):
        top = 3383280 + index * 594360
        if key:
            key_box = text_box(slide, x=11887200, y=top, w=4572000, h=274320)
            write(
                key_box,
                plain(key),
                size=11,
                colour=P.on_dark_faint,
                bold=True,
            )
        value_box = text_box(
            slide,
            x=11887200,
            y=top + (228600 if key else 0),
            w=4572000,
            h=320040,
        )
        write(
            value_box,
            plain(value),
            size=14,
            colour=P.on_dark,
            font=T.FONT_CODE,
        )

    who = text_box(slide, x=T.MARGIN_L, y=7772400, w=8229600, h=731520)
    write(who, plain(facts.author), size=19, colour=P.on_dark, bold=True)
    write(
        who,
        plain(facts.author_role),
        size=15,
        colour="B9C8E6",
        first=False,
    )

    stamp = text_box(slide, x=T.MARGIN_L, y=8686800, w=12801600, h=320040)
    write(
        stamp,
        plain(
            f"Executed {facts.deck_date} against agent-framework-core "
            f"{facts.af_version} and autogen-agentchat "
            f"{facts.autogen_version}. Every external claim verified "
            f"{facts.research_date}."
        ),
        size=12,
        colour="9FB2D8",
    )

    T.footer(slide, "dataart.com", dark=True)

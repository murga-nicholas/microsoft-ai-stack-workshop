"""Opening: concrete jobs, a timed agenda and the honesty claim."""

from __future__ import annotations

from typing import TYPE_CHECKING

import components as C
import research_facts as R
import theme as T
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from theme import P, plain, text_box, write

if TYPE_CHECKING:
    from facts import Facts
    from pptx.presentation import Presentation

SUBTITLE = "One runtime, one identity model, one control plane"


def slide_jobs(prs: Presentation, facts: Facts) -> None:
    """Start with four concrete jobs and their tool patterns."""
    del facts
    slide = T.content_slide(
        prs,
        eyebrow="use cases",
        title="Four jobs a junior can ship with this stack",
        deck="Start with a job, then choose a model, a tool and a human "
        "review step.",
        number=2,
    )
    C.screenshot(
        slide,
        str(T.ASSETS / "foundry_agent_catalog.jpg"),
        x=T.MARGIN_L,
        y=T.Y_BODY,
        w=7498080,
        h=2923680,
        caption="Microsoft Foundry agent catalog (Preview) - "
        f"{R.AGENT_CATALOG_COUNT} starter agents visible in this capture, "
        f"{R.CAPTURE_DATE}",
        callouts=((0.675, 0.45, "Internal Policy Q&A"),),
        legend_x=T.MARGIN_L,
        legend_y=6681240,
        legend_w=7498080,
    )
    path = text_box(slide, x=T.MARGIN_L, y=7047000, w=7498080, h=548640)
    write(
        path,
        plain(
            "Pick a starter agent -> inspect its tools and data -> "
            "configure access -> test."
        ),
        size=14,
        colour=P.muted,
    )
    label = text_box(slide, x=T.MARGIN_L, y=7705368, w=7498080, h=320040)
    write(
        label,
        plain("STARTER AGENTS ARE PATTERNS YOU ADAPT"),
        size=14,
        colour=P.faint,
        bold=True,
    )
    C.callout(
        slide,
        "Each job is a pattern: a model, instructions, one or two tools, "
        "and a human who reviews the draft.",
        x=T.MARGIN_L,
        y=8107704,
        w=7498080,
        accent=P.teal,
    )
    jobs = (
        (
            "Knowledge Base Q&A",
            "Answers from your documents with citations",
            f"Azure AI Search / Foundry IQ · slide "
            f"{T.number_of('slide_knowledge')}",
        ),
        (
            "Meeting Notes Summarizer",
            "Decisions and owners from a transcript",
            "Foundry prompt agent with File search",
        ),
        (
            "Log File Analyzer",
            "Clusters errors and builds a timeline",
            "Code interpreter in a Foundry agent",
        ),
        (
            "Test Case Generator",
            "Happy, edge and negative cases from a GitHub spec",
            f"GitHub MCP tool · slide {T.number_of('slide_mcp')}",
        ),
    )
    for index, (title, detail, tool) in enumerate(jobs):
        x, y, w = 9265920, T.Y_BODY + index * 1371600, 7498080
        T.card(slide, x=x, y=y, w=w, h=1188720)
        T.rounded(
            slide,
            x=x,
            y=y,
            w=54864,
            h=1188720,
            fill=(P.teal, P.blue, P.violet, P.coral)[index],
            line=None,
        )
        box = text_box(
            slide, x=x + 182880, y=y + 137160, w=w - 365760, h=960120
        )
        write(box, plain(title), size=16, colour=P.ink, bold=True)
        write(
            box,
            plain(detail),
            size=14,
            colour=P.muted,
            first=False,
            space_after=3,
        )
        write(box, plain(tool), size=14, colour=P.blue, first=False)
    C.run_strip(slide, "list")


def slide_agenda(prs: Presentation, facts: Facts) -> None:
    """Mirror the reference agenda bar, rows and command column."""
    del facts
    slide = T.content_slide(
        prs,
        eyebrow="agenda",
        title="The next sixty minutes, minute by minute",
        deck="Eight segments. The commands run on this laptop; the slides "
        "explain what you are watching.",
        number=3,
    )
    segments = (
        (0, 3, "Opening", "Four jobs this stack does", "list", P.coral),
        (
            3,
            11,
            "Lineage and Foundry",
            "What replaced what, and what Foundry contains",
            "doctor",
            P.blue,
        ),
        (
            11,
            18,
            "Legacy estate",
            "AutoGen, Semantic Kernel, Bot Framework, prompt flow",
            "autogen",
            P.amber,
        ),
        (
            18,
            30,
            "Agent Framework",
            "Agent, class family, workflow, harness, MCP, A2A, traces",
            "agent-framework",
            P.teal,
        ),
        (
            30,
            35,
            "AutoGen vs Agent Framework",
            "One approval gate, a restart, who owns what",
            "group-chat",
            P.violet,
        ),
        (
            35,
            52,
            "Microsoft Foundry",
            "Models, agents, Foundry Local, knowledge, safety, identity, "
            "evaluation",
            "foundry-models",
            P.blue,
        ),
        (
            52,
            55,
            "Choosing",
            "Reference architecture and the smallest sufficient solution",
            "-",
            P.coral,
        ),
        (55, 60, "Q&A", "Questions and discussion", "-", P.violet),
    )
    bar_labels = (
        "Open",
        "Lineage",
        "Legacy",
        "Agent Framework",
        "Compare",
        "Foundry",
        "Choosing",
        "Q&A",
    )
    for segment, short in zip(segments, bar_labels, strict=True):
        start, end, _, _, _, colour = segment
        x = T.MARGIN_L + int(T.CONTENT_W * start / 60)
        w = int(T.CONTENT_W * (end - start) / 60) - 45720
        T.rounded(
            slide,
            x=x,
            y=3054096,
            w=w,
            h=320040,
            fill=colour,
            line=None,
            radius=0,
        )
        box = text_box(
            slide, x=x, y=3054096, w=w, h=320040, anchor=MSO_ANCHOR.MIDDLE
        )
        write(
            box,
            plain(short),
            size=12 if short == "Choosing" else 14,
            colour=P.ink_soft if colour in {P.teal, P.amber} else P.on_dark,
            bold=True,
            align=PP_ALIGN.CENTER,
        )
    for label, x, align in (
        ("0 min", T.MARGIN_L, PP_ALIGN.LEFT),
        ("60 min", 15000000, PP_ALIGN.RIGHT),
    ):
        box = text_box(slide, x=x, y=3438144, w=1840000, h=274320)
        write(box, plain(label), size=12, colour=P.faint, align=align)
    columns = (2295144, 3657600, 7040880, 12100560)
    widths = (1097280, 3108960, 4754880, 4450080)
    for header, x, w in zip(
        ("WHEN", "SEGMENT", "WHAT YOU WILL SEE", "THE COMMAND I RUN"),
        columns,
        widths,
        strict=True,
    ):
        box = text_box(slide, x=x, y=3803904, w=w, h=274320)
        write(
            box,
            plain(header),
            size=12,
            colour=P.faint,
            bold=True,
            align=PP_ALIGN.RIGHT
            if header == "THE COMMAND I RUN"
            else PP_ALIGN.LEFT,
        )
    for index, (start, end, label, detail, command, colour) in enumerate(
        segments
    ):
        top, height = 4197096 + index * 548640, 502920
        T.card(slide, x=T.MARGIN_L, y=top, w=T.CONTENT_W, h=height)
        T.rounded(
            slide,
            x=T.MARGIN_L + 228600,
            y=top + 182880,
            w=274320,
            h=274320,
            fill=colour,
            line=None,
            radius=0,
        )
        values = (
            f"{start}-{end} min",
            label,
            detail,
            "-" if command == "-" else f"uv run msai-demo {command}",
        )
        for col, (value, x, w) in enumerate(
            zip(values, columns, widths, strict=True)
        ):
            box = text_box(
                slide, x=x, y=top, w=w, h=height, anchor=MSO_ANCHOR.MIDDLE
            )
            write(
                box,
                plain(value),
                size=14,
                colour=colour if col == 1 else P.body,
                bold=col == 1,
                font=T.FONT_CODE if col == 3 else T.FONT_UI,
                align=PP_ALIGN.RIGHT if col == 3 else PP_ALIGN.LEFT,
                line_spacing=1.05,
            )
    box = text_box(slide, x=T.MARGIN_L, y=8705088, w=T.CONTENT_W, h=548640)
    write(
        box,
        plain(
            "Every command runs offline on a laptop; each result states "
            "its mode, "
            "so nothing simulated passes as a cloud call."
        ),
        size=16,
        colour=P.coral,
        bold=True,
    )


def slide_title(prs: Presentation, facts: Facts) -> None:
    """Cover: who, what, and the promise the deck has to keep."""
    slide = T.new_slide(prs)
    T.set_background(slide, "bg_title.jpeg")
    T.add_logo(slide, dark=True)

    brow = text_box(slide, x=T.MARGIN_L, y=3127248, w=12801600, h=365760)
    write(
        brow,
        plain(f"MICROSOFT AI STACK   ·   {facts.deck_date}"),
        size=15,
        colour=P.yellow,
        bold=True,
    )

    head = text_box(slide, x=T.MARGIN_L, y=3639312, w=14081760, h=1325880)
    write(
        head,
        plain("Microsoft AI stack"),
        size=76,
        colour=P.on_dark,
        bold=True,
    )

    sub = text_box(slide, x=T.MARGIN_L, y=4992624, w=14081760, h=868680)
    write(sub, plain(SUBTITLE), size=40, colour=P.on_dark_soft)

    pills = (
        ("Agent Framework", P.teal),
        ("Microsoft Foundry", P.sky),
        ("Foundry Local", P.teal),
        ("Entra Agent ID", P.yellow),
        ("AutoGen - SK (legacy)", P.coral),
    )
    for index, (label, colour) in enumerate(pills):
        left = T.MARGIN_L + index * 2788920
        shape = T.rounded(
            slide,
            x=left,
            y=6144768,
            w=2651760,
            h=566928,
            fill=P.on_dark,
            line=colour,
            line_w=19050,
            radius=50000,
            alpha=14000,
        )
        shape.text_frame.vertical_anchor = MSO_ANCHOR.MIDDLE
        write(
            shape,
            plain(label),
            size=16,
            colour=P.on_dark,
            bold=True,
            align=PP_ALIGN.CENTER,
        )

    claim = text_box(slide, x=T.MARGIN_L, y=7132320, w=12984480, h=594360)
    write(
        claim,
        plain(
            "Commands demonstrate mechanisms and report their mode. "
            "Use-case bands describe illustrative applications."
        ),
        size=18,
        colour="BFCDE9",
    )

    who = text_box(slide, x=T.MARGIN_L, y=7936992, w=8229600, h=914400)
    write(who, plain(facts.author), size=21, colour=P.on_dark, bold=True)
    write(
        who,
        plain(facts.author_role),
        size=16,
        colour="B9C8E6",
        first=False,
    )

    T.footer(slide, "dataart.com", dark=True)

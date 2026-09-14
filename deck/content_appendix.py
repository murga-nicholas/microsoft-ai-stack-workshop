"""Appendix: the lab material a developer takes home.

The main talk stays on decisions and evidence. Everything a Python
developer needs to reproduce it - the project map, the readiness check,
the engineering gate, recorded transcripts and the references - lives
here, after the closing slide.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import components as C
import diagrams as D
import theme as T
from theme import P, plain, text_box, write

if TYPE_CHECKING:
    from facts import Facts
    from pptx.presentation import Presentation

CODE_W = 7635240
RIGHT_X = 9345168
RIGHT_W = 7498080

LEARN = "https://learn.microsoft.com/en-us"
AF = f"{LEARN}/agent-framework"
AZ = f"{LEARN}/azure"


def slide_section(prs: Presentation, facts: Facts) -> None:
    """Divider between the talk and the take-home lab material."""
    del facts
    T.section_slide(
        prs,
        index="A",
        eyebrow="appendix",
        title_lines=["Lab material", "to take home"],
        deck=(
            "Not presented. Everything a Python developer needs to "
            "reproduce the talk on their own laptop."
        ),
        bullets=(
            "Recorded transcripts and persisted approval",
            "Exact class MRO and compatibility constraints",
            "The stack map, platform choices and operations",
            "Repository, readiness and automated checks",
            "Official references, every one a link",
        ),
        number=0,
        accent=P.teal,
    )


SPEAKER_COLOURS = {
    "SolutionArchitect": P.coral,
    "RiskReviewer": P.violet,
}


def slide_transcripts(prs: Presentation, facts: Facts) -> None:
    """Both group-chat transcripts, exactly as recorded offline."""
    slide = T.content_slide(
        prs,
        eyebrow="appendix - transcripts",
        title="Both group-chat transcripts, as recorded",
        deck=(
            "Offline runs with scripted model clients. Long proposal "
            "JSON is cut for the slide; the full text is in facts.json."
        ),
        number=0,
        accent=P.teal,
    )
    C.run_strip(slide, "group-chat --format json")

    lanes = (
        ("autogen", "AutoGen", P.amber, T.MARGIN_L, CODE_W),
        (
            "group-chat-agent-framework",
            "Agent Framework",
            P.teal,
            RIGHT_X,
            RIGHT_W,
        ),
    )
    for key, name, colour, left, width in lanes:
        run = facts.demo_run(key)
        label = text_box(slide, x=left, y=T.Y_BODY, w=width, h=320040)
        write(
            label,
            plain(f"{name.upper()} - {len(run['turns'])} TURNS WITH TEXT"),
            size=12.5,
            colour=colour,
            bold=True,
        )
        top = T.Y_BODY + 411480
        for turn in run["turns"]:
            speaker = str(turn["speaker"])
            accent = SPEAKER_COLOURS.get(speaker, P.blue)
            C.card(slide, x=left, y=top, w=width, h=1051560)
            T.rounded(
                slide,
                x=left,
                y=top,
                w=68580,
                h=1051560,
                fill=accent,
                line=None,
                radius=0,
            )
            box = text_box(
                slide,
                x=left + 320040,
                y=top + 137160,
                w=width - 548640,
                h=822960,
            )
            write(
                box,
                plain(speaker),
                size=14,
                colour=accent,
                bold=True,
                font=T.FONT_CODE,
            )
            write(
                box,
                plain(_short(str(turn["text"]), 120)),
                size=14,
                colour=P.muted,
                line_spacing=1.15,
                first=False,
            )
            top += 1143000
        C.table(
            slide,
            ("Recorded", "Value"),
            (
                ("stop_reason", str(run["stop_reason"])),
                ("tool_calling", _short(str(run["tool_calling"]), 40)),
            ),
            x=left,
            y=T.Y_BODY + 2926080,
            w=width,
            widths=(1.4, 3.2),
            row_h=411480,
            size=14,
            mono_columns=(0,),
            accents=(colour, colour),
        )


def _ruff_families() -> int:
    """Count the Ruff rule families selected in pyproject.toml."""
    import tomllib
    from pathlib import Path

    pyproject = Path(__file__).resolve().parent.parent / "pyproject.toml"
    with pyproject.open("rb") as handle:
        config = tomllib.load(handle)
    return len(config["tool"]["ruff"]["lint"]["select"])


def _short(text: str, limit: int) -> str:
    """Trim recorded text to fit a card, marking the cut."""
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 3].rstrip() + "..."


def slide_repository(prs: Presentation, facts: Facts) -> None:
    """One repository, one command, twenty-four runnable stories."""
    slide = T.content_slide(
        prs,
        eyebrow="the demo",
        title="One repository. One command. Twenty-four technologies.",
        deck=(
            "Pinned with uv.lock, linted at 79 columns, strictly typed, "
            "and tested with no network at all."
        ),
        number=10,
    )

    T.code_panel(
        slide,
        x=T.MARGIN_L,
        y=T.Y_BODY,
        w=7635240,
        h=5413248,
    )
    D.panel_label(
        slide,
        "project map",
        x=T.MARGIN_L + 310896,
        y=T.Y_BODY + 182880,
        w=6995160,
    )
    tree = (
        ("data/microsoft_ai_stack_notes.md", "local grounding corpus"),
        ("src/msai_demo/", ""),
        ("  contracts.py", "the mode/status result envelope"),
        ("  scenario.py", "the shared business task"),
        ("  providers.py / offline.py", "live switch / scripted tokens"),
        ("  doctor.py", "readiness, never a secret"),
        ("  autogen_demo.py", "legacy lane"),
        ("  semantic_kernel_demo.py", "legacy lane"),
        ("  group_chat_demo.py", "the side-by-side comparison"),
        ("  agent_framework_demo.py", "agent, workflow, harness family"),
        ("  foundry_*.py", "five Microsoft Foundry services"),
        ("  azure_identity_demo.py", "real Entra tokens"),
        ("  resume_worker.py", "the separate resume process"),
        ("tests/", "offline, 100% statements and branches"),
        (".env.example", "every variable, documented"),
        ("uv.lock", "the authoritative dependency set"),
    )
    lines = [
        [
            (path.ljust(29), P.code_fg),
            (f"# {note}" if note else "", P.code_dim),
        ]
        for path, note in tree
    ]
    D.code_lines(
        slide,
        lines,
        x=T.MARGIN_L + 310896,
        y=T.Y_BODY + 548640,
        w=7013448,
        h=4645152,
        size=14,
    )

    commands = (
        (
            "uv sync --frozen --group legacy",
            "Recreate the exact pinned set.",
        ),
        (
            "uv run msai-demo list",
            "The table of contents for the workshop.",
        ),
        (
            "uv run msai-demo doctor",
            f"{facts.package_count} versions, credentials by name only.",
        ),
        (
            "uv run msai-demo group-chat",
            "Both lanes, one task, one comparison.",
        ),
        (
            "uv run msai-demo all --lane current",
            "Every current-lane technology in order.",
        ),
    )
    for index, (command, note) in enumerate(commands):
        top = T.Y_BODY + index * 960120
        box = text_box(slide, x=9345168, y=top, w=7498080, h=411480)
        write(
            box,
            plain(command),
            size=15,
            colour=P.ink_soft,
            bold=True,
            font=T.FONT_CODE,
        )
        note_box = text_box(
            slide,
            x=9345168,
            y=top + 365760,
            w=7498080,
            h=457200,
        )
        write(note_box, plain(note), size=14, colour=P.muted)

    C.callout(
        slide,
        "Telemetry is off unless you ask for it. That is what makes the "
        "live run believable.",
        x=9345168,
        y=T.Y_BODY + 4937760,
        w=7498080,
        accent=P.teal,
    )
    note = text_box(slide, x=T.MARGIN_L, y=8810000, w=T.CONTENT_W, h=320040)
    write(
        note,
        plain("Supplementary code excerpts in speaker notes"),
        size=14,
        colour=P.muted,
    )


def slide_readiness(prs: Presentation, facts: Facts) -> None:
    """Prove the room is ready before you talk."""
    slide = T.content_slide(
        prs,
        eyebrow="appendix - readiness",
        title="Check configuration before the workshop",
        deck=(
            "doctor reports installed versions and which credentials are "
            "present. It never prints a value, and it does not prove a "
            "credential is authorised - a live run does."
        ),
        number=11,
    )

    T.code_panel(slide, x=T.MARGIN_L, y=T.Y_BODY, w=7635240, h=3657600)
    D.panel_label(
        slide,
        "API excerpt  -  src/msai_demo/runtime.py",
        x=T.MARGIN_L + 310896,
        y=T.Y_BODY + 182880,
        w=6995160,
    )
    code = (
        [
            ("def ", P.sky),
            ("env_is_present", P.teal),
            ("(name: ", P.code_fg),
            ("str", P.sky),
            (") -> ", P.code_fg),
            ("bool", P.sky),
            (":", P.code_fg),
        ],
        [('    """Check a value is usable without logging it."""', P.yellow)],
        [
            ("    value = os.getenv(name, ", P.code_fg),
            ('""', P.yellow),
            (").strip()", P.code_fg),
        ],
        [("    normalized = value.casefold()", P.code_fg)],
        [
            ("    ", P.code_fg),
            ("if", P.sky),
            ("    not value or normalized in _PLACEHOLDERS:", P.code_fg),
        ],
        [("        ", P.code_fg), ("return", P.sky), (" False", P.code_fg)],
        [
            ("    ", P.code_fg),
            ("return", P.sky),
            (' "xxxxxxxx" not in normalized', P.code_fg),
        ],
        [],
        [("# doctor reports booleans. Never a value.", P.code_dim)],
        [('"OPENAI_API_KEY"', P.yellow), (": env_is_present(...)", P.code_fg)],
        [
            ('"AZURE_CLIENT_SECRET"', P.yellow),
            (": env_is_present(...)", P.code_fg),
        ],
    )
    D.code_lines(
        slide,
        [list(line) for line in code],
        x=T.MARGIN_L + 310896,
        y=T.Y_BODY + 548640,
        w=7013448,
        h=2926080,
        size=14,
    )

    label = text_box(
        slide,
        x=9345168,
        y=T.Y_BODY,
        w=7498080,
        h=320040,
    )
    write(
        label,
        plain("WHAT THE ROOM SEES"),
        size=11,
        colour=P.faint,
        bold=True,
    )

    live = sum(1 for ready in facts.demos.values() if ready)
    missing = sum(
        not facts.credentials.get(name)
        for name in (
            "OPENAI_API_KEY",
            "ANTHROPIC_API_KEY",
            "AZURE_CLIENT_SECRET",
        )
    )
    total = len(facts.demos) or 1
    rows = (
        ("Python", facts.packages.get("python", "3.12.x")),
        ("agent-framework-core", facts.af_version),
        ("autogen-agentchat", facts.autogen_version),
        (
            "semantic-kernel",
            facts.packages.get("semantic-kernel", "not installed"),
        ),
        ("azure-ai-projects", facts.packages.get("azure-ai-projects", "-")),
        (
            "OPENAI_API_KEY",
            "present"
            if facts.credentials.get("OPENAI_API_KEY")
            else "missing",
        ),
        (
            "ANTHROPIC_API_KEY",
            "present"
            if facts.credentials.get("ANTHROPIC_API_KEY")
            else "missing",
        ),
        (
            "AZURE_CLIENT_SECRET",
            "present"
            if facts.credentials.get("AZURE_CLIENT_SECRET")
            else "missing",
        ),
        ("Demos with a live path", f"{live} of {total}"),
        ("Demos that run offline", "all of them"),
    )
    C.table(
        slide,
        ("Check", "Status"),
        rows,
        x=9345168,
        y=T.Y_BODY + 365760,
        w=7498080,
        widths=(2.6, 1.4),
        row_h=365760,
        size=14,
        mono_columns=(0,),
    )

    C.callout(
        slide,
        f"{missing} of 3 credential rows "
        f"{'says' if missing == 1 else 'say'} missing, and that is "
        "fine. Every demo still runs - it tells you which path it took.",
        x=T.MARGIN_L,
        y=T.Y_BODY + 4114800,
        w=7635240,
        accent=P.teal,
    )
    C.source_note(
        slide,
        "Captured from this machine at deck build time by "
        "msai_demo.doctor.collect_readiness().",
    )


def slide_standard(prs: Presentation, facts: Facts) -> None:
    """The executable quality gate."""
    slide = T.content_slide(
        prs,
        eyebrow="appendix - engineering standard",
        title="Automated checks for the workshop code",
        deck=(
            "Style expectations are worthless as a wiki page and "
            "priceless as a command that fails the build."
        ),
        number=41,
        accent=P.teal,
    )

    T.code_panel(slide, x=T.MARGIN_L, y=T.Y_BODY, w=7635240, h=2377440)
    D.panel_label(
        slide,
        "the gate - all five, green, before anything is shown",
        x=T.MARGIN_L + 310896,
        y=T.Y_BODY + 182880,
        w=6995160,
    )
    D.code_lines(
        slide,
        [
            [("uv run ruff format --check src/ tests/ deck/", P.code_fg)],
            [("uv run ruff check src/ tests/ deck/", P.code_fg)],
            [("uv run mypy", P.code_fg)],
            [
                (
                    "uv run pytest --cov=msai_demo --cov-report=term-missing",
                    P.code_fg,
                )
            ],
            [("uv lock --check", P.code_fg)],
        ],
        x=T.MARGIN_L + 310896,
        y=T.Y_BODY + 594360,
        w=7013448,
        h=1737360,
        size=15,
    )

    C.metrics(
        slide,
        (
            (
                "79",
                "column limit",
                f"PEP 8 and Google's ceiling, {_ruff_families()} Ruff "
                "rule families",
            ),
            ("strict", "mypy, every module", "Any confined to SDK boundaries"),
            (
                "100%",
                "statements and branches",
                "fail_under = 100 in pyproject",
            ),
        ),
        x=T.MARGIN_L,
        y=T.Y_BODY + 2651760,
        w=7635240,
        gap=137160,
        accent=P.teal,
    )

    C.table(
        slide,
        ("Habit a reviewer can see", "How it is enforced"),
        (
            (
                "No credential is ever printed",
                "doctor returns booleans; .env is git-ignored",
            ),
            (
                "Telemetry is off by default",
                "configure_telemetry() runs before any client is built",
            ),
            (
                "Every claim carries a mode",
                "contracts.result() raises on dishonest evidence",
            ),
            (
                "Tests never touch the network",
                "first-party scripted clients and injected ports",
            ),
            (
                "One lockfile, one truth",
                "uv.lock and pyproject move in the same commit",
            ),
            (
                "Quoted figures come from runs",
                "facts.json is captured from the demos before a build",
            ),
        ),
        x=RIGHT_X,
        y=T.Y_BODY,
        w=RIGHT_W,
        widths=(2.6, 3.4),
        row_h=502920,
        size=14,
    )

    C.source_note(
        slide,
        f"Installed at build time: agent-framework-core "
        f"{facts.af_version}, autogen-agentchat {facts.autogen_version}. "
        f"Run uv run msai-demo doctor --packages for the full list.",
    )


def slide_references(prs: Presentation, facts: Facts) -> None:
    """Official links for the products, APIs and migration paths."""
    del facts
    slide = T.content_slide(
        prs,
        eyebrow="references",
        title="Learn it from the source, not from a blog post",
        deck=(
            "Official documentation for the products, APIs and migration "
            "paths. Each title below is a clickable link. Capture dates "
            "and recorded modes stay next to the evidence."
        ),
        number=44,
    )

    groups = (
        (
            "Agent Framework and SDKs",
            P.teal,
            (
                (
                    "Overview: agents and workflows",
                    f"{AF}/overview/agent-framework-overview",
                ),
                (
                    "Group chat orchestration",
                    f"{AF}/workflows/orchestrations/group-chat",
                ),
                ("Harness agent", f"{AF}/concepts/harness"),
                ("Observability", f"{AF}/agents/observability"),
                ("MCP tools", f"{AF}/agents/tools/local-mcp-tools"),
                (
                    "A2A agents",
                    f"{AF}/integrations/by-component/agent-services/a2a",
                ),
                (
                    "Migrating from AutoGen",
                    f"{AF}/migration-guide/from-autogen/",
                ),
                (
                    "Migrating from Semantic Kernel",
                    f"{AF}/migration-guide/from-semantic-kernel/",
                ),
                (
                    "Python 2026 significant changes",
                    f"{AF}/support/upgrade/python-2026-significant-changes",
                ),
                (
                    "Agent Framework 1.0 announcement",
                    "https://devblogs.microsoft.com/agent-framework/"
                    "microsoft-agent-framework-version-1-0/",
                ),
            ),
        ),
        (
            "Foundry platform and services",
            P.sky,
            (
                ("What is Microsoft Foundry", f"{AZ}/foundry/what-is-foundry"),
                (
                    "Foundry architecture",
                    f"{AZ}/foundry/concepts/architecture",
                ),
                (
                    "Product and capability map",
                    f"{AZ}/foundry/concepts/capabilities",
                ),
                (
                    "Migrate from Foundry (classic)",
                    f"{AZ}/foundry/how-to/navigate-from-classic",
                ),
                (
                    "Foundry GA overview",
                    f"{AZ}/foundry/concepts/general-availability",
                ),
                ("Foundry Agent Service", f"{AZ}/foundry/agents/overview"),
                (
                    "Guardrails and controls",
                    f"{AZ}/foundry/guardrails/guardrails-overview",
                ),
                (
                    "Foundry IQ",
                    f"{AZ}/foundry/agents/concepts/what-is-foundry-iq",
                ),
                (
                    "Foundry Local architecture",
                    f"{AZ}/foundry-local/concepts/foundry-local-architecture",
                ),
                ("Foundry Local", f"{AZ}/foundry-local/what-is-foundry-local"),
                (
                    "Ollama OpenAI compatibility",
                    "https://docs.ollama.com/api/openai-compatibility",
                ),
            ),
        ),
        (
            "Identity, retrieval and migration",
            P.amber,
            (
                (
                    "Bot Framework to M365 Agents SDK",
                    f"{LEARN}/microsoft-365/agents-sdk/bf-migration-python",
                ),
                (
                    "Microsoft Entra Agent ID",
                    f"{LEARN}/entra/agent-id/what-is-microsoft-entra-agent-id",
                ),
                (
                    "Autonomous agent tokens",
                    f"{LEARN}/entra/agent-id/"
                    "autonomous-agent-authentication-authorization-flow",
                ),
                (
                    "AI Search document-level access",
                    f"{AZ}/search/search-document-level-access-overview",
                ),
                (
                    "Azure AI Search news and rebrands",
                    f"{AZ}/search/whats-new",
                ),
                (
                    "prompt flow migration",
                    f"{AZ}/foundry-classic/how-to/"
                    "prompt-flow-migration-overview",
                ),
                (
                    "Content Moderator retirement",
                    f"{AZ}/ai-services/content-moderator/overview",
                ),
                ("PyPI JSON API", "https://docs.pypi.org/api/json/"),
            ),
        ),
    )

    gap = 274320
    column = (T.CONTENT_W - gap * 2) // 3
    for index, (title, colour, items) in enumerate(groups):
        left = T.MARGIN_L + index * (column + gap)
        C.card(slide, x=left, y=T.Y_BODY, w=column, h=5029200)
        T.rounded(
            slide,
            x=left,
            y=T.Y_BODY,
            w=column,
            h=68580,
            fill=colour,
            line=None,
            radius=0,
        )
        head = text_box(
            slide,
            x=left + 320040,
            y=T.Y_BODY + 274320,
            w=column - 640080,
            h=411480,
        )
        write(head, plain(title), size=16, colour=P.ink, bold=True)

        body = text_box(
            slide,
            x=left + 320040,
            y=T.Y_BODY + 777240,
            w=column - 640080,
            h=3931920,
        )
        for item_index, (label, url) in enumerate(items):
            write(
                body,
                [(label, {"link": url})],
                size=14,
                colour=P.blue,
                line_spacing=1.2,
                space_after=6,
                first=item_index == 0,
            )

    C.callout(
        slide,
        "Run figures: deck/facts.json through deck/facts.py. "
        "Dated research facts and source URLs: deck/research_facts.py.",
        x=T.MARGIN_L,
        y=T.Y_BODY + 5212080,
        w=T.CONTENT_W,
        accent=P.teal,
        size=15,
    )

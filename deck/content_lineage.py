"""Framework and service lineage, then the Foundry resource model."""

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


def _text(
    slide: Slide,
    text: str,
    x: int,
    y: int,
    w: int,
    h: int,
    *,
    size: float = 15,
    bold: bool = False,
    colour: str = P.body,
) -> None:
    """Place a measured text region using the shared theme."""
    box = text_box(slide, x=x, y=y, w=w, h=h)
    write(box, plain(text), size=size, colour=colour, bold=bold)


def slide_section(prs: Presentation, facts: Facts) -> None:
    """Introduce the evolution and governance boundaries."""
    del facts
    T.section_slide(
        prs,
        index="01",
        eyebrow="lineage",
        title_lines=["Where today's", "names came from"],
        deck="Read the lineage before you copy a sample or open a resource.",
        bullets=[
            "Frameworks and SDKs",
            "Azure services",
            "The portal today",
            "Inside Foundry",
        ],
        number=4,
    )


def slide_framework_lineage(prs: Presentation, facts: Facts) -> None:
    """Separate replacements, SDK migration and API migration."""
    del facts
    slide = T.content_slide(
        prs,
        eyebrow="lineage / frameworks and SDKs",
        title="AutoGen and Semantic Kernel became one framework",
        deck="A successor carries ideas forward; a migration still changes "
        "your code.",
        number=5,
    )
    D.lineage(
        slide,
        [
            (
                [
                    D.LineageNode(
                        "AutoGen / Microsoft Research",
                        R.FRAMEWORK_ORIGINS_YEAR,
                    ),
                    D.LineageNode("Semantic Kernel", R.FRAMEWORK_ORIGINS_YEAR),
                ],
                "successor",
                ["Microsoft Agent Framework"],
                f"Preview {R.AGENT_FRAMEWORK_PREVIEW}; GA "
                f"{R.AGENT_FRAMEWORK_GA}. "
                f"AutoGen last release {R.AUTOGEN_LAST_RELEASE}; SK "
                f"{R.SEMANTIC_KERNEL_STATUS}.",
            ),
            (
                ["Bot Framework SDK"],
                "migration",
                ["Microsoft 365 Agents SDK"],
                f"Bot Framework LTS ended {R.BOT_FRAMEWORK_LTS_ENDED}",
            ),
            (
                ["prompt flow"],
                "migration",
                ["Agent Framework workflows", "azure-ai-evaluation"],
                f"prompt flow retires {R.PROMPT_FLOW_RETIREMENT}",
            ),
            (
                ["azure-ai-inference"],
                "migration",
                ["openai package"],
                f"Retired {R.INFERENCE_RETIRED}",
            ),
            (
                ["AzureOpenAI()"],
                "migration",
                ["OpenAI(base_url=…/openai/v1)"],
                "v1 routes, no api-version",
            ),
            (
                ["azure-ai-generative"],
                "merged into",
                ["azure-ai-projects 2.x"],
                "One project client",
            ),
            (
                ["Assistants API (threads, runs)"],
                "migration",
                ["Responses API / Agents v2"],
                f"Sunset {R.ASSISTANTS_SUNSET}",
            ),
        ],
        x=T.MARGIN_L,
        y=T.Y_BODY,
        w=T.CONTENT_W,
    )
    C.source_note(
        slide,
        "Sources: Microsoft Learn: What is Microsoft Foundry; Migrate from "
        "Foundry "
        "(classic); prompt flow migration overview; Agent Framework overview.",
    )
    C.run_strip(slide, "doctor")


def slide_service_lineage(prs: Presentation, facts: Facts) -> None:
    """Separate service renames, composition and identity extension."""
    del facts
    slide = T.content_slide(
        prs,
        eyebrow="lineage / Azure services",
        title="The Azure services were renamed, merged and built upon",
        deck="Product names changed faster than Azure resource types. "
        "Dashed arrows mean a relationship.",
        number=6,
    )
    node, chain = D.LineageNode, D.LineageChain
    D.lineage(
        slide,
        [
            (
                chain(
                    (
                        node("Azure AI Studio", R.AI_STUDIO_YEAR),
                        node("Azure AI Foundry", R.AI_FOUNDRY_YEAR),
                    )
                ),
                "rename",
                ["Microsoft Foundry"],
                R.FOUNDRY_RENAME,
            ),
            (
                chain(
                    (
                        node("Azure Cognitive Services"),
                        node("Azure AI Services"),
                    )
                ),
                "rename",
                ["Foundry Tools"],
                "Resource type remains Microsoft.CognitiveServices/accounts",
            ),
            (
                ["Hub", "Azure OpenAI", "AI Services"],
                "merged into",
                ["Foundry resource with projects"],
                "Hub projects stay in Foundry (classic)",
            ),
            (
                chain(
                    (
                        node("Azure Search", R.AZURE_SEARCH_LAUNCH),
                        node(
                            "Azure Cognitive Search", R.COGNITIVE_SEARCH_RENAME
                        ),
                    )
                ),
                "rename",
                chain(
                    (
                        node("Azure AI Search", R.AI_SEARCH_RENAME),
                        node("Foundry IQ", R.FOUNDRY_IQ_PREVIEW),
                    ),
                    "built on",
                ),
                f"Foundry IQ is built on AI Search. {R.FOUNDRY_IQ_STATUS}.",
            ),
            (
                ["Content Moderator"],
                "successor",
                chain(
                    (
                        node("Azure AI Content Safety"),
                        node("Foundry guardrails"),
                    ),
                    "used by",
                ),
                f"Moderator deprecated {R.CONTENT_MODERATOR_DEPRECATED}; "
                f"retires {R.CONTENT_MODERATOR_RETIRES}. Guardrails use "
                f"its classifiers.",
            ),
            (
                ["Microsoft Entra ID"],
                "extends",
                ["Microsoft Entra Agent ID"],
                "Agent identities and blueprints",
            ),
            (
                ["Foundry portal Workflows (preview)"],
                "migration",
                ["Agent Framework workflows"],
                f"Portal Workflows retire {R.FOUNDRY_WORKFLOWS_RETIREMENT}",
            ),
        ],
        x=T.MARGIN_L,
        y=T.Y_BODY,
        w=T.CONTENT_W,
    )
    C.source_note(
        slide,
        "Sources: Microsoft Learn: Foundry classic migration; Azure AI Search "
        "what's new; Content Moderator retirement; Entra Agent ID; Foundry "
        "GA overview.",
    )
    C.run_strip(slide, "doctor")


def slide_portal(prs: Presentation, facts: Facts) -> None:
    """Connect visible portal labels to the management task."""
    del facts
    slide = T.content_slide(
        prs,
        eyebrow="lineage / the portal today",
        title="The Azure portal shows old and new side by side",
        deck="Current and classic services coexist. The menu groups Azure "
        "OpenAI and AI Search with Foundry.",
        number=7,
    )
    left_w, right_x = 7498080, 9265920
    C.screenshot(
        slide,
        str(T.ASSETS / "azure_ai_services.jpg"),
        x=T.MARGIN_L,
        y=T.Y_BODY,
        w=left_w,
        h=3773482,
        caption=f"All services > AI + Machine Learning, {R.CAPTURE_DATE}",
        callouts=(
            (0.235, 0.43, "AI Search (Foundry IQ)"),
            (0.235, 0.817, "Microsoft Foundry"),
            (0.59, 0.817, "Azure OpenAI"),
            (0.59, 0.496, "Bot Services"),
        ),
        legend_x=T.MARGIN_L,
        legend_y=7248144,
        legend_w=left_w,
        legend_columns=2,
    )
    C.screenshot(
        slide,
        str(T.ASSETS / "azure_foundry_hub.jpg"),
        x=right_x,
        y=T.Y_BODY,
        w=7498080,
        h=2927822,
        caption="Microsoft Foundry blade",
        callouts=(
            (
                0.015,
                0.34,
                "Use with Foundry: Foundry, AI Hubs, Azure OpenAI, AI Search",
            ),
            (0.015, 0.61, "More services: Content safety, Language, Speech…"),
        ),
        legend_x=right_x,
        legend_y=6446520,
        legend_w=7498080,
    )
    _text(
        slide,
        "Further down the menu, QnA maker, Language understanding and "
        "Content moderator carry '(classic)' labels.",
        right_x,
        7382250,
        7498080,
        457200,
        size=14,
    )
    # Compact, full-width band leaves both textual legends readable.
    C.use_case(
        slide,
        who="Junior engineer must find an existing AI resource",
        steps=[
            "All services",
            "Microsoft Foundry",
            "All resources",
            "Open the project",
        ],
        result="the right management page, not a guess.",
        x=T.MARGIN_L,
        y=7900000,
        w=T.CONTENT_W,
        accent=P.teal,
    )
    C.run_strip(slide, "doctor")


def slide_foundry_architecture(prs: Presentation, facts: Facts) -> None:
    """Show resource, project and connected-resource scopes."""
    del facts
    slide = T.content_slide(
        prs,
        eyebrow="lineage / inside Foundry",
        title="Inside Microsoft Foundry: one resource, many projects",
        deck="The resource governs shared services; projects isolate each "
        "team's agents, files and evaluations.",
        number=8,
    )
    x, y, main_w = T.MARGIN_L, T.Y_BODY, 11521440
    T.rounded(slide, x=x, y=y, w=main_w, h=502920, fill=P.wash, line=P.rule)
    _text(
        slide,
        "SURFACES   Foundry portal ai.azure.com   ·   SDKs: "
        "azure-ai-projects + openai   ·   azd   ·   VS Code   ·   MCP",
        x + 91440,
        y + 91440,
        main_w - 182880,
        365760,
        size=15,
    )
    T.line(
        slide, x=x + main_w // 2, y=y + 502920, w=0, h=274320, colour=P.blue
    )
    top = y + 777240
    T.rounded(slide, x=x, y=top, w=main_w, h=2697480, fill=P.wash, line=P.blue)
    _text(
        slide,
        "FOUNDRY RESOURCE / GOVERNANCE BOUNDARY",
        x + 182880,
        top + 91440,
        main_w - 365760,
        320040,
        size=15,
        bold=True,
        colour=P.blue,
    )
    _text(
        slide,
        "Microsoft.CognitiveServices/accounts, kind AIServices",
        x + 182880,
        top + 411480,
        main_w - 365760,
        365760,
        size=15,
    )
    for index, label in enumerate(
        (
            "Model deployments",
            "Security: networking, keys, RBAC",
            "Connections",
        )
    ):
        left = x + 182880 + index * 3718560
        T.card(slide, x=left, y=top + 914400, w=3535680, h=594360)
        _text(
            slide,
            label,
            left + 91440,
            top + 1005840,
            3352800,
            411480,
            size=15,
            bold=True,
        )
    for index, label in enumerate(("Project A", "Project B")):
        left = x + 182880 + index * 5577840
        T.rounded(
            slide,
            x=left,
            y=top + 1737360,
            w=5394960,
            h=777240,
            fill=P.card,
            line=P.teal,
        )
        _text(
            slide,
            label,
            left + 182880,
            top + 1805940,
            5029200,
            320040,
            size=16,
            bold=True,
        )
        _text(
            slide,
            "Agents   ·   files   ·   evaluations",
            left + 182880,
            top + 2171700,
            5029200,
            320040,
            size=15,
        )
    ext_top = top + 3246120
    _text(
        slide,
        "OWN GOVERNANCE / REFERENCED THROUGH CONNECTIONS",
        x,
        ext_top - 457200,
        main_w,
        320040,
        size=14,
        colour=P.muted,
    )
    for index, label in enumerate(
        ("Azure Storage", "Key Vault", "Azure AI Search")
    ):
        left = x + index * 3840480
        T.line(
            slide,
            x=left + 1828800,
            y=ext_top - 137160,
            w=0,
            h=137160,
            colour=P.faint,
            dashed=True,
        )
        T.rounded(
            slide,
            x=left,
            y=ext_top,
            w=3657600,
            h=548640,
            fill=P.card,
            line=P.faint,
        )
        _text(
            slide,
            label,
            left + 182880,
            ext_top + 91440,
            3291840,
            365760,
            size=15,
            bold=True,
        )
    C.rail(
        slide,
        title="WHAT YOU BUILD",
        y=y,
        h=4663440,
        lines=[
            "Prompt agents and hosted agents",
            "Models",
            "Tools and knowledge: Toolbox, Foundry IQ, memory (preview)",
            "Evaluations and tracing",
            "Guardrails",
        ],
    )
    C.use_case(
        slide,
        who="Platform engineer supports an HR team",
        steps=[
            "Create a Foundry resource",
            "Create an HR project",
            "Deploy model + connect knowledge",
            "Assign Foundry User roles",
        ],
        result="a governed workspace for the HR assistant.",
        x=x,
        y=7880000,
        w=T.CONTENT_W,
        accent=P.teal,
    )
    slide.notes_slide.notes_text_frame.text = (
        "Source: https://learn.microsoft.com/en-us/azure/foundry/concepts/"
        "architecture "
        f"(updated {R.FOUNDRY_ARCHITECTURE_UPDATED})."
    )
    C.run_strip(slide, "azure-ai-projects")

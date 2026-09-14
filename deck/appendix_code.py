"""Attach exact repository excerpts to the take-home appendix notes."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import theme as T

if TYPE_CHECKING:
    from pptx.presentation import Presentation

SOURCE_ROOT = Path(__file__).resolve().parent.parent / "src" / "msai_demo"


def _snippet(filename: str, start: str, end: str) -> str:
    """Read an exact source slice and validate its anchors."""
    source = (SOURCE_ROOT / filename).read_text(encoding="utf-8")
    try:
        first = source.index(start)
        last = source.index(end, first)
    except ValueError as exc:
        message = f"Appendix excerpt anchors changed in {filename}"
        raise ValueError(message) from exc
    line = source.count("\n", 0, first) + 1
    return f"src/msai_demo/{filename}:{line}\n" + source[first:last].rstrip()


def attach_code_notes(prs: Presentation) -> None:
    """Keep supplementary code in the repository appendix notes."""
    excerpts = (
        (
            "1. AutoGen: construct a team and persist its SDK state",
            (
                _snippet(
                    "autogen_demo.py",
                    "    architect = AssistantAgent(",
                    "\n\n\ndef offline_script",
                ),
                _snippet(
                    "autogen_demo.py",
                    "async def save_team_state(",
                    "\n\n\ndef save_pending_approval",
                ),
            ),
        ),
        (
            "2. Semantic Kernel: register a native plugin and filter",
            (
                _snippet(
                    "semantic_kernel_demo.py",
                    "        class PilotPlugin:",
                    "\n    async def _audit_invocation",
                ),
            ),
        ),
        (
            "3. Channel handling: invoke the shared handler locally",
            (
                _snippet(
                    "bot_framework_demo.py",
                    "        context = LocalTurnContext(activity=activity)",
                    "        return {",
                ),
            ),
        ),
        (
            "4. Harness: compose the agent and its persistent file stores",
            (
                _snippet(
                    "harness_demo.py",
                    "        todo_provider = TodoProvider()",
                    '        self.record["sdk_invoked"] = True',
                ),
            ),
        ),
        (
            "5. SDK clients: project resources and the Foundry provider",
            (
                _snippet(
                    "azure_ai_projects_demo.py",
                    "    with AIProjectClient(",
                    "\n\n\nclass LiveProjectsPort",
                ),
                _snippet(
                    "providers.py",
                    '    if config.name == "foundry":',
                    "    return _create_foundry_local_client",
                ),
            ),
        ),
    )
    body = [
        "SUPPLEMENTARY CODE EXCERPTS",
        "Exact source slices, read from the repository at deck build time. "
        "They are take-home references; surrounding setup and imports remain "
        "in each source module. These notes contain code, "
        "not execution results.",
    ]
    for heading, snippets in excerpts:
        body.extend((heading, *snippets))
    slide = prs.slides[T.number_of("slide_repository") - 1]
    frame = slide.notes_slide.notes_text_frame
    if frame is None:
        message = "The repository appendix has no notes text frame"
        raise ValueError(message)
    existing = frame.text.strip()
    appendix = "\n\n".join(body)
    frame.text = f"{existing}\n\n{appendix}" if existing else appendix

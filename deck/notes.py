"""Load presenter scripts and preserve supplementary slide notes."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

    from pptx.slide import Slide

_MARKER = re.compile(
    r"^[^\S\n]*<!-- slide: "
    r"([A-Za-z_]\w*(?:\.[A-Za-z_]\w*)+) -->[^\S\n]*$",
    re.MULTILINE,
)


def load_notes(path: Path) -> dict[str, str]:
    """Parse slide sections and convert their bodies to presenter text.

    Args:
        path: Markdown script containing slide markers.

    Returns:
        Plain presenter text keyed by module and function name.

    Raises:
        FileNotFoundError: If the script file is missing.
        ValueError: If a key repeats or a section has no presenter text.
    """
    source = path.read_text(encoding="utf-8")
    markers = list(_MARKER.finditer(source))
    notes: dict[str, str] = {}
    for index, marker in enumerate(markers):
        key = marker.group(1)
        if key in notes:
            message = f"duplicate notes section: {key}"
            raise ValueError(message)
        end = (
            markers[index + 1].start()
            if index + 1 < len(markers)
            else len(source)
        )
        body = source[marker.end() : end]
        body = re.sub(r"(?m)^[ \t]*#{1,3}(?:[ \t]+|$)", "", body)
        body = body.replace("**", "")
        body = re.sub(r"\n(?:[^\S\n]*\n){3,}", "\n\n", body).strip()
        if not body:
            message = f"empty notes section: {key}"
            raise ValueError(message)
        notes[key] = body
    return notes


def attach_notes(slide: Slide, script: str) -> None:
    """Prepend a presenter script to any existing slide notes.

    Args:
        slide: Slide receiving the presenter script.
        script: Plain presenter text to place before existing notes.

    Raises:
        ValueError: If the slide has no notes text frame.
    """
    frame = slide.notes_slide.notes_text_frame
    if frame is None:
        message = "slide has no notes text frame"
        raise ValueError(message)
    existing = frame.text
    frame.text = f"{script}\n\n{existing}" if existing else script

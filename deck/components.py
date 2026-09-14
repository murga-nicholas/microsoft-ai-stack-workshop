"""Reusable slide components built on the theme primitives.

These are the half-dozen shapes the reference deck repeats: a row of
big numbers, a table, a stack of numbered steps, a two-column
comparison, a timeline, and the dark "read this" rail. Forty slides
stay consistent because they are all assembled from these.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from theme import (
    COL_RAIL_W,
    COL_RAIL_X,
    FONT_CODE,
    Y_BODY,
    P,
    card,
    dark_panel,
    plain,
    rounded,
    text_box,
    write,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from pptx.slide import Slide


def metrics(
    slide: Slide,
    items: Sequence[tuple[str, str, str]],
    *,
    x: int,
    y: int,
    w: int,
    gap: int = 228600,
    accent: str = P.coral,
) -> None:
    """A row of big numbers, each with a label and a footnote.

    Args:
        slide: Target slide.
        items: ``(value, label, footnote)`` per column.
        x: Left edge of the row.
        y: Top edge.
        w: Total width the row occupies.
        gap: Space between columns.
        accent: Colour for the big number.
    """
    count = len(items)
    column = (w - gap * (count - 1)) // count
    for index, (value, label, note) in enumerate(items):
        left = x + index * (column + gap)
        box = card(slide, x=left, y=y, w=column, h=2011680)
        del box
        head = text_box(
            slide,
            x=left + 274320,
            y=y + 228600,
            w=column - 548640,
            h=640080,
        )
        write(head, plain(value), size=44, colour=accent, bold=True)
        body = text_box(
            slide,
            x=left + 274320,
            y=y + 868680,
            w=column - 548640,
            h=1005840,
        )
        write(body, plain(label), size=16, colour=P.ink_soft, bold=True)
        write(
            body,
            plain(note),
            size=14,
            colour=P.muted,
            line_spacing=1.2,
            first=False,
        )


def table(
    slide: Slide,
    headers: Sequence[str],
    rows: Sequence[Sequence[str]],
    *,
    x: int,
    y: int,
    w: int,
    widths: Sequence[float],
    row_h: int = 457200,
    size: float = 14.5,
    accents: Sequence[str] | None = None,
    mono_columns: Sequence[int] = (),
) -> int:
    """Draw a light table with a ruled header.

    Args:
        slide: Target slide.
        headers: Column headings.
        rows: Row cells, already stringified.
        x: Left edge.
        y: Top edge.
        w: Total width.
        widths: Relative column widths; they are normalised.
        row_h: Height of a body row.
        size: Body point size.
        accents: Optional per-row colour for the first cell.
        mono_columns: Column indexes drawn in Consolas.

    Returns:
        The y coordinate just below the table.
    """
    total = sum(widths)
    offsets: list[int] = []
    running = x
    for share in widths:
        offsets.append(running)
        running += int(w * share / total)

    header_h = 365760
    for index, title in enumerate(headers):
        width = int(w * widths[index] / total) - 91440
        box = text_box(slide, x=offsets[index], y=y, w=width, h=header_h)
        write(
            box,
            plain(title.upper()),
            size=12.5,
            colour=P.faint,
            bold=True,
        )

    rule(slide, x=x, y=y + header_h, w=w)

    for row_index, cells in enumerate(rows):
        top = y + header_h + 45720 + row_index * row_h
        for col_index, cell in enumerate(cells):
            width = int(w * widths[col_index] / total) - 91440
            box = text_box(
                slide,
                x=offsets[col_index],
                y=top,
                w=width,
                h=row_h,
                anchor=MSO_ANCHOR.MIDDLE,
            )
            colour = P.body
            bold = False
            if col_index == 0:
                bold = True
                colour = (
                    accents[row_index] if accents is not None else P.ink_soft
                )
            write(
                box,
                plain(cell),
                size=size,
                colour=colour,
                bold=bold,
                font=FONT_CODE if col_index in mono_columns else "Arial",
                line_spacing=1.15,
            )
        if row_index < len(rows) - 1:
            rule(slide, x=x, y=top + row_h - 45720, w=w, colour=P.rule)

    return y + header_h + 45720 + len(rows) * row_h


def rule(
    slide: Slide,
    *,
    x: int,
    y: int,
    w: int,
    colour: str = P.rule,
) -> None:
    """Draw a one-pixel horizontal hairline."""
    shape = rounded(
        slide,
        x=x,
        y=y,
        w=w,
        h=12700,
        fill=colour,
        line=None,
        radius=0,
    )
    shape.text_frame.word_wrap = False


def steps(
    slide: Slide,
    items: Sequence[tuple[str, str, str]],
    *,
    x: int,
    y: int,
    w: int,
    accent: str = P.coral,
    step_h: int = 1005840,
) -> None:
    """A numbered vertical list of short decisions.

    Args:
        slide: Target slide.
        items: ``(number, title, detail)`` per step.
        x: Left edge.
        y: Top edge.
        w: Width.
        accent: Colour of the step number.
        step_h: Vertical pitch between steps.
    """
    for index, (number, title, detail) in enumerate(items):
        top = y + index * step_h
        badge = rounded(
            slide,
            x=x,
            y=top,
            w=457200,
            h=457200,
            fill=accent,
            line=None,
            radius=50000,
        )
        badge.text_frame.vertical_anchor = MSO_ANCHOR.MIDDLE
        write(
            badge,
            plain(number),
            size=15,
            colour=P.on_dark,
            bold=True,
            align=PP_ALIGN.CENTER,
        )
        box = text_box(
            slide,
            x=x + 640080,
            y=top - 27432,
            w=w - 640080,
            h=step_h - 91440,
        )
        write(box, plain(title), size=18, colour=P.ink_soft, bold=True)
        write(
            box,
            plain(detail),
            size=15,
            colour=P.muted,
            line_spacing=1.25,
            first=False,
        )


def rail(
    slide: Slide,
    *,
    title: str,
    lines: Sequence[str],
    y: int = Y_BODY,
    h: int = 4882896,
    accent: str = P.teal,
) -> None:
    """The dark right-hand column that says what to take away."""
    dark_panel(slide, x=COL_RAIL_X, y=y, w=COL_RAIL_W, h=h)
    head = text_box(
        slide,
        x=COL_RAIL_X + 338328,
        y=y + 274320,
        w=COL_RAIL_W - 658368,
        h=502920,
    )
    write(head, plain(title), size=17, colour=accent, bold=True)

    body = text_box(
        slide,
        x=COL_RAIL_X + 338328,
        y=y + 822960,
        w=COL_RAIL_W - 658368,
        h=h - 1188720,
    )
    for index, text in enumerate(lines):
        write(
            body,
            plain(text),
            size=15.5,
            colour=P.on_dark_soft,
            line_spacing=1.35,
            space_after=12,
            first=index == 0,
        )


def compare(
    slide: Slide,
    *,
    left_title: str,
    left_rows: Sequence[tuple[str, str]],
    right_title: str,
    right_rows: Sequence[tuple[str, str]],
    x: int,
    y: int,
    w: int,
    h: int,
    left_accent: str = P.amber,
    right_accent: str = P.teal,
) -> None:
    """Two labelled columns for a legacy-versus-current comparison."""
    gap = 274320
    column = (w - gap) // 2
    for index, (title, rows, accent) in enumerate(
        (
            (left_title, left_rows, left_accent),
            (right_title, right_rows, right_accent),
        )
    ):
        left = x + index * (column + gap)
        card(slide, x=left, y=y, w=column, h=h)
        rounded(
            slide,
            x=left,
            y=y,
            w=column,
            h=68580,
            fill=accent,
            line=None,
            radius=0,
        )
        head = text_box(
            slide,
            x=left + 320040,
            y=y + 274320,
            w=column - 640080,
            h=384048,
        )
        write(head, plain(title), size=19, colour=P.ink, bold=True)

        body = text_box(
            slide,
            x=left + 320040,
            y=y + 777240,
            w=column - 640080,
            h=h - 914400,
        )
        for row_index, (label, detail) in enumerate(rows):
            write(
                body,
                [
                    (f"{label}  ", {"bold": True, "colour": P.ink_soft}),
                    (detail, {"colour": P.muted}),
                ],
                size=15,
                colour=P.muted,
                line_spacing=1.3,
                space_after=9,
                first=row_index == 0,
            )


def callout(
    slide: Slide,
    text: str,
    *,
    x: int,
    y: int,
    w: int,
    accent: str = P.coral,
    size: float = 16,
) -> None:
    """The single-sentence takeaway that closes a slide.

    The bar and the box grow together with the sentence, so a longer
    takeaway never clips: at this width a line holds roughly
    ``w / (size * 0.52)`` characters.
    """
    per_line = max(int((w - 228600) / (size * 0.52 * 12700)), 1)
    lines = max(1, -(-len(text) // per_line))
    height = max(548640, int(lines * size * 1.3 * 12700) + 182880)

    rounded(
        slide,
        x=x,
        y=y,
        w=68580,
        h=height,
        fill=accent,
        line=None,
        radius=0,
    )
    box = text_box(
        slide,
        x=x + 228600,
        y=y,
        w=w - 228600,
        h=height,
        anchor=MSO_ANCHOR.MIDDLE,
    )
    write(box, plain(text), size=size, colour=P.ink_soft, bold=True)


def timeline(
    slide: Slide,
    points: Sequence[tuple[str, str, str]],
    *,
    x: int,
    y: int,
    w: int,
    accent: str = P.coral,
) -> None:
    """A horizontal dated timeline.

    Args:
        slide: Target slide.
        points: ``(date, title, note)`` per milestone.
        x: Left edge.
        y: Vertical centre of the spine.
        w: Total width.
        accent: Colour of the final, current milestone.
    """
    rule(slide, x=x, y=y, w=w, colour=P.rule)
    count = len(points)
    pitch = w // max(count - 1, 1)
    for index, (date, title, note) in enumerate(points):
        centre = x + index * pitch
        current = index == count - 1
        dot = rounded(
            slide,
            x=centre - 91440,
            y=y - 85344,
            w=182880,
            h=182880,
            fill=accent if current else P.faint,
            line=None,
            radius=50000,
        )
        dot.text_frame.word_wrap = False

        above = text_box(
            slide,
            x=centre - 1005840,
            y=y - 685800,
            w=2011680,
            h=457200,
            align=PP_ALIGN.CENTER,
        )
        write(
            above,
            plain(date),
            size=12.5,
            colour=accent if current else P.faint,
            bold=True,
            align=PP_ALIGN.CENTER,
        )

        below = text_box(
            slide,
            x=centre - 1097280,
            y=y + 228600,
            w=2194560,
            h=1005840,
            align=PP_ALIGN.CENTER,
        )
        write(
            below,
            plain(title),
            size=14,
            colour=P.ink_soft,
            bold=True,
            align=PP_ALIGN.CENTER,
        )
        write(
            below,
            plain(note),
            size=12,
            colour=P.muted,
            align=PP_ALIGN.CENTER,
            line_spacing=1.2,
            first=False,
        )


def run_strip(slide: Slide, *commands: str) -> None:
    """Print the command that reproduces the slide, in the footer row.

    Every technology slide carries one, always in the same place, so a
    developer in the room learns to look there. The strip is part of
    the slide chrome: it sits between the footer text and the page
    number, where the layout check does not police it.
    """
    from theme import MARGIN_L, SLIDE_W, Y_FOOTER

    text = "   ·   ".join(f"uv run msai-demo {c}" for c in commands)
    size = 14.0
    left = MARGIN_L + 3931920
    right = SLIDE_W - MARGIN_L - 2862072
    width = min(
        right - left,
        int(len(text) * size * 0.58 * 12700) + 594360,
    )
    x = left + (right - left - width) // 2
    pill = rounded(
        slide,
        x=x,
        y=Y_FOOTER - 64008,
        w=width,
        h=420624,
        fill=P.wash,
        line=P.rule,
        radius=50000,
    )
    pill.name = "chrome-run-pill"
    box = text_box(
        slide,
        x=x,
        y=Y_FOOTER - 64008,
        w=width,
        h=420624,
        align=PP_ALIGN.CENTER,
        anchor=MSO_ANCHOR.MIDDLE,
    )
    box.name = "chrome-run"
    write(
        box,
        [("▶  ", {"colour": P.teal, "font": "Arial"}), (text, {})],
        size=size,
        colour=P.ink_soft,
        bold=True,
        font=FONT_CODE,
        align=PP_ALIGN.CENTER,
    )


def source_note(slide: Slide, text: str, *, y: int = 8961120) -> None:
    """The small grey provenance line every evidence slide carries."""
    from theme import CONTENT_W, MARGIN_L

    box = text_box(slide, x=MARGIN_L, y=y, w=CONTENT_W, h=274320)
    write(box, plain(text), size=12.5, colour=P.faint)


def layer_row(
    slide: Slide,
    *,
    top: int,
    colour: str,
    role: str,
    product: str,
    detail: str,
    x: int,
    w: int,
    h: int = 960120,
) -> None:
    """One band of the stack map: a role, a product, a sentence.

    Args:
        slide: Target slide.
        top: Top edge of the band.
        colour: Lane colour, drawn as a spine on the left.
        role: What this layer is responsible for.
        product: The Microsoft product that fills the role.
        detail: One line on what it actually owns.
        x: Left edge.
        w: Width.
        h: Height of the band.
    """
    card(slide, x=x, y=top, w=w, h=h)
    rounded(slide, x=x, y=top, w=68580, h=h, fill=colour, line=None, radius=0)

    left = text_box(
        slide,
        x=x + 365760,
        y=top,
        w=2834640,
        h=h,
        anchor=MSO_ANCHOR.MIDDLE,
    )
    write(left, plain(role.upper()), size=14, colour=colour, bold=True)

    right = text_box(
        slide,
        x=x + 3383280,
        y=top,
        w=w - 3749040,
        h=h,
        anchor=MSO_ANCHOR.MIDDLE,
    )
    write(right, plain(product), size=24, colour=P.ink, bold=True)
    write(right, plain(detail), size=16, colour=P.muted, first=False)


def _text_height(text: str, width: int, size: float) -> int:
    """Reserve whole lines using the strict build metric."""
    per_line = max(int(width / (size * 0.52 * 12700)), 1)
    lines = sum(max(1, -(-len(part) // per_line)) for part in text.split("\n"))
    return int(lines * size * 1.2 * 1.16 * 12700)


def use_case(
    slide: Slide,
    *,
    who: str,
    steps: Sequence[str],
    result: str,
    x: int,
    y: int,
    w: int,
    accent: str,
    label: str = "USE CASE - illustrative",
) -> int:
    """Draw an illustrative actor, chip sequence and outcome card.

    Chips retain 14pt text and wrap as units to a second row. The
    returned bottom lets callers reserve space without guessing.
    """
    from theme import line

    if not 3 <= len(steps) <= 4:
        message = "A use case needs three or four short steps"
        raise ValueError(message)
    pad, gap = 109728, 45720
    inner = w - 2 * pad
    arrow_w = 274320
    chip_h = 320040
    chip_rows: list[list[tuple[str, int]]] = [[]]
    used = 0
    for step in steps:
        width = max(548640, int(len(step) * 14 * 0.52 * 12700) + 182880)
        if width > inner:
            message = f"Use-case chip is too long for its card: {step}"
            raise ValueError(message)
        extra = arrow_w if chip_rows[-1] else 0
        if used + extra + width > inner:
            chip_rows.append([])
            used, extra = arrow_w, 0
        chip_rows[-1].append((step, width))
        used += extra + width
    if len(chip_rows) > 2:
        message = "Use-case steps require more than two chip rows"
        raise ValueError(message)
    who_h = _text_height(who, inner, 16)
    result_text = f"Result: {result}"
    result_h = _text_height(result_text, inner, 14)
    label_h = 213360
    height = (
        2 * pad
        + label_h
        + who_h
        + result_h
        + 3 * gap
        + len(chip_rows) * chip_h
        + (len(chip_rows) - 1) * gap
    )
    rounded(slide, x=x, y=y, w=w, h=height, fill=P.wash, line=P.rule)
    rounded(
        slide, x=x, y=y, w=54864, h=height, fill=accent, line=None, radius=0
    )
    top = y + pad
    tag = text_box(slide, x=x + pad, y=top, w=inner, h=label_h)
    write(tag, plain(label), size=12, colour=P.faint, bold=True)
    top += label_h + gap
    actor = text_box(slide, x=x + pad, y=top, w=inner, h=who_h)
    write(actor, plain(who), size=16, colour=P.ink, bold=True)
    top += who_h + gap
    for row_index, row in enumerate(chip_rows):
        left = x + pad
        if row_index:
            # A continuation label preserves the sequence across rows.
            left += arrow_w
            line(
                slide,
                x=x + pad,
                y=top + chip_h // 2,
                w=arrow_w - 45720,
                h=0,
                colour=accent,
            )
        for index, (step, width) in enumerate(row):
            if index:
                line(
                    slide,
                    x=left + 45720,
                    y=top + chip_h // 2,
                    w=arrow_w - 91440,
                    h=0,
                    colour=accent,
                )
                left += arrow_w
            chip = rounded(
                slide,
                x=left,
                y=top,
                w=width,
                h=chip_h,
                fill=P.card,
                line=P.rule,
                radius=50000,
            )
            chip.text_frame.margin_left = 0
            chip.text_frame.margin_right = 0
            chip.text_frame.margin_top = 0
            chip.text_frame.margin_bottom = 0
            chip.text_frame.vertical_anchor = MSO_ANCHOR.MIDDLE
            write(
                chip,
                plain(step),
                size=14,
                colour=P.body,
                align=PP_ALIGN.CENTER,
            )
            left += width
        top += chip_h + gap
    outcome = text_box(slide, x=x + pad, y=top, w=inner, h=result_h)
    write(outcome, plain(result_text), size=14, colour=P.muted)
    return y + height


def screenshot(
    slide: Slide,
    path: str,
    *,
    x: int,
    y: int,
    w: int,
    h: int,
    caption: str,
    callouts: Sequence[tuple[float, float, str]] = (),
    legend_x: int | None = None,
    legend_y: int | None = None,
    legend_w: int | None = None,
    legend_columns: int = 1,
) -> int:
    """Crop a screenshot, with numbered points and a text legend.

    Coordinates in callouts refer to the cropped picture box. When
    used, the legend position and width must be explicit. Returns the
    bottom of the caption (the legend has its own layout).
    """
    from pptx.enum.shapes import MSO_SHAPE
    from pptx.util import Emu
    from theme import rgb

    picture = slide.shapes.add_picture(str(path), Emu(x), Emu(y))
    natural_ratio = picture.width / picture.height
    target_ratio = w / h
    if natural_ratio > target_ratio:
        crop = (1 - target_ratio / natural_ratio) / 2
        picture.crop_left = picture.crop_right = crop
    else:
        crop = (1 - natural_ratio / target_ratio) / 2
        picture.crop_top = picture.crop_bottom = crop
    picture.width, picture.height = Emu(w), Emu(h)
    rounded(
        slide,
        x=x,
        y=y,
        w=w,
        h=h,
        fill=None,
        line=P.rule,
        line_w=12700,
        radius=0,
    )
    caption_h = _text_height(caption, w, 12)
    box = text_box(slide, x=x, y=y + h + 91440, w=w, h=caption_h)
    write(box, plain(caption), size=12, colour=P.faint)
    if callouts:
        if legend_x is None or legend_y is None or legend_w is None:
            message = "Numbered screenshots require an explicit text legend"
            raise ValueError(message)
        top = legend_y
        column_w = legend_w // legend_columns
        row_h = (
            max(
                _text_height(f"{n}  {entry[2]}", column_w - 91440, 14)
                for n, entry in enumerate(callouts, 1)
            )
            + 45720
        )
        for number, (fx, fy, text) in enumerate(callouts, 1):
            if not 0 <= fx <= 1 or not 0 <= fy <= 1:
                message = "Screenshot callout fractions must be in [0, 1]"
                raise ValueError(message)
            diameter = 274320
            badge = slide.shapes.add_shape(
                MSO_SHAPE.OVAL,
                Emu(x + int(fx * w) - diameter // 2),
                Emu(y + int(fy * h) - diameter // 2),
                Emu(diameter),
                Emu(diameter),
            )
            badge.fill.solid()
            badge.fill.fore_color.rgb = rgb(P.coral)
            badge.line.fill.background()
            for edge in ("left", "right", "top", "bottom"):
                setattr(badge.text_frame, f"margin_{edge}", 0)
            badge.text_frame.vertical_anchor = MSO_ANCHOR.MIDDLE
            write(
                badge,
                plain(str(number)),
                size=12,
                colour=P.on_dark,
                bold=True,
                align=PP_ALIGN.CENTER,
            )
            entry = f"{number}  {text}"
            entry_h = _text_height(entry, column_w - 91440, 14)
            top = legend_y + ((number - 1) // legend_columns) * row_h
            left = legend_x + ((number - 1) % legend_columns) * column_w
            row = text_box(slide, x=left, y=top, w=column_w - 91440, h=entry_h)
            write(row, plain(entry), size=14, colour=P.muted)
    return y + h + 91440 + caption_h

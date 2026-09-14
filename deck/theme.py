"""The DataArt deck design system, as code.

Every constant here was measured from the reference deck
(`lang-stack/langchain_python_community_worshop_2026-08-27.pptx`) so
this deck sits in the same template: same canvas, same grid, same
palette, same type scale, same artwork.

Nothing in this module knows anything about the Microsoft AI stack. It
is the layout engine; `build_deck.py` is the content.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Final

from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Emu, Pt

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

    from pptx.presentation import Presentation
    from pptx.shapes.autoshape import Shape
    from pptx.slide import Slide

# --------------------------------------------------------------------
# Canvas and grid. 18288000 x 10287000 EMU is 20 x 11.25 inches, which
# is a 1920 x 1080 design canvas at 96 dpi.
# --------------------------------------------------------------------
SLIDE_W: Final[int] = 18288000
SLIDE_H: Final[int] = 10287000

MARGIN_L: Final[int] = 1439997
MARGIN_R: Final[int] = 1439997
CONTENT_W: Final[int] = SLIDE_W - MARGIN_L - MARGIN_R

# Vertical rhythm, measured off the reference content slides.
Y_EYEBROW: Final[int] = 658368
Y_TITLE: Final[int] = 1079998
Y_DECK: Final[int] = 2194560
Y_BODY: Final[int] = 3127248
Y_FOOTER: Final[int] = 9428653
BODY_H: Final[int] = Y_FOOTER - Y_BODY - 228600

# Two-column split used by most content slides.
COL_MAIN_W: Final[int] = 11338560
COL_RAIL_X: Final[int] = 13121640
COL_RAIL_W: Final[int] = 3721608

# Logo placement differs between the light and dark layouts.
LOGO_LIGHT: Final[tuple[int, int, int, int]] = (
    14695204,
    1300130,
    2180378,
    359999,
)
LOGO_DARK_TITLE: Final[tuple[int, int, int, int]] = (
    1439997,
    960120,
    2788920,
    461772,
)
LOGO_DARK_SECTION: Final[tuple[int, int, int, int]] = (
    1439997,
    1005840,
    2395728,
    395935,
)

ASSETS: Final[Path] = Path(__file__).resolve().parent / "assets"


# --------------------------------------------------------------------
# Palette
# --------------------------------------------------------------------
@dataclass(frozen=True)
class Palette:
    """Every colour the deck is allowed to use."""

    ink: str = "000000"  # headlines on light
    ink_soft: str = "23272F"  # sub-headlines on light
    body: str = "333333"  # body copy
    muted: str = "5A6478"  # supporting copy
    faint: str = "8A93A6"  # footers, captions
    rule: str = "D8DDE8"  # hairlines and card borders
    card: str = "FFFFFF"  # card fill on light
    wash: str = "F6F8FC"  # very light fill

    panel: str = "0E1A33"  # code panel fill
    panel_deep: str = "1B2440"  # dark rail fill
    code_fg: str = "E6EAF2"  # code default foreground
    code_dim: str = "7C8CAE"  # code panel caption

    on_dark: str = "FFFFFF"
    on_dark_soft: str = "D9E2F7"
    on_dark_faint: str = "9FB2D8"

    coral: str = "F0503C"  # primary accent / legacy lane
    teal: str = "2BC6BF"  # secondary accent / current lane
    amber: str = "FFB133"  # caution / preview
    yellow: str = "FFDE55"  # eyebrow on dark, code strings
    blue: str = "3453AD"  # structural
    sky: str = "53CFF8"  # code keywords
    violet: str = "70529F"  # protocols


P: Final[Palette] = Palette()

# Lane colours, used consistently on every slide and diagram.
LANE_COLOUR: Final[dict[str, str]] = {
    "legacy": P.amber,
    "current": P.teal,
    "shared": P.blue,
}

FONT_UI: Final[str] = "Arial"
FONT_CODE: Final[str] = "Consolas"

FOOTER_TEXT: Final[str] = "Your Partner for Progress"

# Set by build_deck.py before each slide renders. Slide modules never
# type a page number: the running order in SLIDES is the only source.
_CURRENT_NUMBER: list[int] = [0]
_SLIDE_INDEX: dict[str, int] = {}


def begin_slide(number: int) -> None:
    """Record the page number the next slide will carry."""
    _CURRENT_NUMBER[0] = number


def register_order(names: Sequence[str]) -> None:
    """Record the running order so slides can cross-reference."""
    _SLIDE_INDEX.clear()
    _SLIDE_INDEX.update({name: i for i, name in enumerate(names, 1)})


def number_of(name: str) -> int:
    """Return the page number of a slide function, by name."""
    return _SLIDE_INDEX[name]


# --------------------------------------------------------------------
# Low-level helpers
# --------------------------------------------------------------------
def rgb(value: str) -> RGBColor:
    """Turn a six-digit hex string into a pptx colour."""
    return RGBColor.from_string(value)


def set_background(slide: Slide, image: str) -> None:
    """Stretch one of the template artworks behind a slide."""
    picture = slide.shapes.add_picture(
        str(ASSETS / image),
        Emu(0),
        Emu(0),
        Emu(SLIDE_W),
        Emu(SLIDE_H),
    )
    # Backgrounds must sit behind everything added afterwards.
    slide.shapes._spTree.remove(picture._element)
    slide.shapes._spTree.insert(2, picture._element)


def add_logo(slide: Slide, *, dark: bool, section: bool = False) -> None:
    """Place the DataArt logo in its layout-specific position."""
    if dark:
        box = LOGO_DARK_SECTION if section else LOGO_DARK_TITLE
        name = "logo_white.png"
    else:
        box, name = LOGO_LIGHT, "logo_dark.png"
    left, top, width, height = box
    slide.shapes.add_picture(
        str(ASSETS / name),
        Emu(left),
        Emu(top),
        Emu(width),
        Emu(height),
    )


def text_box(
    slide: Slide,
    *,
    x: int,
    y: int,
    w: int,
    h: int,
    align: PP_ALIGN | None = None,
    anchor: MSO_ANCHOR | None = None,
) -> Shape:
    """Add a borderless text box with zero internal padding.

    The reference deck sets every inset to zero so that text aligns to
    the grid rather than to PowerPoint's default margins.
    """
    shape = slide.shapes.add_textbox(Emu(x), Emu(y), Emu(w), Emu(h))
    frame = shape.text_frame
    frame.word_wrap = True
    frame.margin_left = 0
    frame.margin_right = 0
    frame.margin_top = 0
    frame.margin_bottom = 0
    if anchor is not None:
        frame.vertical_anchor = anchor
    if align is not None:
        frame.paragraphs[0].alignment = align
    return shape


def write(
    shape: Shape,
    runs: Sequence[tuple[str, dict[str, object]]],
    *,
    size: float,
    colour: str,
    bold: bool = False,
    font: str = FONT_UI,
    line_spacing: float | None = None,
    space_after: int = 0,
    align: PP_ALIGN | None = None,
    first: bool = True,
) -> None:
    """Write one paragraph of styled runs into a text box.

    Args:
        shape: Target text box.
        runs: ``(text, overrides)`` pairs. Overrides may set ``size``,
            ``colour``, ``bold`` or ``font`` for that run alone.
        size: Default point size for the paragraph.
        colour: Default hex colour.
        bold: Default weight.
        font: Default typeface.
        line_spacing: Multiple of single spacing, when not the default.
        space_after: Points of space after the paragraph.
        align: Paragraph alignment.
        first: Reuse the empty first paragraph instead of adding one.
    """
    frame = shape.text_frame
    para = frame.paragraphs[0] if first else frame.add_paragraph()
    if align is not None:
        para.alignment = align
    if line_spacing is not None:
        para.line_spacing = line_spacing
    para.space_after = Pt(space_after)

    for text, override in runs:
        run = para.add_run()
        run.text = text
        font_obj = run.font
        font_obj.name = str(override.get("font", font))
        font_obj.size = Pt(float(override.get("size", size)))
        font_obj.bold = bool(override.get("bold", bold))
        font_obj.color.rgb = rgb(str(override.get("colour", colour)))
        link = override.get("link")
        if link:
            # A real hyperlink, clickable in PowerPoint and in PDF.
            run.hyperlink.address = str(link)


def plain(text: str) -> list[tuple[str, dict[str, object]]]:
    """Shorthand for a single unstyled run."""
    return [(text, {})]


def rounded(
    slide: Slide,
    *,
    x: int,
    y: int,
    w: int,
    h: int,
    fill: str | None,
    line: str | None = None,
    line_w: int = 12700,
    radius: int = 1520,
    alpha: int | None = None,
) -> Shape:
    """Add the deck's standard rounded rectangle.

    ``radius`` is the OOXML ``adj`` value; 1520 is the card corner the
    reference deck uses everywhere, and 50000 makes a pill.
    """
    shape = slide.shapes.add_shape(
        MSO_SHAPE.ROUNDED_RECTANGLE,
        Emu(x),
        Emu(y),
        Emu(w),
        Emu(h),
    )
    shape.shadow.inherit = False
    _set_adjust(shape, radius)

    if fill is None:
        shape.fill.background()
    else:
        shape.fill.solid()
        shape.fill.fore_color.rgb = rgb(fill)
        if alpha is not None:
            _set_alpha(shape, alpha)

    if line is None:
        shape.line.fill.background()
    else:
        shape.line.color.rgb = rgb(line)
        shape.line.width = Emu(line_w)

    shape.text_frame.word_wrap = True
    return shape


def card(slide: Slide, *, x: int, y: int, w: int, h: int) -> Shape:
    """A white card with the standard hairline border."""
    return rounded(slide, x=x, y=y, w=w, h=h, fill=P.card, line=P.rule)


def code_panel(slide: Slide, *, x: int, y: int, w: int, h: int) -> Shape:
    """The dark navy panel that code always sits on."""
    return rounded(
        slide,
        x=x,
        y=y,
        w=w,
        h=h,
        fill=P.panel,
        line=P.body,
    )


def dark_panel(slide: Slide, *, x: int, y: int, w: int, h: int) -> Shape:
    """The deep navy rail used for the 'read this' side column."""
    return rounded(slide, x=x, y=y, w=w, h=h, fill=P.panel_deep, line=None)


def line(
    slide: Slide,
    *,
    x: int,
    y: int,
    w: int,
    h: int,
    colour: str,
    width: int = 19050,
    dashed: bool = False,
    arrow: bool = True,
    reverse: bool = False,
) -> Shape:
    """Draw a connector.

    A zero height is a horizontal run, a zero width a vertical one;
    anything else is a diagonal. Dashed means "this path needs a cloud
    resource you do not have yet".
    """
    shape = slide.shapes.add_shape(
        MSO_SHAPE.LINE_INVERSE if False else MSO_SHAPE.RECTANGLE,
        Emu(x),
        Emu(y),
        Emu(max(w, 1)),
        Emu(max(h, 1)),
    )
    # Replace the rectangle geometry with a straight connector so the
    # shape renders as a line rather than a filled box.
    _set_geometry(shape, "line")
    shape.fill.background()
    shape.line.color.rgb = rgb(colour)
    shape.line.width = Emu(width)
    shape.shadow.inherit = False
    if dashed:
        _set_dash(shape, "dash")
    if arrow:
        _set_arrow(shape, reverse=reverse)
    return shape


def _set_geometry(shape: Shape, preset: str) -> None:
    """Swap a shape's preset geometry in place."""
    prst = shape._element.spPr.find(qn("a:prstGeom"))
    if prst is not None:
        prst.set("prst", preset)


def _set_adjust(shape: Shape, value: int) -> None:
    """Set the corner-radius adjustment on a rounded rectangle."""
    shape.adjustments[0] = value / 100000


def _set_alpha(shape: Shape, alpha: int) -> None:
    """Apply transparency to a solid fill, in OOXML thousandths."""
    fill = shape._element.spPr.find(qn("a:solidFill"))
    if fill is None:
        return
    colour = fill.find(qn("a:srgbClr"))
    if colour is None:
        return
    node = colour.makeelement(qn("a:alpha"), {"val": str(alpha)})
    colour.append(node)


def _set_dash(shape: Shape, style: str) -> None:
    """Make a connector dashed."""
    ln = shape._element.spPr.find(qn("a:ln"))
    if ln is None:
        return
    node = ln.makeelement(qn("a:prstDash"), {"val": style})
    ln.append(node)


def _set_arrow(shape: Shape, *, reverse: bool = False) -> None:
    """Put a triangular head on the end of a connector."""
    ln = shape._element.spPr.find(qn("a:ln"))
    if ln is None:
        return
    node = ln.makeelement(
        qn("a:headEnd" if reverse else "a:tailEnd"),
        {"type": "triangle", "w": "med", "len": "med"},
    )
    ln.append(node)


# --------------------------------------------------------------------
# Slide chrome
# --------------------------------------------------------------------
def new_slide(prs: Presentation) -> Slide:
    """Add a blank slide."""
    return prs.slides.add_slide(prs.slide_layouts[6])


def footer(slide: Slide, number: int | str, *, dark: bool = False) -> None:
    """Add the standard footer and page number.

    An integer ``number`` is ignored in favour of the number the build
    assigned; a string (``dataart.com`` on the cover) is printed as is.
    """
    if isinstance(number, int) and _CURRENT_NUMBER[0]:
        number = _CURRENT_NUMBER[0]
    colour = P.on_dark_faint if dark else P.faint
    left = text_box(slide, x=MARGIN_L, y=Y_FOOTER, w=3657600, h=411480)
    left.name = "chrome-footer"
    write(left, plain(FOOTER_TEXT), size=12, colour=colour)
    right = text_box(
        slide,
        x=SLIDE_W - MARGIN_L - 2679192,
        y=Y_FOOTER,
        w=2679192,
        h=411480,
        align=PP_ALIGN.RIGHT,
    )
    right.name = "chrome-page-number"
    write(
        right,
        plain(str(number)),
        size=12,
        colour=colour,
        align=PP_ALIGN.RIGHT,
    )


def title_size(title: str) -> float:
    """Return the headline size, which is always the reference 38pt.

    The reference deck never shrinks a headline, and the grid leaves
    room for exactly one line of 38pt above the deck line. A headline
    that would wrap is caught by the build's title check and has to be
    rewritten shorter.
    """
    del title
    return 38.0


def heading(
    slide: Slide,
    *,
    eyebrow: str,
    title: str,
    deck: str,
    accent: str = P.coral,
) -> None:
    """Write the three-line heading every content slide starts with."""
    brow = text_box(
        slide,
        x=MARGIN_L,
        y=Y_EYEBROW,
        w=CONTENT_W,
        h=310896,
        anchor=MSO_ANCHOR.MIDDLE,
    )
    write(brow, plain(eyebrow.upper()), size=14, colour=accent, bold=True)

    head = text_box(
        slide,
        x=MARGIN_L,
        y=Y_TITLE,
        w=LOGO_LIGHT[0] - MARGIN_L - 45720,
        h=1051560,
    )
    # The build checks this shape by name: a headline must fit one line.
    head.name = "title"
    write(
        head,
        plain(title),
        size=title_size(title),
        colour=P.ink,
        line_spacing=1.05,
    )

    if deck:
        sub = text_box(slide, x=MARGIN_L, y=Y_DECK, w=CONTENT_W, h=566928)
        write(sub, plain(deck), size=19, colour=P.muted, line_spacing=1.2)


def content_slide(
    prs: Presentation,
    *,
    eyebrow: str,
    title: str,
    deck: str,
    number: int | str,
    accent: str = P.coral,
) -> Slide:
    """Create the standard light content slide with its chrome."""
    slide = new_slide(prs)
    set_background(slide, "bg_content.jpeg")
    add_logo(slide, dark=False)
    heading(
        slide,
        eyebrow=eyebrow,
        title=title,
        deck=deck,
        accent=accent,
    )
    footer(slide, number)
    return slide


def section_slide(
    prs: Presentation,
    *,
    index: str,
    eyebrow: str,
    title_lines: Sequence[str],
    deck: str,
    bullets: Iterable[str],
    number: int | str,
    accent: str = P.teal,
) -> Slide:
    """Create a dark section divider with its 'in this section' list."""
    slide = new_slide(prs)
    set_background(slide, "bg_section.jpeg")
    add_logo(slide, dark=True, section=True)

    # Four small squares, a motif the template uses on dividers.
    for step in range(4):
        rounded(
            slide,
            x=MARGIN_L + step * 420624,
            y=2359152,
            w=274320,
            h=274320,
            fill=accent if step == 0 else P.on_dark,
            line=None,
            radius=0,
            alpha=None if step == 0 else 30000,
        )

    number_box = text_box(slide, x=MARGIN_L, y=2798064, w=3840480, h=1965960)
    write(number_box, plain(index), size=128, colour=P.on_dark, bold=True)

    brow = text_box(slide, x=MARGIN_L, y=4956048, w=8229600, h=365760)
    write(brow, plain(eyebrow.upper()), size=15, colour=accent, bold=True)

    head = text_box(slide, x=MARGIN_L, y=5321808, w=7863840, h=1920240)
    for position, part in enumerate(title_lines):
        write(
            head,
            plain(part),
            size=50,
            colour=P.on_dark,
            line_spacing=1.05,
            first=position == 0,
        )

    sub = text_box(slide, x=MARGIN_L, y=7333488, w=7863840, h=1188720)
    write(sub, plain(deck), size=18, colour=P.on_dark_soft, line_spacing=1.3)

    panel = rounded(
        slide,
        x=10058400,
        y=2798064,
        w=6784848,
        h=4727448,
        fill=P.on_dark,
        line=None,
        alpha=10000,
    )
    panel.text_frame.text = ""

    label = text_box(slide, x=10533888, y=3163824, w=5833872, h=347472)
    write(
        label,
        plain("IN THIS SECTION"),
        size=13,
        colour=P.on_dark_faint,
        bold=True,
    )

    for position, item in enumerate(bullets):
        top = 3749040 + position * 822960
        rounded(
            slide,
            x=10533888,
            y=top + 109728,
            w=201168,
            h=201168,
            fill=accent,
            line=None,
            radius=50000,
        )
        row = text_box(slide, x=10954512, y=top, w=5367528, h=786384)
        write(
            row,
            plain(item),
            size=16.5,
            colour="E4EBFA",
            line_spacing=1.25,
        )

    footer(slide, number, dark=True)
    return slide

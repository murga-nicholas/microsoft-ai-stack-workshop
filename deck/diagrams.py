"""Architecture schemas, drawn as native PowerPoint shapes.

Every technology in this deck gets a diagram, and every diagram is
drawn from a declarative spec rather than pasted as an image. That
keeps them editable in PowerPoint, keeps them legible when projected,
and keeps one visual grammar across forty slides:

====================  ==================================================
process               rounded rectangle, filled in the lane colour
state                 cylinder — anything that survives a restart
decision              diamond
boundary              an outlined region: a trust, host or process edge
solid connector       a path this repository actually exercises
dashed connector      a path that needs a cloud resource you must bring
====================  ==================================================

A reader who learns those six marks once can read every schema in the
deck without a legend, and the legend is on the slide anyway.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, Literal

from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Emu, Pt
from theme import (
    FONT_CODE,
    FONT_UI,
    P,
    line,
    plain,
    rgb,
    rounded,
    text_box,
    write,
)

if TYPE_CHECKING:
    from pptx.shapes.autoshape import Shape
    from pptx.slide import Slide

NodeKind = Literal["process", "state", "decision", "actor", "note"]

# One grid unit. Diagrams are laid out on a coarse grid so that
# everything lines up without hand-tuning EMU on forty slides.
UNIT_X: int = 228600
UNIT_Y: int = 182880


@dataclass(frozen=True)
class Node:
    """One box in a schema.

    Attributes:
        key: Identifier used by :class:`Edge`.
        label: Text drawn inside. Keep it to three or four words.
        col: Left edge, in grid units from the diagram origin.
        row: Top edge, in grid units.
        width: Width in grid units.
        height: Height in grid units.
        kind: Which shape grammar to use.
        colour: Fill (process/actor) or outline (state/decision).
        mono: Draw the label in Consolas, for code identifiers.
        sub: Optional second line, one size smaller.
    """

    key: str
    label: str
    col: float
    row: float
    width: float = 8
    height: float = 3
    kind: NodeKind = "process"
    colour: str = P.blue
    mono: bool = False
    sub: str = ""


@dataclass(frozen=True)
class Edge:
    """A connector between two nodes.

    Attributes:
        start: Key of the source node.
        end: Key of the target node.
        label: Optional text placed beside the midpoint.
        dashed: Marks a path that needs a resource you must provide.
        side: Which faces to leave from and arrive at. ``auto`` picks
            horizontal when the nodes are side by side, otherwise
            vertical.
    """

    start: str
    end: str
    label: str = ""
    dashed: bool = False
    side: Literal["auto", "h", "v"] = "auto"


@dataclass(frozen=True)
class Boundary:
    """A labelled region enclosing several nodes.

    Attributes:
        label: What the region is, e.g. "Microsoft Foundry".
        col: Left edge in grid units.
        row: Top edge in grid units.
        width: Width in grid units.
        height: Height in grid units.
        colour: Outline colour.
    """

    label: str
    col: float
    row: float
    width: float
    height: float
    colour: str = P.faint


@dataclass
class Schema:
    """A complete diagram.

    Attributes:
        nodes: Boxes, in draw order.
        edges: Connectors.
        boundaries: Regions, drawn behind the nodes.
        caption: One line under the diagram.
    """

    nodes: list[Node] = field(default_factory=list)
    edges: list[Edge] = field(default_factory=list)
    boundaries: list[Boundary] = field(default_factory=list)
    caption: str = ""


class Canvas:
    """Grid-to-EMU mapping for one diagram on one slide."""

    def __init__(self, *, x: int, y: int) -> None:
        """Anchor a diagram's grid origin at an absolute position."""
        self.x = x
        self.y = y

    def left(self, col: float) -> int:
        """Absolute left edge for a grid column."""
        return int(self.x + col * UNIT_X)

    def top(self, row: float) -> int:
        """Absolute top edge for a grid row."""
        return int(self.y + row * UNIT_Y)

    def width(self, units: float) -> int:
        """Absolute width for a span of grid columns."""
        return int(units * UNIT_X)

    def height(self, units: float) -> int:
        """Absolute height for a span of grid rows."""
        return int(units * UNIT_Y)


def draw(slide: Slide, schema: Schema, *, x: int, y: int) -> None:
    """Render a schema onto a slide.

    Boundaries are drawn first so they sit behind their contents,
    then connectors, then nodes, so a connector never covers a label.
    """
    schema = _normalised(schema)
    canvas = Canvas(x=x, y=y)
    for boundary in schema.boundaries:
        _draw_boundary(slide, canvas, boundary)

    placed = {node.key: node for node in schema.nodes}
    for edge in schema.edges:
        _draw_edge(slide, canvas, edge, placed)
    for node in schema.nodes:
        _draw_node(slide, canvas, node)

    if schema.caption:
        # A caption sits under everything, boundaries included, so it
        # never lands on top of a region's dashed edge.
        widest = max(
            [node.col + node.width for node in schema.nodes]
            + [b.col + b.width for b in schema.boundaries],
            default=10.0,
        )
        lowest = max(
            [node.row + node.height for node in schema.nodes]
            + [b.row + b.height for b in schema.boundaries],
            default=6.0,
        )
        box = text_box(
            slide,
            x=canvas.left(0),
            y=canvas.top(lowest + 0.9),
            w=canvas.width(widest),
            h=UNIT_Y * 3,
        )
        write(box, plain(schema.caption), size=14, colour=P.muted)


def _normalised(schema: Schema) -> Schema:
    """Slide a schema so its top-left content sits at the origin.

    Authors place nodes on whatever grid reads well while writing the
    slide. Without this, a diagram whose first node is on row 4 leaves
    four rows of blank space under the headline.
    """
    rows = [node.row for node in schema.nodes]
    cols = [node.col for node in schema.nodes]
    rows += [b.row for b in schema.boundaries]
    cols += [b.col for b in schema.boundaries]
    if not rows:
        return schema

    row_shift, col_shift = min(rows), min(cols)
    if row_shift == 0 and col_shift == 0:
        return schema

    return Schema(
        nodes=[
            replace(node, row=node.row - row_shift, col=node.col - col_shift)
            for node in schema.nodes
        ],
        edges=list(schema.edges),
        boundaries=[
            replace(b, row=b.row - row_shift, col=b.col - col_shift)
            for b in schema.boundaries
        ],
        caption=schema.caption,
    )


def _draw_node(slide: Slide, canvas: Canvas, node: Node) -> None:
    """Draw one node in its shape grammar."""
    left = canvas.left(node.col)
    top = canvas.top(node.row)
    width = canvas.width(node.width)
    height = canvas.height(node.height)

    if node.kind == "state":
        shape = _cylinder(slide, left, top, width, height, node.colour)
        label_colour = P.ink_soft
    elif node.kind == "decision":
        shape = _diamond(slide, left, top, width, height, node.colour)
        label_colour = P.ink_soft
    elif node.kind == "note":
        shape = rounded(
            slide,
            x=left,
            y=top,
            w=width,
            h=height,
            fill=P.wash,
            line=P.rule,
        )
        label_colour = P.muted
    elif node.kind == "actor":
        shape = rounded(
            slide,
            x=left,
            y=top,
            w=width,
            h=height,
            fill=P.card,
            line=node.colour,
            line_w=25400,
        )
        label_colour = P.ink_soft
    else:
        shape = rounded(
            slide,
            x=left,
            y=top,
            w=width,
            h=height,
            fill=node.colour,
            line=None,
        )
        label_colour = P.on_dark

    _label(shape, node, label_colour)


def _label(shape: Shape, node: Node, colour: str) -> None:
    """Write a node's label, and its optional second line."""
    frame = shape.text_frame
    frame.word_wrap = True
    frame.vertical_anchor = MSO_ANCHOR.MIDDLE
    frame.margin_left = Emu(45720)
    frame.margin_right = Emu(45720)
    frame.margin_top = 0
    frame.margin_bottom = 0
    write(
        shape,
        plain(node.label),
        size=15,
        colour=colour,
        bold=True,
        font=FONT_CODE if node.mono else FONT_UI,
        align=PP_ALIGN.CENTER,
    )
    if node.sub:
        write(
            shape,
            plain(node.sub),
            size=15,
            colour=colour,
            font=FONT_UI,
            align=PP_ALIGN.CENTER,
            first=False,
        )


def _cylinder(
    slide: Slide,
    left: int,
    top: int,
    width: int,
    height: int,
    colour: str,
) -> Shape:
    """A cylinder: anything that survives a process restart."""
    shape = slide.shapes.add_shape(
        MSO_SHAPE.CAN,
        Emu(left),
        Emu(top),
        Emu(width),
        Emu(height),
    )
    shape.shadow.inherit = False
    shape.fill.solid()
    shape.fill.fore_color.rgb = rgb(P.wash)
    shape.line.color.rgb = rgb(colour)
    shape.line.width = Emu(25400)
    return shape


def _diamond(
    slide: Slide,
    left: int,
    top: int,
    width: int,
    height: int,
    colour: str,
) -> Shape:
    """A diamond: a branch in the control flow."""
    shape = slide.shapes.add_shape(
        MSO_SHAPE.DIAMOND,
        Emu(left),
        Emu(top),
        Emu(width),
        Emu(height),
    )
    shape.shadow.inherit = False
    shape.fill.solid()
    shape.fill.fore_color.rgb = rgb(P.card)
    shape.line.color.rgb = rgb(colour)
    shape.line.width = Emu(25400)
    return shape


def _draw_boundary(
    slide: Slide,
    canvas: Canvas,
    boundary: Boundary,
) -> None:
    """Draw a labelled trust, host or process boundary."""
    shape = rounded(
        slide,
        x=canvas.left(boundary.col),
        y=canvas.top(boundary.row),
        w=canvas.width(boundary.width),
        h=canvas.height(boundary.height),
        fill=None,
        line=boundary.colour,
        line_w=12700,
        radius=2400,
    )
    _dash(shape)
    tag = text_box(
        slide,
        x=canvas.left(boundary.col) + 91440,
        y=canvas.top(boundary.row) - 228600,
        w=canvas.width(boundary.width),
        h=228600,
    )
    write(
        tag,
        plain(boundary.label.upper()),
        size=14,
        colour=boundary.colour,
        bold=True,
    )


def _dash(shape: Shape) -> None:
    """Make a boundary outline dashed."""
    from pptx.oxml.ns import qn

    ln = shape._element.spPr.find(qn("a:ln"))
    if ln is None:
        return
    ln.append(ln.makeelement(qn("a:prstDash"), {"val": "sysDash"}))


Segment = tuple[int, int, int, int]


def _route_horizontal(
    canvas: Canvas,
    start: Node,
    end: Node,
) -> tuple[list[Segment], int, int, int]:
    """Route left-to-right (or right-to-left) with one elbow."""
    forward = _mid_x(end) >= _mid_x(start)
    x0 = canvas.left(start.col + start.width if forward else start.col)
    x1 = canvas.left(end.col if forward else end.col + end.width)
    y0 = canvas.top(_mid_y(start))
    y1 = canvas.top(_mid_y(end))
    span = x1 - x0

    if abs(y1 - y0) < UNIT_Y // 2:
        segments = [(min(x0, x1), y0, abs(span) or 1, 0)]
    else:
        turn = x0 + span // 2
        segments = [
            (min(x0, turn), y0, abs(turn - x0) or 1, 0),
            (turn, min(y0, y1), 0, abs(y1 - y0) or 1),
            (min(turn, x1), y1, abs(x1 - turn) or 1, 0),
        ]

    label_w = max(abs(span), UNIT_X * 4)
    return segments, min(x0, x1), min(y0, y1) - 274320, label_w


def _route_vertical(
    canvas: Canvas,
    start: Node,
    end: Node,
) -> tuple[list[Segment], int, int, int]:
    """Route top-to-bottom (or bottom-to-top) with one elbow."""
    downward = _mid_y(end) >= _mid_y(start)
    y0 = canvas.top(start.row + start.height if downward else start.row)
    y1 = canvas.top(end.row if downward else end.row + end.height)
    x0 = canvas.left(_mid_x(start))
    x1 = canvas.left(_mid_x(end))
    span = y1 - y0

    if abs(x1 - x0) < UNIT_X // 2:
        segments = [(x0, min(y0, y1), 0, abs(span) or 1)]
    else:
        turn = y0 + span // 2
        segments = [
            (x0, min(y0, turn), 0, abs(turn - y0) or 1),
            (min(x0, x1), turn, abs(x1 - x0) or 1, 0),
            (x1, min(turn, y1), 0, abs(y1 - turn) or 1),
        ]

    return segments, min(x0, x1) + 91440, y0 + span // 2 - 137160, UNIT_X * 7


def _draw_edge(
    slide: Slide,
    canvas: Canvas,
    edge: Edge,
    nodes: dict[str, Node],
) -> None:
    """Draw an orthogonal connector between two placed nodes.

    Routing is deliberately simple and predictable: leave the source
    from whichever face points at the target, travel to the midpoint,
    turn once, and arrive at the matching face of the target. Only the
    final segment carries the arrow head, so an elbow reads as one
    connector rather than three.
    """
    start, end = nodes[edge.start], nodes[edge.end]
    side = edge.side
    if side == "auto":
        gap_x = max(
            end.col - (start.col + start.width),
            start.col - (end.col + end.width),
        )
        gap_y = max(
            end.row - (start.row + start.height),
            start.row - (end.row + end.height),
        )
        side = "h" if gap_x >= gap_y else "v"

    segments, label_x, label_y, label_w = (
        _route_horizontal(canvas, start, end)
        if side == "h"
        else _route_vertical(canvas, start, end)
    )
    for index, (sx, sy, sw, sh) in enumerate(segments):
        line(
            slide,
            x=sx,
            y=sy,
            w=sw,
            h=sh,
            colour=P.faint,
            dashed=edge.dashed,
            arrow=index == len(segments) - 1,
            reverse=(
                _mid_x(end) < _mid_x(start)
                if side == "h"
                else _mid_y(end) < _mid_y(start)
            ),
        )

    if edge.label:
        per_line = max(int(label_w / (14 * 0.52 * 12700)), 1)
        label_lines = max(1, -(-len(edge.label) // per_line))
        label_h = max(365760, int(label_lines * 14 * 1.2 * 1.16 * 12700))
        if side == "h" and label_lines > 1:
            label_y -= label_h - 228600
        box = text_box(slide, x=label_x, y=label_y, w=label_w, h=label_h)
        write(
            box,
            plain(edge.label),
            size=14,
            colour=P.muted,
            align=PP_ALIGN.CENTER if side == "h" else PP_ALIGN.LEFT,
        )


def _mid_x(node: Node) -> float:
    """Grid column of a node's centre."""
    return node.col + node.width / 2


def _mid_y(node: Node) -> float:
    """Grid row of a node's centre."""
    return node.row + node.height / 2


def legend(slide: Slide, *, x: int, y: int) -> None:
    """Draw the six-mark legend the schemas share."""
    entries = (
        ("process", "step your code runs"),
        ("state", "survives a restart"),
        ("decision", "a branch"),
        ("solid", "this repo runs it"),
        ("dashed", "needs your resource"),
    )
    for index, (mark, meaning) in enumerate(entries):
        top = y + index * 320040
        box = text_box(slide, x=x, y=top, w=3200400, h=274320)
        write(
            box,
            [
                (f"{mark}  ", {"bold": True, "colour": P.ink_soft}),
                (meaning, {"colour": P.muted}),
            ],
            size=13,
            colour=P.muted,
        )


def code_lines(
    slide: Slide,
    lines: list[list[tuple[str, str]]],
    *,
    x: int,
    y: int,
    w: int,
    h: int,
    size: float = 14,
) -> None:
    """Write syntax-highlighted code onto a dark panel.

    Args:
        slide: Target slide.
        lines: One list of ``(text, colour)`` runs per line.
        x: Left edge.
        y: Top edge.
        w: Width.
        h: Height.
        size: Point size. 14 fits about 62 characters per line in the
            wide column, 12 in the narrow one.
    """
    box = text_box(slide, x=x, y=y, w=w, h=h)
    for index, runs in enumerate(lines):
        write(
            box,
            [(text, {"colour": colour}) for text, colour in runs]
            or [(" ", {"colour": P.code_fg})],
            size=size,
            colour=P.code_fg,
            font=FONT_CODE,
            line_spacing=1.22,
            first=index == 0,
        )


def panel_label(slide: Slide, text: str, *, x: int, y: int, w: int) -> None:
    """Write the small caption that sits above a code panel."""
    box = text_box(slide, x=x, y=y, w=w, h=256032)
    write(box, plain(text.upper()), size=11, colour=P.code_dim, bold=True)


def pt(value: float) -> Pt:
    """Expose ``Pt`` so slide modules need not import pptx directly."""
    return Pt(value)


@dataclass(frozen=True)
class LineageNode:
    """A lineage label with an optional dated chip."""

    label: str
    date: str = ""


@dataclass(frozen=True)
class LineageChain:
    """A compact sequence inside one side of a lineage row."""

    nodes: tuple[LineageNode, ...]
    relation: str = "rename"


LineageSide = list[str | LineageNode] | LineageChain
LineageRow = tuple[LineageSide, str, LineageSide, str]


def _lineage_arrow(
    slide: Slide,
    *,
    x: int,
    y: int,
    w: int,
    relation: str,
    colour: str,
) -> None:
    """Point dependency relations back to the service they depend on."""
    from pptx.oxml.ns import qn

    shape = line(
        slide,
        x=x,
        y=y,
        w=w,
        h=0,
        colour=colour,
        dashed=relation in {"built on", "extends", "used by"},
    )
    if relation in {"built on", "extends"}:
        arrow = shape._element.spPr.find(".//" + qn("a:tailEnd"))
        if arrow is not None:
            arrow.tag = qn("a:headEnd")


def lineage(
    slide: Slide, rows: list[LineageRow], *, x: int, y: int, w: int
) -> int:
    """Draw evenly spaced evolution rows and the relation legend.

    Lists combine nodes with a plus. A LineageChain instead shows
    sequential labelled relations within the same row. Dashed arrows
    mean composition or inheritance, never replacement.
    """
    from theme import Y_FOOTER

    relation_words = {
        "rename",
        "successor",
        "migration",
        "merged into",
        "built on",
        "extends",
        "used by",
    }
    pitch = min(777240, (Y_FOOTER - 914400 - y) // len(rows))
    left_w = int(w * 0.34)
    arrow_w = int(w * 0.10)
    after_w = int(w * 0.29)
    note_x = x + left_w + arrow_w + after_w + 182880
    note_w = x + w - note_x

    def side(nodes: LineageSide, left: int, top: int, width: int) -> None:
        """Place labels with explicit intermediate links."""
        chain = isinstance(nodes, LineageChain)
        items = nodes.nodes if chain else nodes
        gap = 731520 if chain else 182880
        available = width - gap * (len(items) - 1)
        # Long API signatures get more space than short product names.
        labels = [n if isinstance(n, str) else n.label for n in items]
        weights = [max(12, len(label)) for label in labels]
        offset = left
        for index, item in enumerate(items):
            node = LineageNode(item) if isinstance(item, str) else item
            node_w = int(available * weights[index] / sum(weights))
            box = rounded(
                slide,
                x=offset,
                y=top + 45720,
                w=node_w,
                h=pitch - 137160,
                fill=P.wash,
                line=P.rule,
            )
            frame = box.text_frame
            frame.margin_left = frame.margin_right = Emu(45720)
            frame.margin_top = frame.margin_bottom = 0
            frame.vertical_anchor = MSO_ANCHOR.MIDDLE
            label_box = box
            if node.date:
                label_box = text_box(
                    slide,
                    x=offset + 45720,
                    y=top + 45720,
                    w=node_w - 91440,
                    h=pitch - 393192,
                    anchor=MSO_ANCHOR.MIDDLE,
                )
            write(
                label_box,
                plain(node.label),
                size=15,
                colour=P.ink_soft,
                bold=True,
                align=PP_ALIGN.CENTER,
                line_spacing=1.05,
            )
            if node.date:
                date_w = min(
                    node_w - 91440,
                    int(len(node.date) * 15 * 0.52 * 12700) + 182880,
                )
                chip = rounded(
                    slide,
                    x=offset + (node_w - date_w) // 2,
                    y=top + pitch - 347472,
                    w=date_w,
                    h=228600,
                    fill=P.rule,
                    line=None,
                    radius=50000,
                )
                chip.text_frame.margin_left = 0
                chip.text_frame.margin_right = 0
                chip.text_frame.margin_top = 0
                chip.text_frame.margin_bottom = 0
                chip.text_frame.vertical_anchor = MSO_ANCHOR.MIDDLE
                write(
                    chip,
                    plain(node.date),
                    size=15,
                    colour=P.muted,
                    align=PP_ALIGN.CENTER,
                    line_spacing=1.05,
                )
            offset += node_w
            if index < len(items) - 1:
                tag = text_box(
                    slide,
                    x=offset,
                    y=top + 91440,
                    w=gap,
                    h=pitch - 182880,
                    anchor=MSO_ANCHOR.MIDDLE,
                )
                write(
                    tag,
                    plain(nodes.relation if chain else "+"),
                    size=13 if chain else 15,
                    colour=P.muted,
                    align=PP_ALIGN.CENTER,
                )
                if chain:
                    _lineage_arrow(
                        slide,
                        x=offset + 45720,
                        y=top + pitch - 182880,
                        w=gap - 91440,
                        colour=P.faint,
                        relation=nodes.relation,
                    )
                offset += gap

    for index, (before, relation, after, note) in enumerate(rows):
        if relation not in relation_words:
            message = f"Unknown lineage relation: {relation}"
            raise ValueError(message)
        top = y + index * pitch
        side(before, x, top, left_w)
        side(after, x + left_w + arrow_w, top, after_w)
        arrow_x = x + left_w + 91440
        tag = text_box(
            slide, x=arrow_x, y=top + 137160, w=arrow_w - 182880, h=274320
        )
        write(
            tag,
            plain(relation),
            size=13,
            colour=P.blue,
            bold=True,
            align=PP_ALIGN.CENTER,
        )
        _lineage_arrow(
            slide,
            x=arrow_x,
            y=top + pitch - 228600,
            w=arrow_w - 182880,
            colour=P.blue,
            relation=relation,
        )
        box = text_box(
            slide,
            x=note_x,
            y=top + 45720,
            w=note_w,
            h=pitch - 91440,
            anchor=MSO_ANCHOR.MIDDLE,
        )
        write(box, plain(note), size=13, colour=P.muted, line_spacing=1.05)
    bottom = y + len(rows) * pitch + 45720
    for left, dashed, text in (
        (x, False, "rename / successor / migration / merged into"),
        (
            x + w // 2,
            True,
            "built on / extends / used by: relationship, not replacement",
        ),
    ):
        line(
            slide,
            x=left,
            y=bottom + 137160,
            w=548640,
            h=0,
            colour=P.blue,
            dashed=dashed,
        )
        box = text_box(
            slide, x=left + 685800, y=bottom, w=w // 2 - 685800, h=365760
        )
        write(box, plain(text), size=13, colour=P.muted)
    return bottom + 365760

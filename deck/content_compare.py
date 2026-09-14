"""The comparison: one customer task, two implementations.

Same brief, same budget, same computed checks, two frameworks. The
argument is never "AutoGen cannot": both lanes pause, survive a real
process boundary and refuse to act twice. The difference is which
responsibilities the framework owns and which stay in application
code, and every figure here comes from ``deck/facts.json``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import components as C
import diagrams as D
import theme as T
from theme import P, plain, text_box, write

from msai_demo.providers import PROVIDER_CONFIGS

if TYPE_CHECKING:
    from facts import Facts
    from pptx.presentation import Presentation

CODE_W = 7635240
RIGHT_X = 9345168
RIGHT_W = 7498080

LANES = (
    ("autogen", "AutoGen", P.amber),
    ("agent-framework", "Agent Framework", P.teal),
)

CHECKS = (
    ("schema_valid", "the proposal validates against a Pydantic model"),
    ("sources_valid", "every cited section exists in the corpus"),
    ("no_action_before_approval", "in the event log, approval comes first"),
    ("survived_process_boundary", "the resume ran in another PID, from disk"),
    ("idempotent_second_resume", "a replayed resume executes nothing"),
)


def slide_section(prs: Presentation, facts: Facts) -> None:
    """Divider for the comparison section."""
    del facts
    T.section_slide(
        prs,
        index="04",
        eyebrow="the comparison",
        title_lines=["One customer task,", "two implementations"],
        deck=(
            "Same brief and acceptance rules; framework-specific "
            "adapters. One approval gate, one restart, one replay."
        ),
        bullets=(
            "The experiment",
            "Side by side",
            "Restart evidence",
            "Who owns what",
        ),
        number=18,
    )


def slide_experiment(prs: Presentation, facts: Facts) -> None:
    """The experimental setup and vocabulary, before any result."""
    slide = T.content_slide(
        prs,
        eyebrow="the experiment",
        title="Two vendors, one reviewable proposal",
        deck=(
            "A solution architect on OpenAI drafts. A risk reviewer on "
            "Anthropic challenges. Neither may accept the work alone."
        ),
        number=19,
    )
    C.run_strip(slide, "group-chat")

    cost = facts.pilot_cost
    openai = PROVIDER_CONFIGS["openai"]
    anthropic = PROVIDER_CONFIGS["anthropic"]
    C.table(
        slide,
        ("Held constant", "Value"),
        (
            ("Brief", "Six-week customer-support agent pilot"),
            ("Budget", f"{cost['budget']:,} USD, fictional"),
            ("Architect", f"OpenAI, {openai.default_model} by default"),
            ("Reviewer", f"Anthropic, {anthropic.default_model} by default"),
            ("Turn budget", "4 speaking rounds, hard cap"),
            ("Costing", "scenario.price_pilot(), both lanes"),
            ("Action", "accept_proposal, a simulated business action"),
            ("Offline", "AutoGen replay client; a BaseChatClient subclass"),
        ),
        x=T.MARGIN_L,
        y=T.Y_BODY,
        w=CODE_W,
        widths=(1.4, 3.0),
        row_h=429768,
        size=14.5,
    )

    C.callout(
        slide,
        "Every check is computed from the proposal, the event log and OS "
        "process ids. None of them is typed into a slide.",
        x=T.MARGIN_L,
        y=T.Y_BODY + 4206240,
        w=CODE_W,
        accent=P.teal,
        size=15,
    )

    label = text_box(slide, x=RIGHT_X, y=T.Y_BODY, w=RIGHT_W, h=320040)
    write(
        label,
        plain("THREE WORDS FIRST"),
        size=12.5,
        colour=P.faint,
        bold=True,
    )
    C.steps(
        slide,
        (
            ("A", "Agent", "A model client, instructions, tools, a session."),
            ("W", "Workflow", "Explicit execution steps between agents."),
            ("C", "Checkpoint", "Saved workflow state, pending requests too."),
        ),
        x=RIGHT_X,
        y=T.Y_BODY + 411480,
        w=RIGHT_W,
        accent=P.teal,
        step_h=777240,
    )

    C.table(
        slide,
        ("Computed in both lanes", "What it measures"),
        CHECKS,
        x=RIGHT_X,
        y=T.Y_BODY + 2926080,
        w=RIGHT_W,
        widths=(2.7, 3.3),
        row_h=457200,
        size=13,
        mono_columns=(0,),
    )


def slide_side_by_side(prs: Presentation, facts: Facts) -> None:
    """The two approval paths, next to each other."""
    slide = T.content_slide(
        prs,
        eyebrow="side by side",
        title="Built-in approval and checkpoints reduce plumbing",
        deck=(
            "Same task, same checks. AutoGen's application code saves and "
            "restores the approval; Agent Framework's checkpoint already "
            "holds the pending request."
        ),
        number=20,
        accent=P.teal,
    )
    C.run_strip(slide, "group-chat")

    autogen_code = [
        [("# parent process: your code saves both halves", P.code_dim)],
        [("await", P.sky), (" save_team_state(team, run_dir)", P.code_fg)],
        [("save_pending_approval(run_dir, proposal, sha)", P.code_fg)],
        [],
        [("# resume process: your code restores and gates", P.code_dim)],
        [
            ("state = read_json(run_dir / ", P.code_fg),
            ('"team-state.json"', P.yellow),
            (")", P.code_fg),
        ],
        [
            ("pending = read_json(run_dir / ", P.code_fg),
            ('"pending-approval.json"', P.yellow),
            (")", P.code_fg),
        ],
        [("await", P.sky), (" team.load_state(state)", P.code_fg)],
        [("apply_approval(run_dir, proposal, approve)", P.coral)],
    ]
    framework_code = [
        [
            ("@tool", P.teal),
            ("(approval_mode=", P.code_fg),
            ('"always_require"', P.yellow),
            (")", P.code_fg),
        ],
        [("def ", P.sky), ("accept(scenario_id: str) -> str: ...", P.code_fg)],
        [],
        [
            ("GroupChatBuilder", P.teal),
            ("(participants=[architect, reviewer],", P.code_fg),
        ],
        [
            ("    checkpoint_storage=", P.code_fg),
            ("FileCheckpointStorage", P.teal),
            ("(dir))", P.code_fg),
        ],
        [],
        [("# resume process: the checkpoint holds the request", P.code_dim)],
        [
            ("cp, request_id, _ = ", P.code_fg),
            ("await", P.sky),
            (" load_pending_approval(dir)", P.code_fg),
        ],
        [("workflow.run(responses={request_id: decision},", P.code_fg)],
        [("             checkpoint_id=cp.checkpoint_id, ...)", P.code_fg)],
    ]
    panels = (
        (
            "autogen",
            T.MARGIN_L,
            CODE_W,
            f"AutoGen {facts.autogen_version}  -  API excerpt, "
            "autogen_demo.py",
            autogen_code,
        ),
        (
            "agent-framework",
            RIGHT_X,
            RIGHT_W,
            f"Agent Framework {facts.af_version}  -  API excerpt, "
            "group_chat_demo.py",
            framework_code,
        ),
    )
    colours = {lane: colour for lane, _, colour in LANES}
    names = {lane: name for lane, name, _ in LANES}
    for lane, left, width, caption, lines in panels:
        T.code_panel(slide, x=left, y=T.Y_BODY, w=width, h=3749040)
        D.panel_label(
            slide,
            caption,
            x=left + 310896,
            y=T.Y_BODY + 182880,
            w=width - 548640,
        )
        D.code_lines(
            slide,
            lines,
            x=left + 310896,
            y=T.Y_BODY + 548640,
            w=width - 548640,
            h=3017520,
            size=13,
        )
        run = _lane_run(facts, lane)
        colour = colours[lane]
        C.table(
            slide,
            (f"{names[lane]}, recorded", "Value"),
            (
                ("turns with text", str(len(run["turns"]))),
                ("tool calling", str(run["tool_calling"]).split(":")[0]),
                (
                    "approval stored in",
                    str(run["approval"]["storage"]).split(" in ")[0],
                ),
            ),
            x=left,
            y=T.Y_BODY + 3931920,
            w=width,
            widths=(1.8, 3.0),
            row_h=393192,
            size=13,
            accents=(colour, colour, colour),
            mono_columns=(1,),
        )

    C.callout(
        slide,
        facts.verdict,
        x=T.MARGIN_L,
        y=T.Y_BODY + 5486400,
        w=T.CONTENT_W,
        accent=P.teal,
        size=14,
    )


def slide_approval(prs: Presentation, facts: Facts) -> None:
    """Approval as a persisted state transition, both lanes."""
    del facts
    slide = T.content_slide(
        prs,
        eyebrow="human control",
        title="Approval is a state transition, not a callback",
        deck=(
            "Both lanes stop before the simulated business action and "
            "write the pending decision to disk. They differ in who "
            "defines that record."
        ),
        number=22,
    )
    C.run_strip(slide, "group-chat")

    nodes: list[D.Node] = []
    edges: list[D.Edge] = []
    lanes = (
        (
            "a",
            0.0,
            P.amber,
            ("team.run()", "pending-approval.json", "apply_approval()"),
        ),
        (
            "b",
            7.0,
            P.teal,
            ("workflow.run()", "checkpoints/*.json", "run(responses=)"),
        ),
    )
    for prefix, row, colour, (start, record, resume) in lanes:
        nodes += [
            D.Node(
                f"{prefix}1",
                start,
                col=0,
                row=row,
                width=13,
                height=2.8,
                colour=colour,
                mono=True,
                sub="parent process",
            ),
            D.Node(
                f"{prefix}2",
                record,
                col=21,
                row=row - 0.2,
                width=15,
                height=3.2,
                kind="state",
                colour=colour,
                sub="on disk",
            ),
            D.Node(
                f"{prefix}3",
                resume,
                col=43,
                row=row,
                width=15,
                height=2.8,
                colour=colour,
                mono=True,
                sub="separate process",
            ),
        ]
        edges += [
            D.Edge(f"{prefix}1", f"{prefix}2", "state", side="h"),
            D.Edge(f"{prefix}2", f"{prefix}3", "decision", side="h"),
        ]
    D.draw(
        slide,
        D.Schema(
            nodes=nodes,
            edges=edges,
            boundaries=[
                D.Boundary(
                    "AutoGen: a record format you define",
                    col=-1.2,
                    row=-1.6,
                    width=60.4,
                    height=5.4,
                    colour=P.amber,
                ),
                D.Boundary(
                    "Agent Framework: the SDK's checkpoint format",
                    col=-1.2,
                    row=5.4,
                    width=60.4,
                    height=5.4,
                    colour=P.teal,
                ),
            ],
        ),
        x=T.MARGIN_L + 274320,
        y=T.Y_BODY + 365760,
    )

    C.table(
        slide,
        ("Question the auditor asks", "AutoGen lane", "Agent Framework lane"),
        (
            (
                "Where is the pending approval?",
                "pending-approval.json, your format",
                "pending_request_info_events, in the checkpoint",
            ),
            (
                "What stops the action?",
                "apply_approval(), application code",
                'the tool\'s approval_mode="always_require"',
            ),
            ("Who starts the resume?", "the application", "the application"),
            (
                "What makes a replay safe?",
                "EventStore.execute_action()",
                "EventStore.execute_action()",
            ),
        ),
        x=T.MARGIN_L,
        y=T.Y_BODY + 2743200,
        w=T.CONTENT_W,
        widths=(2.4, 2.8, 3.4),
        row_h=457200,
        size=14.5,
    )

    C.callout(
        slide,
        "If the pending decision lives only in process memory, a restart "
        "loses the approval. Both lanes avoid that here; only one of them "
        "had to invent the record to do it.",
        x=T.MARGIN_L,
        y=T.Y_BODY + 5029200,
        w=T.CONTENT_W,
        accent=P.coral,
    )


def slide_recovery(prs: Presentation, facts: Facts) -> None:
    """The measured process boundary, from the recorded event logs."""
    slide = T.content_slide(
        prs,
        eyebrow="recovery",
        title="Separate processes resume from disk; a replay does nothing",
        deck=(
            "Phase two starts a fresh Python interpreter that receives only "
            "the run directory and the decision. Then it runs once more."
        ),
        number=23,
        accent=P.teal,
    )
    C.run_strip(slide, "group-chat")

    top = T.Y_BODY
    for lane, name, colour in reversed(LANES):
        recovery = facts.recovery(lane)
        roles = {
            recovery["parent_pid"]: "parent",
            recovery["resume_pid"]: "resume",
            recovery["second_resume_pid"]: "replay",
        }
        events = _lane_run(facts, lane)["events"]
        label = text_box(slide, x=T.MARGIN_L, y=top, w=T.COL_MAIN_W, h=320040)
        write(
            label,
            plain(f"{name.upper()} - EVENT LOG, IN ORDER"),
            size=12.5,
            colour=colour,
            bold=True,
        )
        C.table(
            slide,
            ("#", "Event", "Process", "PID"),
            tuple(
                (
                    str(event["sequence"]),
                    str(event["name"]),
                    roles.get(event["pid"], "other"),
                    str(event["pid"]),
                )
                for event in events
            ),
            x=T.MARGIN_L,
            y=top + 320040,
            w=T.COL_MAIN_W,
            widths=(0.5, 3.0, 1.6, 1.2),
            row_h=338328,
            size=13.5,
            mono_columns=(1, 3),
            accents=tuple(colour for _ in events),
        )
        top += 2743200

    framework = facts.recovery("agent-framework")
    legacy = facts.recovery("autogen")
    C.rail(
        slide,
        title="Measured, not asserted",
        lines=(
            "Checkpoint files the Agent Framework resume read: "
            f"{facts.checkpoint_count}.",
            "Actions after the replay: "
            f"{legacy['second_resume_action_count']} (AutoGen), "
            f"{framework['second_resume_action_count']} (Agent Framework).",
            "The action is labelled a simulated business action.",
            "Child stderr is discarded; failures surface as codes.",
        ),
        accent=P.teal,
        h=5486400,
    )


def slide_migration_evidence(prs: Presentation, facts: Facts) -> None:
    """The responsibility matrix, as the comparison returned it."""
    slide = T.content_slide(
        prs,
        eyebrow="migration evidence",
        title="The recovery path shows who owns each responsibility",
        deck=(
            "Returned by responsibility_matrix(). A unit test imports every "
            "application function it names, so the table cannot name code "
            "that does not exist."
        ),
        number=24,
        accent=P.coral,
    )
    C.run_strip(slide, "group-chat")

    rows = facts.responsibility_matrix
    C.table(
        slide,
        ("Concern", "AutoGen", "Agent Framework"),
        tuple(
            (
                str(row["concern"]).capitalize(),
                _owner(row["autogen"]),
                _owner(row["agent-framework"]),
            )
            for row in rows
        ),
        x=T.MARGIN_L,
        y=T.Y_BODY,
        w=T.CONTENT_W,
        widths=(2.0, 3.6, 4.4),
        row_h=502920,
        size=14,
        mono_columns=(1, 2),
        accents=tuple(
            P.teal
            if str(row["agent-framework"]).startswith("framework")
            else P.ink_soft
            for row in rows
        ),
    )

    passed = {lane: sum(facts.checks(lane).values()) for lane, _, _ in LANES}
    totals = {lane: len(facts.checks(lane)) for lane, _, _ in LANES}
    C.callout(
        slide,
        facts.verdict,
        x=T.MARGIN_L,
        y=T.Y_BODY + 3749040,
        w=T.CONTENT_W,
        accent=P.teal,
        size=16,
    )
    C.callout(
        slide,
        f"Computed checks passed: AutoGen {passed['autogen']} of "
        f"{totals['autogen']}, Agent Framework "
        f"{passed['agent-framework']} of {totals['agent-framework']}. "
        "Not a capability gap: a difference in what you maintain.",
        x=T.MARGIN_L,
        y=T.Y_BODY + 4754880,
        w=T.CONTENT_W,
        accent=P.coral,
        size=16,
    )


def slide_comparison(prs: Presentation, facts: Facts) -> None:
    """The common task, vocabulary and approval paths on one slide."""
    slide = T.content_slide(
        prs,
        eyebrow="the experiment - side by side",
        title="Same task, two frameworks, one approval gate",
        deck=(
            "An agent combines a model, instructions and tools. A workflow "
            "controls the steps, and a checkpoint saves the pending work."
        ),
        number=0,
        accent=P.teal,
    )
    C.run_strip(slide, "group-chat")
    cost = facts.demo_run("group-chat-agent-framework")["cost"]
    held = text_box(slide, x=T.MARGIN_L, y=T.Y_BODY, w=T.CONTENT_W, h=548640)
    write(
        held,
        plain(
            f"HELD CONSTANT: {cost['weeks']}-week support-pilot brief, "
            f"{cost['budget']:,} USD fictional budget, source corpus, "
            "turn cap, pricing and acceptance checks. Live roles: OpenAI "
            "architect, Anthropic reviewer. Recorded mode: scripted offline."
        ),
        size=14,
        colour=P.muted,
    )
    definitions = (
        ("Agent", "A model, instructions, tools and a session."),
        ("Workflow", "Explicit execution steps between agents."),
        ("Checkpoint", "Saved workflow state, including requests."),
    )
    width = (T.CONTENT_W - 365760) // 3
    for index, (term, meaning) in enumerate(definitions):
        box = text_box(
            slide,
            x=T.MARGIN_L + index * (width + 182880),
            y=T.Y_BODY + 640080,
            w=width,
            h=457200,
        )
        write(
            box,
            [(f"{term}: ", {"bold": True}), (meaning, {})],
            size=14,
            colour=P.ink_soft,
        )
    panels = (
        (
            T.MARGIN_L,
            CODE_W,
            f"AutoGen {facts.autogen_version} - application owns the gate",
            [
                [("await save_team_state(team, run_dir)", P.code_fg)],
                [("save_pending_approval(run_dir, proposal, sha)", P.code_fg)],
                [("# separate resume process", P.code_dim)],
                [
                    (
                        'state = read_json(run_dir / "team-state.json")',
                        P.code_fg,
                    )
                ],
                [
                    (
                        "pending = read_json(run_dir / "
                        '"pending-approval.json")',
                        P.code_fg,
                    )
                ],
                [("await team.load_state(state)", P.code_fg)],
                [("apply_approval(run_dir, proposal, approve)", P.coral)],
            ],
        ),
        (
            RIGHT_X,
            RIGHT_W,
            f"Agent Framework {facts.af_version} - framework gate",
            [
                [('@tool(approval_mode="always_require")', P.teal)],
                [("def accept(scenario_id: str) -> str: ...", P.code_fg)],
                [
                    (
                        "GroupChatBuilder(participants=[architect, reviewer],",
                        P.code_fg,
                    )
                ],
                [
                    (
                        "    checkpoint_storage=FileCheckpointStorage(dir))",
                        P.code_fg,
                    )
                ],
                [
                    (
                        "cp, request_id, _ = await load_pending_approval(dir)",
                        P.code_fg,
                    )
                ],
                [
                    (
                        "workflow.run(responses={request_id: decision},",
                        P.code_fg,
                    )
                ],
                [
                    (
                        "             checkpoint_id=cp.checkpoint_id, ...)",
                        P.code_fg,
                    )
                ],
            ],
        ),
    )
    for left, panel_w, caption, lines in panels:
        T.code_panel(slide, x=left, y=T.Y_BODY + 1188720, w=panel_w, h=2423160)
        D.panel_label(
            slide,
            caption,
            x=left + 274320,
            y=T.Y_BODY + 1325880,
            w=panel_w - 548640,
        )
        D.code_lines(
            slide,
            lines,
            x=left + 274320,
            y=T.Y_BODY + 1691640,
            w=panel_w - 548640,
            h=1783080,
            size=14,
        )
    disclosure = text_box(
        slide,
        x=T.MARGIN_L,
        y=T.Y_BODY + 3703320,
        w=T.CONTENT_W,
        h=548640,
    )
    write(
        disclosure,
        plain(
            "Same brief and acceptance rules; framework-specific adapters. "
            "The demo supplies a preselected decision; --decision reject "
            "exercises rejection. accept_proposal is a simulated "
            "business action."
        ),
        size=14,
        colour=P.muted,
    )
    C.use_case(
        slide,
        who="Architect and risk reviewer prepare a client proposal",
        steps=("Draft", "Review", "A named human approves", "Accept"),
        result="Nothing is accepted without the human.",
        x=T.MARGIN_L,
        y=T.Y_BODY + 4343400,
        w=T.CONTENT_W,
        accent=P.teal,
    )


def slide_recovery_evidence(prs: Presentation, facts: Facts) -> None:
    """Recorded restart evidence beside the responsibility matrix."""
    slide = T.content_slide(
        prs,
        eyebrow="restart evidence - who owns what",
        title="Both survive a restart; they differ in who owns what",
        deck=(
            "Fresh Python processes resume from disk and replay once more. "
            "The event logs and responsibility owners below come from the "
            "recorded comparison."
        ),
        number=0,
        accent=P.teal,
    )
    C.run_strip(slide, "group-chat")
    log_w = 6812280
    matrix_x = T.MARGIN_L + log_w + 365760
    matrix_w = T.CONTENT_W - log_w - 365760
    for index, (lane, name, colour) in enumerate(LANES):
        top = T.Y_BODY + index * 2286000
        recovery = facts.recovery(lane)
        label = text_box(slide, x=T.MARGIN_L, y=top, w=log_w, h=320040)
        write(label, plain(name.upper()), size=14, colour=colour, bold=True)
        pids = text_box(
            slide,
            x=T.MARGIN_L,
            y=top + 320040,
            w=log_w,
            h=365760,
        )
        write(
            pids,
            plain(
                f"Parent {recovery['parent_pid']}  /  "
                f"resume {recovery['resume_pid']}  /  "
                f"replay {recovery['second_resume_pid']}"
            ),
            size=14,
            colour=P.muted,
        )
        events = _lane_run(facts, lane)["events"]
        C.table(
            slide,
            ("#", "Recorded event", "PID"),
            tuple(
                (
                    str(event["sequence"]),
                    str(event["name"]),
                    str(event["pid"]),
                )
                for event in events
            ),
            x=T.MARGIN_L,
            y=top + 731520,
            w=log_w,
            widths=(0.4, 3.8, 1.1),
            row_h=274320,
            size=14,
            mono_columns=(1, 2),
            accents=tuple(colour for _ in events),
        )
    rows = facts.responsibility_matrix
    C.table(
        slide,
        ("Responsibility", "AutoGen", "Agent Framework"),
        tuple(
            (
                str(row["concern"]).capitalize(),
                str(row["autogen"]).partition(":")[0].capitalize(),
                str(row["agent-framework"]).partition(":")[0].capitalize(),
            )
            for row in rows
        ),
        x=matrix_x,
        y=T.Y_BODY,
        w=matrix_w,
        widths=(2.5, 1.7, 2.1),
        row_h=502920,
        size=14,
        accents=tuple(
            P.teal
            if str(row["agent-framework"]).startswith("framework")
            else P.ink_soft
            for row in rows
        ),
    )
    verdict = text_box(
        slide,
        x=matrix_x,
        y=T.Y_BODY + 3566160,
        w=matrix_w,
        h=1005840,
    )
    write(verdict, plain(facts.verdict), size=16, colour=P.ink_soft, bold=True)
    legacy = facts.recovery("autogen")
    current = facts.recovery("agent-framework")
    C.callout(
        slide,
        f"Simulated business action. Actions after replay: "
        f"{legacy['second_resume_action_count']} (AutoGen), "
        f"{current['second_resume_action_count']} (Agent Framework). "
        f"Agent Framework read {facts.checkpoint_count} checkpoint files. "
        "The application still launches recovery and enforces idempotency.",
        x=T.MARGIN_L,
        y=T.Y_BODY + 4937760,
        w=T.CONTENT_W,
        accent=P.coral,
        size=14,
    )


def _lane_run(facts: Facts, lane: str) -> dict[str, object]:
    """One recorded group-chat lane, by implementation name."""
    return facts.demo_run(
        "autogen" if lane == "autogen" else "group-chat-agent-framework"
    )


def _owner(cell: str) -> str:
    """Shorten ``owner: dotted.path`` to the recognisable part."""
    owner, _, target = cell.partition(": ")
    if owner == "application":
        target = target.rsplit(".", 1)[-1] + "()"
    else:
        target = target.removeprefix("agent_framework.")
    return f"{owner}: {target}"


def _short(text: str, limit: int) -> str:
    """Trim recorded text to fit a card, marking the cut."""
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 3].rstrip() + "..."

"""One entry point for every demo in the workshop.

The registry below is the table of contents for the whole repository:
one row per technology, each naming the module that teaches it. Adding
a technology is one row plus one module.

Run it:

    uv run msai-demo list
    uv run msai-demo all --format json
"""

from __future__ import annotations

import argparse
import asyncio
import importlib
import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, Protocol, cast

from rich.console import Console
from rich.table import Table

from msai_demo.contracts import DemoResult, batch
from msai_demo.runtime import configure_telemetry, load_env_file

if TYPE_CHECKING:
    from collections.abc import Sequence


@dataclass(frozen=True)
class Demo:
    """One row of the workshop's table of contents.

    Attributes:
        name: CLI command, and the ``demo`` field in the result.
        module: Module under ``msai_demo`` that implements it.
        runner: Async function in that module.
        lane: ``legacy``, ``current`` or ``shared``.
        technology: What the slide calls it.
        summary: One line for ``msai-demo list``.
    """

    name: str
    module: str
    runner: str
    lane: str
    technology: str
    summary: str


DEMOS: Final[tuple[Demo, ...]] = (
    # --- the legacy estate -------------------------------------------
    Demo(
        "autogen",
        "autogen_demo",
        "run_autogen_demo",
        "legacy",
        "AutoGen",
        "Round-robin group chat, termination, team state.",
    ),
    Demo(
        "semantic-kernel",
        "semantic_kernel_demo",
        "run_semantic_kernel_demo",
        "legacy",
        "Semantic Kernel",
        "Kernel, plugin and filter - and the pin that caps your SDK.",
    ),
    Demo(
        "bot-framework",
        "bot_framework_demo",
        "run_bot_framework_demo",
        "legacy",
        "Bot Framework SDK",
        "One channel activity through the retired adapter.",
    ),
    Demo(
        "promptflow",
        "promptflow_demo",
        "run_promptflow_demo",
        "legacy",
        "prompt flow",
        "A small local DAG flow, and its OpenTelemetry pin conflict.",
    ),
    Demo(
        "azure-ai-inference",
        "azure_ai_inference_demo",
        "run_azure_ai_inference_demo",
        "legacy",
        "azure-ai-inference",
        "The stalled beta request, beside its replacement.",
    ),
    Demo(
        "content-safety",
        "content_safety_demo",
        "run_content_safety_demo",
        "legacy",
        "Azure AI Content Safety",
        "Classify one prompt yourself, then apply a threshold.",
    ),
    # --- the current runtime -----------------------------------------
    Demo(
        "agent-framework",
        "agent_framework_demo",
        "run_agent_framework_demo",
        "current",
        "Microsoft Agent Framework",
        "Agent, session, tool, streaming, structured output, RAG.",
    ),
    Demo(
        "group-chat",
        "group_chat_demo",
        "run_group_chat_demo",
        "shared",
        "Group chat: AutoGen vs Agent Framework",
        "The same task on both lanes, with the ownership diff.",
    ),
    Demo(
        "workflow",
        "workflow_demo",
        "run_workflow_demo",
        "current",
        "Agent Framework Workflows",
        "Typed graph, conditional edge, approval pause, checkpoints.",
    ),
    Demo(
        "harness",
        "harness_demo",
        "run_harness_demo",
        "current",
        "Agent Framework Harness",
        "Planning, todos, memory, compaction, tool approval.",
    ),
    # --- channels and protocols --------------------------------------
    Demo(
        "m365-agents",
        "m365_agents_demo",
        "run_m365_agents_demo",
        "current",
        "Microsoft 365 Agents SDK",
        "The same handler, a new adapter. Bot Framework's successor.",
    ),
    Demo(
        "mcp",
        "mcp_demo",
        "run_mcp_demo",
        "current",
        "Model Context Protocol",
        "Discover and call a tool over MCP.",
    ),
    Demo(
        "a2a",
        "a2a_demo",
        "run_a2a_demo",
        "current",
        "Agent2Agent",
        "Delegate a task, track status, collect an artifact.",
    ),
    # --- Microsoft Foundry -------------------------------------------
    Demo(
        "azure-ai-projects",
        "azure_ai_projects_demo",
        "run_azure_ai_projects_demo",
        "current",
        "azure-ai-projects (Foundry control plane)",
        "List model deployments through AIProjectClient.",
    ),
    Demo(
        "foundry-models",
        "foundry_models_demo",
        "run_foundry_models_demo",
        "current",
        "Foundry Models",
        "FoundryChatClient, its hosted tools and their lifecycle.",
    ),
    Demo(
        "foundry-agent-service",
        "foundry_agent_service_demo",
        "run_foundry_agent_service_demo",
        "current",
        "Foundry Agent Service",
        "When the service owns the agent, not your process.",
    ),
    Demo(
        "foundry-local",
        "foundry_local_demo",
        "run_foundry_local_demo",
        "current",
        "Foundry Local",
        "Inference on the laptop, through an OpenAI-compatible port.",
    ),
    Demo(
        "ai-search",
        "ai_search_demo",
        "run_ai_search_demo",
        "current",
        "Azure AI Search",
        "Hybrid query and citations over an index you own.",
    ),
    Demo(
        "foundry-iq",
        "foundry_iq_demo",
        "run_foundry_iq_demo",
        "current",
        "Foundry IQ",
        "One knowledge endpoint across enterprise sources.",
    ),
    Demo(
        "foundry-guardrails",
        "foundry_guardrails_demo",
        "run_foundry_guardrails_demo",
        "current",
        "Foundry guardrails",
        "Four intervention points, not one prompt classification.",
    ),
    # --- identity, operations, quality --------------------------------
    Demo(
        "azure-identity",
        "azure_identity_demo",
        "run_azure_identity_demo",
        "current",
        "Microsoft Entra workload identity",
        "Real tokens, and the authorisation gate behind them.",
    ),
    Demo(
        "entra-agent-id",
        "entra_agent_id_demo",
        "run_entra_agent_id_demo",
        "current",
        "Microsoft Entra Agent ID",
        "An agent as a governable directory object.",
    ),
    Demo(
        "otel",
        "observability_demo",
        "run_observability_demo",
        "current",
        "OpenTelemetry GenAI conventions",
        "The span tree a run produces, and the opt-in export.",
    ),
    Demo(
        "evaluation",
        "evaluation_demo",
        "run_evaluation_demo",
        "current",
        "azure-ai-evaluation",
        "A dataset, two evaluators, and one failing case on purpose.",
    ),
)

DEMOS_BY_NAME: Final[dict[str, Demo]] = {demo.name: demo for demo in DEMOS}

# Flags that only some demos accept. Passing one to a demo that does
# not take it is a usage error, not a silently ignored argument.
_EXTRA_FLAGS: Final[dict[str, tuple[str, ...]]] = {
    "group-chat": ("implementation", "max_rounds", "approve"),
    "autogen": ("max_turns", "approve"),
    "otel": ("trace",),
}

# Parser attributes and batch dispatch share these defaults. In
# particular, running all demos must capture the same spans as otel.
_EXTRA_DEFAULTS: Final[dict[str, str | int]] = {
    "implementation": "both",
    "max_rounds": 4,
    "max_turns": 4,
    "decision": "approve",
    "trace": "local",
}


class _DemoRunner(Protocol):
    """The typed boundary for a lazily imported demo runner."""

    async def __call__(self, **kwargs: object) -> DemoResult:
        """Run a demo with only its registered arguments."""


def build_parser() -> argparse.ArgumentParser:
    """Build the parser used by the console script and the tests."""
    parser = argparse.ArgumentParser(
        prog="msai-demo",
        description=(
            "A runnable tour of the Microsoft AI stack: Agent "
            "Framework, Microsoft Foundry, and the legacy lane they "
            "replace."
        ),
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("list", help="Show every demo in the workshop.")

    doctor = subparsers.add_parser(
        "doctor",
        help="Packages, credentials and per-demo readiness.",
    )
    doctor.add_argument("--packages", action="store_true")
    doctor.add_argument("--demo", default=None)
    doctor.add_argument(
        "--probe",
        action="store_true",
        help="Ask Microsoft Entra for one token per audience.",
    )

    for demo in DEMOS:
        command = subparsers.add_parser(demo.name, help=demo.summary)
        _add_common(command)
        extras = _EXTRA_FLAGS.get(demo.name, ())
        if "implementation" in extras:
            command.add_argument(
                "--implementation",
                choices=("autogen", "agent-framework", "both"),
                default=_EXTRA_DEFAULTS["implementation"],
            )
        if "max_rounds" in extras:
            command.add_argument(
                "--max-rounds", type=int, default=_EXTRA_DEFAULTS["max_rounds"]
            )
        if "max_turns" in extras:
            command.add_argument(
                "--max-turns", type=int, default=_EXTRA_DEFAULTS["max_turns"]
            )
        if "approve" in extras:
            command.add_argument(
                "--decision",
                choices=("approve", "reject"),
                default=_EXTRA_DEFAULTS["decision"],
            )
        if "trace" in extras:
            command.add_argument(
                "--trace",
                choices=("off", "local", "azure"),
                default=_EXTRA_DEFAULTS["trace"],
            )

    run_all = subparsers.add_parser(
        "all",
        help="Run every demo in one lane, or all of them.",
    )
    _add_common(run_all)
    run_all.add_argument(
        "--lane",
        choices=("legacy", "current", "all"),
        default="all",
    )
    return parser


def _add_common(parser: argparse.ArgumentParser) -> None:
    """Add the flags every demo command accepts."""
    parser.add_argument(
        "--execution",
        choices=("offline", "live"),
        default="offline",
        help=(
            "offline runs real code with no credential; live calls the "
            "real service and never silently falls back."
        ),
    )
    parser.add_argument(
        "--format",
        choices=("pretty", "json"),
        default="pretty",
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Run the requested command and return a process exit code.

    Returns:
        ``0`` when the requested path succeeded or paused on purpose,
        ``1`` when it was blocked or failed, ``2`` for a usage error.
    """
    args = build_parser().parse_args(argv)
    console = Console()
    # Shell variables win; the file only fills the gaps.
    load_env_file()

    if args.command == "list":
        console.print(_list_table())
        return 0

    if args.command == "doctor":
        from msai_demo.doctor import run_doctor

        ready = run_doctor(
            console,
            packages_only=args.packages,
            demo=args.demo,
            probe=args.probe,
        )
        return 0 if ready else 1

    # Ordinary demos, including the parent of all, keep instrumentation
    # off before any SDK import. OTel captures in its isolated worker;
    # its shared default must not enable ambient exporters for all.
    configure_telemetry(
        enabled=args.command == "otel" and _extra_value(args, "trace") != "off"
    )

    if args.command == "all":
        return _run_all(args, console)

    demo = DEMOS_BY_NAME[args.command]
    try:
        result = asyncio.run(_invoke(demo, args))
    except ModuleNotFoundError as error:
        console.print(f"[red]{demo.name} is not available:[/red] {error}")
        return 1
    _emit(result, console, args.format)
    return _exit_code(result)


def _run_all(args: argparse.Namespace, console: Console) -> int:
    """Run a whole lane and report one batch result."""
    selected = [
        demo
        for demo in DEMOS
        if args.lane == "all" or demo.lane in {args.lane, "shared"}
    ]
    children: list[DemoResult] = []
    for demo in selected:
        console.rule(f"{demo.name} - {demo.technology}")
        try:
            children.append(asyncio.run(_invoke(demo, args)))
        except ModuleNotFoundError as error:
            console.print(f"[red]skipped {demo.name}:[/red] {error}")
    envelope = batch(
        demo="all",
        headline=f"Ran {len(children)} demos in lane {args.lane!r}.",
        children=children,
    )
    _emit(envelope, console, args.format)
    return _exit_code(envelope)


async def _invoke(demo: Demo, args: argparse.Namespace) -> DemoResult:
    """Import a demo module lazily and call its runner.

    ``all`` reaches this function too, and its parser deliberately does
    not define the per-demo flags. So every extra falls back to the
    same default its own subcommand advertises, rather than assuming
    the attribute is there.
    """
    module = importlib.import_module(f"msai_demo.{demo.module}")
    runner = cast("_DemoRunner", getattr(module, demo.runner))
    kwargs: dict[str, object] = {"execution": args.execution}

    for name in _EXTRA_FLAGS.get(demo.name, ()):
        if name == "approve":
            kwargs[name] = _extra_value(args, "decision") == "approve"
        else:
            kwargs[name] = _extra_value(args, name)

    return await runner(**kwargs)


def _extra_value(args: argparse.Namespace, name: str) -> str | int:
    """Resolve a per-demo flag identically for single and batch runs."""
    return cast("str | int", getattr(args, name, _EXTRA_DEFAULTS[name]))


def _exit_code(result: DemoResult) -> int:
    """Map a result status onto a process exit code."""
    return 1 if result["status"] in {"blocked", "error"} else 0


def _emit(result: DemoResult, console: Console, output: str) -> None:
    """Print a result as JSON, or as a readable summary."""
    if output == "json":
        console.print_json(json.dumps(result, default=str))
        return

    colour = {
        "ok": "green",
        "paused": "yellow",
        "blocked": "yellow",
        "error": "red",
    }[result["status"]]
    console.print(
        f"[bold]{result['technology']}[/bold]  "
        f"[{colour}]{result['status']}[/{colour}]  "
        f"mode=[cyan]{result['mode']}[/cyan]"
    )
    console.print(result["headline"])
    if result["error"]:
        console.print(
            f"[red]{result['error']['code']}[/red]: "
            f"{result['error']['message']}"
        )
    for step in result["next_steps"]:
        console.print(f"  [dim]next:[/dim] {step}")
    console.print_json(json.dumps(result["data"], default=str))


def _list_table() -> Table:
    """Build the table of contents for the whole workshop."""
    table = Table(title="Microsoft AI stack workshop", show_header=True)
    table.add_column("Command")
    table.add_column("Lane")
    table.add_column("Technology")
    table.add_column("What it shows")
    for demo in DEMOS:
        colour = {"legacy": "yellow", "current": "green"}.get(
            demo.lane, "cyan"
        )
        table.add_row(
            demo.name,
            f"[{colour}]{demo.lane}[/{colour}]",
            demo.technology,
            demo.summary,
        )
    return table


if __name__ == "__main__":
    raise SystemExit(main())

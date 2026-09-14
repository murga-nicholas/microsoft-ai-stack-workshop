"""Readiness checks that never print a credential value.

Nothing kills a live demo like a missing key, and nothing kills
credibility like a green tick that means nothing. ``doctor`` answers
three questions in about two seconds:

1. Which packages are installed, and at which versions?
2. Which credentials are *present*? Presence only - whether a key
   authenticates is something the first real call decides.
3. Which demos can run live on this machine right now, and which will
   fall back to an honest offline path?

It reports booleans and version strings. It never reports a secret.

Run it:

    uv run msai-demo doctor
"""

from __future__ import annotations

import importlib.metadata
import sys
from typing import TYPE_CHECKING, Final, Protocol, TypedDict

from rich.table import Table

from msai_demo.runtime import env_is_present

if TYPE_CHECKING:
    from collections.abc import Callable

    from rich.console import Console

# Every package the workshop talks about, in the order the deck does.
# ``lane`` drives the colour in the table and the story on the slide.
PACKAGES: Final[tuple[tuple[str, str], ...]] = (
    ("agent-framework-core", "current"),
    ("agent-framework-openai", "current"),
    ("agent-framework-anthropic", "current"),
    ("agent-framework-foundry", "current"),
    ("agent-framework-orchestrations", "current"),
    ("azure-ai-projects", "current"),
    ("azure-ai-evaluation", "current"),
    ("azure-search-documents", "current"),
    ("azure-identity", "current"),
    ("foundry-local-sdk", "current"),
    ("autogen-agentchat", "legacy"),
    ("autogen-ext", "legacy"),
    ("semantic-kernel", "legacy"),
    ("promptflow", "legacy"),
    ("azure-ai-inference", "legacy"),
    ("azure-ai-contentsafety", "legacy"),
)

# Credentials, and what each one unlocks. Order matters for the table.
CREDENTIALS: Final[tuple[tuple[str, str], ...]] = (
    ("OPENAI_API_KEY", "OpenAI participant in the group chat"),
    ("ANTHROPIC_API_KEY", "Anthropic participant in the group chat"),
    ("AZURE_TENANT_ID", "Microsoft Entra workload identity"),
    ("AZURE_CLIENT_ID", "Microsoft Entra workload identity"),
    ("AZURE_CLIENT_SECRET", "Microsoft Entra workload identity"),
    ("FOUNDRY_PROJECT_ENDPOINT", "Microsoft Foundry project calls"),
    ("AZURE_SEARCH_ENDPOINT", "Azure AI Search queries"),
    ("AZURE_CONTENT_SAFETY_ENDPOINT", "standalone Content Safety calls"),
    ("APPLICATIONINSIGHTS_CONNECTION_STRING", "Azure Monitor export"),
)

# A live path needs every variable listed here. An empty tuple means
# the demo always runs for real, with no credential at all.
LIVE_REQUIREMENTS: Final[dict[str, tuple[str, ...]]] = {
    "agent-framework": ("OPENAI_API_KEY",),
    "autogen": ("OPENAI_API_KEY", "ANTHROPIC_API_KEY"),
    "group-chat": ("OPENAI_API_KEY", "ANTHROPIC_API_KEY"),
    "workflow": (),
    "harness": (),
    "otel": (),
    "mcp": (),
    "a2a": (),
    "evaluation": (),
    "bot-framework": (),
    "promptflow": (),
    "azure-identity": (
        "AZURE_TENANT_ID",
        "AZURE_CLIENT_ID",
        "AZURE_CLIENT_SECRET",
    ),
    "azure-ai-projects": ("FOUNDRY_PROJECT_ENDPOINT",),
    "foundry-models": ("FOUNDRY_PROJECT_ENDPOINT",),
    "foundry-agent-service": ("FOUNDRY_PROJECT_ENDPOINT",),
    "foundry-iq": ("FOUNDRY_PROJECT_ENDPOINT",),
    "ai-search": ("AZURE_SEARCH_ENDPOINT",),
    "content-safety": ("AZURE_CONTENT_SAFETY_ENDPOINT",),
    "foundry-guardrails": ("FOUNDRY_PROJECT_ENDPOINT",),
    "entra-agent-id": ("FOUNDRY_PROJECT_ENDPOINT",),
    "semantic-kernel": (),
    "azure-ai-inference": (),
    "m365-agents": (),
    "foundry-local": (),
}

# Audiences the Entra probe asks for. Never printed with a token.
TOKEN_SCOPES: Final[tuple[str, ...]] = (
    "https://ai.azure.com/.default",
    "https://cognitiveservices.azure.com/.default",
    "https://search.azure.com/.default",
    "https://management.azure.com/.default",
)


class Readiness(TypedDict):
    """Machine-readable doctor output.

    Attributes:
        python: Interpreter version running the demo.
        packages: Distribution name to version, or ``not installed``.
        credentials: Variable name to presence. Never a value.
        demos: Demo name to whether its live path can run now.
        offline_always: Demos that run for real with no credential.
        tokens: Audience to probe outcome, when ``--probe`` ran.
    """

    python: str
    packages: dict[str, str]
    credentials: dict[str, bool]
    demos: dict[str, bool]
    offline_always: list[str]
    tokens: dict[str, str]


def package_versions() -> dict[str, str]:
    """Return installed versions for every workshop package."""
    versions: dict[str, str] = {}
    for name, _lane in PACKAGES:
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            versions[name] = "not installed"
    return versions


def credential_presence() -> dict[str, bool]:
    """Return presence flags for every credential the repo reads."""
    return {name: env_is_present(name) for name, _use in CREDENTIALS}


def demo_readiness(credentials: dict[str, bool]) -> dict[str, bool]:
    """Return whether each demo's live path can run right now."""
    return {
        demo: all(credentials.get(name, False) for name in required)
        for demo, required in sorted(LIVE_REQUIREMENTS.items())
    }


class CredentialPort(Protocol):
    """Acquire a token without exposing its value to the report."""

    def get_token(self, scope: str) -> object:
        """Request one audience; the report immediately discards it."""


def create_environment_credential() -> CredentialPort:
    """Load the optional identity SDK only for an explicit probe."""
    from azure.identity import EnvironmentCredential

    return EnvironmentCredential()


def probe_tokens(
    *,
    credential_factory: Callable[[], CredentialPort] = (
        create_environment_credential
    ),
) -> dict[str, str]:
    """Ask Microsoft Entra for one token per audience.

    This is the only network call ``doctor`` ever makes, and it only
    happens with ``--probe``. The token itself is discarded
    immediately; only the audience and the outcome are reported.

    Args:
        credential_factory: Optional SDK adapter, injected by tests.

    Returns:
        Audience to ``acquired`` or a short failure reason.
    """
    outcomes: dict[str, str] = {}
    try:
        credential = credential_factory()
    except ImportError:
        return dict.fromkeys(TOKEN_SCOPES, "azure-identity not installed")
    for scope in TOKEN_SCOPES:
        try:
            credential.get_token(scope)
        except Exception as error:  # report the failure, never crash
            outcomes[scope] = f"failed: {type(error).__name__}"
        else:
            outcomes[scope] = "acquired"
    return outcomes


def collect_readiness(
    *,
    probe: bool = False,
    credential_factory: Callable[[], CredentialPort] = (
        create_environment_credential
    ),
) -> Readiness:
    """Gather everything ``doctor`` knows, without printing it."""
    credentials = credential_presence()
    return {
        "python": ".".join(map(str, sys.version_info[:3])),
        "packages": package_versions(),
        "credentials": credentials,
        "demos": demo_readiness(credentials),
        "offline_always": sorted(
            demo
            for demo, required in LIVE_REQUIREMENTS.items()
            if not required
        ),
        "tokens": (
            probe_tokens(credential_factory=credential_factory)
            if probe
            else {}
        ),
    }


def run_doctor(
    console: Console,
    *,
    packages_only: bool = False,
    demo: str | None = None,
    probe: bool = False,
    credential_factory: Callable[[], CredentialPort] = (
        create_environment_credential
    ),
) -> bool:
    """Print readiness and report whether the workshop can proceed.

    Args:
        console: Where to print.
        packages_only: Print only the package table.
        demo: Report just this one demo.
        probe: Also ask Entra for a token per audience.
        credential_factory: Optional SDK adapter, injected by tests.

    Returns:
        ``True`` when every demo can at least run its offline path,
        which is always true - that is the point of the design. The
        exit code therefore reflects the *requested* demo when
        ``demo`` is given, and otherwise reports overall sanity.
    """
    status = collect_readiness(
        probe=probe, credential_factory=credential_factory
    )

    if demo is not None:
        return _print_single_demo(console, status, demo)

    console.print(_package_table(status))
    if packages_only:
        return True

    console.print(_credential_table(status))
    console.print(_demo_table(status))
    if probe:
        console.print(_token_table(status))

    live = sum(1 for ready in status["demos"].values() if ready)
    total = len(status["demos"])
    console.print(
        f"[bold]{live}/{total}[/bold] demos can run their live path. "
        f"Every other demo still runs for real offline - see the mode "
        f"column in its output."
    )
    return True


def _package_table(status: Readiness) -> Table:
    """Build the installed-package table, legacy lane marked."""
    lanes = dict(PACKAGES)
    table = Table(title="Packages", show_header=True)
    table.add_column("Package")
    table.add_column("Installed")
    table.add_column("Lane")
    table.add_row("python", status["python"], "runtime")
    for name, version in status["packages"].items():
        lane = lanes[name]
        colour = "yellow" if lane == "legacy" else "green"
        table.add_row(name, version, f"[{colour}]{lane}[/{colour}]")
    return table


def _credential_table(status: Readiness) -> Table:
    """Build the credential table. Presence only, never a value."""
    uses = dict(CREDENTIALS)
    table = Table(title="Credentials (presence only)", show_header=True)
    table.add_column("Variable")
    table.add_column("Status")
    table.add_column("Unlocks")
    for name, present in status["credentials"].items():
        mark = "[green]present[/green]" if present else "[dim]missing[/dim]"
        table.add_row(name, mark, uses[name])
    return table


def _demo_table(status: Readiness) -> Table:
    """Build the per-demo live-path table."""
    table = Table(title="Demos", show_header=True)
    table.add_column("Demo")
    table.add_column("Live path")
    table.add_column("Needs")
    for name, ready in status["demos"].items():
        required = LIVE_REQUIREMENTS[name]
        needs = ", ".join(required) if required else "nothing"
        mark = (
            "[green]ready[/green]"
            if ready
            else "[yellow]offline only[/yellow]"
        )
        table.add_row(name, mark, needs)
    return table


def _token_table(status: Readiness) -> Table:
    """Build the Entra token-probe table. No token is ever shown."""
    table = Table(title="Microsoft Entra token probe", show_header=True)
    table.add_column("Audience")
    table.add_column("Outcome")
    for scope, outcome in status["tokens"].items():
        colour = "green" if outcome == "acquired" else "red"
        table.add_row(scope, f"[{colour}]{outcome}[/{colour}]")
    return table


def _print_single_demo(
    console: Console,
    status: Readiness,
    demo: str,
) -> bool:
    """Report one demo and return whether its live path can run."""
    if demo not in LIVE_REQUIREMENTS:
        known = ", ".join(sorted(LIVE_REQUIREMENTS))
        console.print(f"[red]Unknown demo {demo!r}.[/red] Known: {known}")
        return False

    required = LIVE_REQUIREMENTS[demo]
    ready = status["demos"][demo]
    if not required:
        console.print(
            f"[green]{demo}[/green] runs for real with no credential."
        )
        return True

    missing = [
        name for name in required if not status["credentials"].get(name)
    ]
    if ready:
        console.print(f"[green]{demo}[/green] can run its live path.")
        return True
    console.print(
        f"[yellow]{demo}[/yellow] runs offline only. Missing: "
        f"{', '.join(missing)}."
    )
    return False

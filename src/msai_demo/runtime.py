"""Shared runtime helpers: environment, providers, telemetry gate.

Nothing in this module imports a vendor SDK. That is deliberate: the
telemetry gate has to run *before* Agent Framework is imported, because
Agent Framework enables instrumentation by default from version 1.x.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Final, Literal

REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
ENV_FILE: Final[Path] = REPO_ROOT / ".env"

DEFAULT_SERVICE_NAME: Final[str] = "microsoft-ai-stack-workshop"

ProviderName = Literal[
    "openai",
    "anthropic",
    "foundry",
    "foundry-local",
    "offline",
]
DEFAULT_PROVIDER: Final[ProviderName] = "openai"
PROVIDERS: Final[tuple[ProviderName, ...]] = (
    "openai",
    "anthropic",
    "foundry",
    "foundry-local",
    "offline",
)
PROVIDER_ALIASES: Final[dict[str, ProviderName]] = {
    "openai": "openai",
    "gpt": "openai",
    "anthropic": "anthropic",
    "claude": "anthropic",
    "foundry": "foundry",
    "azure": "foundry",
    "foundry-local": "foundry-local",
    "local": "foundry-local",
    "offline": "offline",
    "scripted": "offline",
}

_PLACEHOLDER_VALUES: Final[frozenset[str]] = frozenset(
    {
        "change-me",
        "change_me",
        "changeme",
        "placeholder",
        "replace-me",
        "replace_me",
        "todo",
        "your-api-key",
        "your_api_key",
        "your-key-here",
        "your_key_here",
    }
)

_TRUTHY: Final[frozenset[str]] = frozenset({"1", "on", "true", "yes"})


def load_env_file(path: Path | None = None) -> list[str]:
    """Load ``KEY=VALUE`` pairs from a local ``.env`` file.

    Values already present in the real environment always win, so a
    shell variable can still override the file during a live demo.
    Agent Framework never reads ``.env`` on its own, so this is the
    only place that file is honoured.

    Args:
        path: Optional override. Defaults to ``.env`` in the repo root.

    Returns:
        The names this call added to the environment, in file order.
        Values are never returned or logged.
    """
    env_path = path or ENV_FILE
    if not env_path.is_file():
        return []

    loaded: list[str] = []
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip().removeprefix("export ").strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, _, raw_value = line.partition("=")
        key = name.strip()
        if not key or key in os.environ:
            continue
        value = raw_value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        os.environ[key] = value
        loaded.append(key)
    return loaded


def normalize_provider(provider: str | None = None) -> ProviderName:
    """Return the canonical provider from input or ``MSAI_PROVIDER``.

    Args:
        provider: A provider name or alias. ``None`` and blank fall
            through to the environment, then to OpenAI.

    Returns:
        One of :data:`PROVIDERS`.

    Raises:
        ValueError: If the name is not a known provider or alias.
    """
    raw_value = provider if provider and provider.strip() else None
    key = raw_value or os.getenv("MSAI_PROVIDER") or DEFAULT_PROVIDER
    key = key.strip().lower()

    if key in PROVIDER_ALIASES:
        return PROVIDER_ALIASES[key]

    choices = ", ".join(PROVIDERS)
    aliases = ", ".join(PROVIDER_ALIASES)
    message = (
        f"Unknown provider {key!r}. Choose one of: {choices}. "
        f"Aliases: {aliases}."
    )
    raise ValueError(message)


def configure_telemetry(
    *,
    enabled: bool,
    service_name: str | None = None,
) -> str:
    """Turn Agent Framework instrumentation on or off.

    Agent Framework instruments agents by default, so an ordinary
    command has to opt *out* explicitly and has to do it before any
    client is constructed. Sensitive-data capture stays off either
    way: it records prompts, responses and tool arguments.

    Args:
        enabled: Whether this process may emit telemetry.
        service_name: Optional ``OTEL_SERVICE_NAME`` override.

    Returns:
        The resolved service name.
    """
    value = "true" if enabled else "false"
    os.environ["ENABLE_INSTRUMENTATION"] = value

    if not enabled:
        os.environ["ENABLE_CONSOLE_EXPORTERS"] = "false"
    os.environ.setdefault("ENABLE_SENSITIVE_DATA", "false")

    resolved = (
        service_name or os.getenv("OTEL_SERVICE_NAME") or DEFAULT_SERVICE_NAME
    )
    os.environ["OTEL_SERVICE_NAME"] = resolved
    return resolved


def env_is_present(name: str) -> bool:
    """Check that an environment value is usable without logging it.

    Blank values, obvious placeholders, ``<angle brackets>`` and
    ``${shell expansions}`` all count as missing, so a half-filled
    ``.env`` cannot make ``doctor`` look green.

    Args:
        name: The environment variable name.

    Returns:
        ``True`` when the value looks like a real setting.
    """
    value = os.getenv(name, "").strip()
    normalized = value.casefold()
    if not value or normalized in _PLACEHOLDER_VALUES:
        return False
    if normalized.startswith("<") and normalized.endswith(">"):
        return False
    if normalized.startswith("${") and normalized.endswith("}"):
        return False
    return "xxxxxxxx" not in normalized


def env_flag(name: str, *, default: bool = False) -> bool:
    """Read a boolean environment flag without raising.

    Args:
        name: The environment variable name.
        default: Value to use when the variable is unset or blank.

    Returns:
        ``True`` when the value is one of ``1``, ``on``, ``true``,
        ``yes`` (case-insensitive).
    """
    value = os.getenv(name, "").strip().casefold()
    if not value:
        return default
    return value in _TRUTHY

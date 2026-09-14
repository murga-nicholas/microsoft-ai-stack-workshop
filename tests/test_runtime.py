"""Verify environment handling without reading the workshop .env.

Run it:

    uv run pytest tests/test_runtime.py
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

import pytest

from msai_demo import runtime

if TYPE_CHECKING:
    from pathlib import Path


def test_load_env_file_handles_a_missing_file(tmp_path: Path) -> None:
    assert runtime.load_env_file(tmp_path / "missing.env") == []
    assert runtime.load_env_file(tmp_path) == []


def test_load_env_file_parses_values_and_returns_only_added_names(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    entries = {
        "MSAI_TEST_PLAIN": "plain=value",
        "MSAI_TEST_EXPORTED": "exported value",
        "MSAI_TEST_SINGLE": "single quoted",
        "MSAI_TEST_DOUBLE": "double quoted",
        "MSAI_TEST_EMPTY": "",
        "MSAI_TEST_SHORT": "a",
        "MSAI_TEST_UNBALANCED": "'open",
        "MSAI_TEST_UNQUOTED": "abba",
        "MSAI_TEST_QUOTED_EMPTY": "",
    }
    for name in entries:
        # Register missing keys so the loader's writes are undone.
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("MSAI_TEST_EXISTING", "shell-wins")
    monkeypatch.setenv("MSAI_TEST_EXISTING_BLANK", "")
    env_file = tmp_path / "test.env"
    env_file.write_text(
        "\n  # A comment\nnot an assignment\n = ignored\n"
        " MSAI_TEST_PLAIN = plain=value \n"
        " export MSAI_TEST_EXPORTED = exported value \n"
        "MSAI_TEST_SINGLE = 'single quoted'\n"
        'MSAI_TEST_DOUBLE = "double quoted"\n'
        "MSAI_TEST_EMPTY=\n"
        "MSAI_TEST_SHORT=a\n"
        "MSAI_TEST_UNBALANCED='open\n"
        "MSAI_TEST_UNQUOTED=abba\n"
        'MSAI_TEST_QUOTED_EMPTY=""\n'
        "MSAI_TEST_EXISTING=file-loses\n"
        "MSAI_TEST_EXISTING_BLANK=file-loses\n"
        "MSAI_TEST_PLAIN=duplicate-loses\n",
        encoding="utf-8",
    )

    assert runtime.load_env_file(env_file) == list(entries)
    assert {name: os.environ[name] for name in entries} == entries
    assert os.environ["MSAI_TEST_EXISTING"] == "shell-wins"
    assert os.environ["MSAI_TEST_EXISTING_BLANK"] == ""
    assert runtime.load_env_file(env_file) == []


def test_load_env_file_default_uses_the_configured_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    env_file = tmp_path / "default.env"
    env_file.write_text("MSAI_TEST_DEFAULT=fixture\n", encoding="utf-8")
    monkeypatch.setattr(runtime, "ENV_FILE", env_file)
    monkeypatch.delenv("MSAI_TEST_DEFAULT", raising=False)

    assert runtime.load_env_file() == ["MSAI_TEST_DEFAULT"]
    assert os.environ["MSAI_TEST_DEFAULT"] == "fixture"


@pytest.mark.parametrize(
    ("alias", "expected"),
    [
        ("openai", "openai"),
        ("gpt", "openai"),
        ("anthropic", "anthropic"),
        ("claude", "anthropic"),
        ("foundry", "foundry"),
        ("azure", "foundry"),
        ("foundry-local", "foundry-local"),
        ("local", "foundry-local"),
        ("offline", "offline"),
        ("scripted", "offline"),
        ("  GPT  ", "openai"),
    ],
)
def test_normalize_provider_accepts_aliases_before_environment(
    monkeypatch: pytest.MonkeyPatch, alias: str, expected: str
) -> None:
    monkeypatch.setenv("MSAI_PROVIDER", "invalid-env-provider")
    assert runtime.normalize_provider(alias) == expected


@pytest.mark.parametrize("provider", [None, "", " \t "])
@pytest.mark.parametrize("environment", [None, "", " CLAUDE "])
def test_normalize_provider_falls_through_to_environment_then_default(
    monkeypatch: pytest.MonkeyPatch,
    provider: str | None,
    environment: str | None,
) -> None:
    if environment is None:
        monkeypatch.delenv("MSAI_PROVIDER", raising=False)
    else:
        monkeypatch.setenv("MSAI_PROVIDER", environment)

    assert runtime.normalize_provider(provider) == (
        "anthropic" if environment else runtime.DEFAULT_PROVIDER
    )


def test_normalize_provider_explains_unknown_names() -> None:
    with pytest.raises(ValueError, match="Unknown provider 'missing'") as exc:
        runtime.normalize_provider(" MISSING ")

    message = str(exc.value)
    assert "Choose one of: " + ", ".join(runtime.PROVIDERS) in message
    assert "Aliases: " + ", ".join(runtime.PROVIDER_ALIASES) in message


@pytest.mark.parametrize("enabled", [False, True])
@pytest.mark.parametrize(
    ("explicit", "environment", "expected"),
    [
        ("caller-service", "environment-service", "caller-service"),
        (None, "environment-service", "environment-service"),
        ("", "environment-service", "environment-service"),
        (None, None, runtime.DEFAULT_SERVICE_NAME),
        (None, "", runtime.DEFAULT_SERVICE_NAME),
    ],
)
def test_configure_telemetry_respects_service_precedence_and_privacy(
    monkeypatch: pytest.MonkeyPatch,
    enabled: bool,
    explicit: str | None,
    environment: str | None,
    expected: str,
) -> None:
    for name in (
        "ENABLE_INSTRUMENTATION",
        "ENABLE_SENSITIVE_DATA",
        "OTEL_SERVICE_NAME",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("ENABLE_CONSOLE_EXPORTERS", "true")
    if environment is not None:
        monkeypatch.setenv("OTEL_SERVICE_NAME", environment)

    assert (
        runtime.configure_telemetry(enabled=enabled, service_name=explicit)
        == expected
    )
    assert os.environ["OTEL_SERVICE_NAME"] == expected
    assert os.environ["ENABLE_INSTRUMENTATION"] == str(enabled).lower()
    assert os.environ["ENABLE_CONSOLE_EXPORTERS"] == str(enabled).lower()
    assert os.environ["ENABLE_SENSITIVE_DATA"] == "false"


@pytest.mark.parametrize("enabled", [False, True])
def test_telemetry_does_not_enable_sensitive_capture_or_exporters(
    monkeypatch: pytest.MonkeyPatch, enabled: bool
) -> None:
    monkeypatch.setenv("ENABLE_SENSITIVE_DATA", "false")
    monkeypatch.setenv("ENABLE_CONSOLE_EXPORTERS", "false")
    monkeypatch.delenv("ENABLE_INSTRUMENTATION", raising=False)
    monkeypatch.delenv("OTEL_SERVICE_NAME", raising=False)

    runtime.configure_telemetry(enabled=enabled)

    assert os.environ["ENABLE_SENSITIVE_DATA"] == "false"
    assert os.environ["ENABLE_CONSOLE_EXPORTERS"] == "false"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, False),
        ("", False),
        (" \t ", False),
        (" CHANGE-ME ", False),
        ("change_me", False),
        ("changeme", False),
        ("placeholder", False),
        ("replace-me", False),
        ("replace_me", False),
        ("todo", False),
        ("your-api-key", False),
        ("your_api_key", False),
        ("your-key-here", False),
        ("your_key_here", False),
        ("<angle>", False),
        ("${expansion}", False),
        ("xxxxxxxx", False),
        ("prefix-XXXXXXXX-suffix", False),
        ("<incomplete", True),
        ("incomplete>", True),
        ("${incomplete", True),
        ("incomplete}", True),
        (" fixture-value ", True),
    ],
)
def test_env_is_present_filters_placeholders(
    monkeypatch: pytest.MonkeyPatch, value: str | None, expected: bool
) -> None:
    name = "MSAI_TEST_PRESENCE"
    if value is None:
        monkeypatch.delenv(name, raising=False)
    else:
        monkeypatch.setenv(name, value)

    assert runtime.env_is_present(name) is expected


@pytest.mark.parametrize("default", [False, True])
@pytest.mark.parametrize("value", [None, "", "  "])
def test_env_flag_uses_default_for_missing_or_blank_values(
    monkeypatch: pytest.MonkeyPatch, default: bool, value: str | None
) -> None:
    if value is None:
        monkeypatch.delenv("MSAI_TEST_FLAG", raising=False)
    else:
        monkeypatch.setenv("MSAI_TEST_FLAG", value)

    assert runtime.env_flag("MSAI_TEST_FLAG", default=default) is default


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("1", True),
        ("on", True),
        (" TRUE ", True),
        ("Yes", True),
        ("0", False),
        ("off", False),
        ("false", False),
        ("no", False),
        ("unexpected", False),
    ],
)
def test_env_flag_accepts_only_documented_truthy_values(
    monkeypatch: pytest.MonkeyPatch, value: str, expected: bool
) -> None:
    monkeypatch.setenv("MSAI_TEST_FLAG", value)

    assert runtime.env_flag("MSAI_TEST_FLAG") is expected

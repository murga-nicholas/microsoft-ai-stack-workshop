"""Test readiness reporting without reading or displaying credentials.

Run it:

    uv run pytest tests/test_doctor.py
"""

from __future__ import annotations

import importlib.metadata
import io
import json
import sys
from types import SimpleNamespace

import pytest
from rich.console import Console

from msai_demo import doctor

ENV_SENTINEL = "sentinel-credential-must-not-be-displayed"
RESPONSE_SENTINEL = "sentinel-token-must-not-be-displayed"


@pytest.fixture(autouse=True)
def isolated_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make readiness independent of the developer's environment."""
    for name, _use in doctor.CREDENTIALS:
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def package_calls(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    calls: list[str] = []

    def version(name: str) -> str:
        calls.append(name)
        if name == "semantic-kernel":
            raise importlib.metadata.PackageNotFoundError(name)
        return "1.2.3-test"

    monkeypatch.setattr(importlib.metadata, "version", version)
    return calls


@pytest.fixture
def console_output() -> tuple[Console, io.StringIO]:
    output = io.StringIO()
    return Console(file=output, width=160, color_system=None), output


class FakeCredential:
    def __init__(self, failures: tuple[str, ...] = ()) -> None:
        self.failures = failures
        self.scopes: list[str] = []

    def get_token(self, scope: str) -> SimpleNamespace:
        self.scopes.append(scope)
        if scope in self.failures:
            # SDK errors can contain secrets; report only their type.
            raise RuntimeError(ENV_SENTINEL)
        return SimpleNamespace(token=RESPONSE_SENTINEL)


def _assert_no_secrets(text: str) -> None:
    assert ENV_SENTINEL not in text
    assert RESPONSE_SENTINEL not in text


def test_package_versions_include_missing_distribution(
    package_calls: list[str],
) -> None:
    versions = doctor.package_versions()
    assert package_calls == [name for name, _lane in doctor.PACKAGES]
    assert list(versions) == package_calls
    assert versions.pop("semantic-kernel") == "not installed"
    assert set(versions.values()) == {"1.2.3-test"}


def test_credential_presence_reports_only_boolean_flags(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", ENV_SENTINEL)
    monkeypatch.setenv("AZURE_CLIENT_SECRET", ENV_SENTINEL)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "placeholder")
    presence = doctor.credential_presence()
    assert presence == {
        name: name in {"OPENAI_API_KEY", "AZURE_CLIENT_SECRET"}
        for name, _use in doctor.CREDENTIALS
    }
    assert all(isinstance(value, bool) for value in presence.values())
    _assert_no_secrets(json.dumps(presence))


def test_demo_readiness_requires_every_credential_and_is_sorted() -> None:
    readiness = doctor.demo_readiness({"OPENAI_API_KEY": True})
    assert list(readiness) == sorted(doctor.LIVE_REQUIREMENTS)
    assert readiness["agent-framework"] is True
    assert readiness["autogen"] is False
    assert readiness["group-chat"] is False
    assert readiness["workflow"] is True
    credentials = {name: True for name, _use in doctor.CREDENTIALS}
    assert all(doctor.demo_readiness(credentials).values())
    credentials["AZURE_CLIENT_SECRET"] = False
    assert doctor.demo_readiness(credentials)["azure-identity"] is False


@pytest.mark.parametrize("probe", [False, True])
def test_collect_readiness_probes_only_when_requested(
    monkeypatch: pytest.MonkeyPatch,
    package_calls: list[str],
    probe: bool,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", ENV_SENTINEL)
    credential = FakeCredential()
    readiness = doctor.collect_readiness(
        probe=probe, credential_factory=lambda: credential
    )

    assert readiness["python"] == ".".join(map(str, sys.version_info[:3]))
    assert readiness["packages"]["semantic-kernel"] == "not installed"
    assert package_calls == [name for name, _lane in doctor.PACKAGES]
    assert readiness["credentials"]["OPENAI_API_KEY"] is True
    assert readiness["demos"]["agent-framework"] is True
    assert readiness["demos"]["autogen"] is False
    assert readiness["offline_always"] == sorted(
        name
        for name, required in doctor.LIVE_REQUIREMENTS.items()
        if not required
    )
    expected = dict.fromkeys(doctor.TOKEN_SCOPES, "acquired") if probe else {}
    assert readiness["tokens"] == expected
    assert credential.scopes == (list(doctor.TOKEN_SCOPES) if probe else [])
    _assert_no_secrets(json.dumps(readiness))


@pytest.mark.parametrize(
    "failures",
    [(), doctor.TOKEN_SCOPES, (doctor.TOKEN_SCOPES[0],)],
)
def test_probe_tokens_discards_tokens_and_exception_messages(
    failures: tuple[str, ...],
) -> None:
    credential = FakeCredential(failures)
    outcomes = doctor.probe_tokens(credential_factory=lambda: credential)
    assert credential.scopes == list(doctor.TOKEN_SCOPES)
    assert outcomes == {
        scope: "failed: RuntimeError" if scope in failures else "acquired"
        for scope in doctor.TOKEN_SCOPES
    }
    _assert_no_secrets(json.dumps(outcomes))


def test_probe_tokens_without_identity_sdk() -> None:
    def missing_sdk() -> doctor.CredentialPort:
        raise ImportError

    assert doctor.probe_tokens(
        credential_factory=missing_sdk
    ) == dict.fromkeys(doctor.TOKEN_SCOPES, "azure-identity not installed")


def test_environment_adapter_constructs_without_requesting_tokens() -> None:
    credential = doctor.create_environment_credential()
    assert type(credential).__name__ == "EnvironmentCredential"
    assert callable(credential.get_token)


@pytest.mark.parametrize("probe", [False, True])
def test_full_report_contains_readiness_without_secrets(
    monkeypatch: pytest.MonkeyPatch,
    package_calls: list[str],
    console_output: tuple[Console, io.StringIO],
    probe: bool,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", ENV_SENTINEL)
    credential = FakeCredential((doctor.TOKEN_SCOPES[0],))
    console, output = console_output

    assert (
        doctor.run_doctor(
            console, probe=probe, credential_factory=lambda: credential
        )
        is True
    )

    rendered = output.getvalue()
    assert package_calls
    assert "Packages" in rendered
    assert "not installed" in rendered
    assert "Credentials (presence only)" in rendered
    assert "OPENAI_API_KEY" in rendered
    assert "present" in rendered
    assert "missing" in rendered
    assert "Demos" in rendered
    assert "ready" in rendered
    assert "offline only" in rendered
    assert "nothing" in rendered
    assert "demos can run their live path" in rendered
    assert ("Microsoft Entra token probe" in rendered) is probe
    assert credential.scopes == (list(doctor.TOKEN_SCOPES) if probe else [])
    if probe:
        assert "failed: RuntimeError" in rendered
        assert "acquired" in rendered
    _assert_no_secrets(rendered)


def test_package_only_report_omits_credentials_and_demos(
    monkeypatch: pytest.MonkeyPatch,
    package_calls: list[str],
    console_output: tuple[Console, io.StringIO],
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", ENV_SENTINEL)
    console, output = console_output
    assert doctor.run_doctor(console, packages_only=True) is True
    assert package_calls
    rendered = output.getvalue()
    assert "Packages" in rendered
    assert "Credentials" not in rendered
    assert "Demos" not in rendered
    _assert_no_secrets(rendered)


@pytest.mark.parametrize(
    ("demo", "expected", "message"),
    [
        ("agent-framework", True, "can run its live path"),
        ("autogen", False, "runs offline only. Missing: ANTHROPIC_API_KEY"),
        ("workflow", True, "runs for real with no credential"),
        ("unknown-demo", False, "Unknown demo 'unknown-demo'"),
    ],
)
def test_single_demo_reports_its_own_readiness(
    monkeypatch: pytest.MonkeyPatch,
    package_calls: list[str],
    console_output: tuple[Console, io.StringIO],
    demo: str,
    expected: bool,
    message: str,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", ENV_SENTINEL)
    console, output = console_output
    assert doctor.run_doctor(console, demo=demo) is expected
    assert package_calls
    rendered = output.getvalue()
    assert message in rendered
    assert "Packages" not in rendered
    if demo == "unknown-demo":
        assert "Known:" in rendered
        assert all(name in rendered for name in doctor.LIVE_REQUIREMENTS)
    _assert_no_secrets(rendered)

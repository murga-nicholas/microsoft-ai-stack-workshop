"""Check provider configuration and construction without a service.

Run it:
    uv run pytest tests/test_providers.py
"""

from __future__ import annotations

import asyncio
import sys
from dataclasses import dataclass, field
from types import ModuleType, SimpleNamespace

import pytest

from msai_demo import providers
from msai_demo.offline import OFFLINE_MODEL, ScriptedChatClient


@dataclass
class _Client:
    model: str
    base_url: str | None = None
    api_key: str | None = None
    project_endpoint: str | None = None
    credential: object | None = None


@dataclass
class _LocalModel:
    id: str


@dataclass
class _LocalCatalog:
    model: _LocalModel | None
    requested: list[str] = field(default_factory=list)

    def get_model(self, name: str) -> _LocalModel | None:
        self.requested.append(name)
        return self.model


@dataclass
class _LocalManager:
    urls: list[str]
    catalog: _LocalCatalog


def _install_module(
    monkeypatch: pytest.MonkeyPatch,
    name: str,
    **members: object,
) -> None:
    # Replace only the import boundary, never a vendor's internals.
    module = ModuleType(name)
    for member, value in members.items():
        setattr(module, member, value)
    monkeypatch.setitem(sys.modules, name, module)


@pytest.mark.parametrize(
    ("name", "model_env", "credential_env", "package"),
    [
        (
            "openai",
            "OPENAI_CHAT_MODEL",
            "OPENAI_API_KEY",
            "agent-framework-openai",
        ),
        (
            "anthropic",
            "ANTHROPIC_CHAT_MODEL",
            "ANTHROPIC_API_KEY",
            "agent-framework-anthropic",
        ),
        (
            "foundry",
            "FOUNDRY_MODEL",
            "FOUNDRY_PROJECT_ENDPOINT",
            "agent-framework-foundry",
        ),
        ("foundry-local", "FOUNDRY_LOCAL_MODEL", None, "foundry-local-sdk"),
        ("offline", "MSAI_OFFLINE_MODEL", None, "agent-framework-core"),
    ],
)
def test_provider_configuration_has_only_nonsecret_facts(
    name: str,
    model_env: str,
    credential_env: str | None,
    package: str,
) -> None:
    config = providers.get_provider_config(name)

    assert config.name == name
    assert config.model_env == model_env
    assert config.credential_env == credential_env
    assert config.package == package
    assert config.default_model
    assert config.setup_hint


def test_configuration_uses_aliases_and_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MSAI_PROVIDER", "scripted")

    assert providers.get_provider_config().name == "offline"
    assert providers.get_provider_config("claude").name == "anthropic"
    assert providers.get_provider_config().default_model == OFFLINE_MODEL


@pytest.mark.parametrize(
    "name", ["openai", "anthropic", "foundry", "foundry-local", "offline"]
)
def test_model_resolution_obeys_override_order(
    monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    config = providers.get_provider_config(name)
    monkeypatch.delenv(config.model_env, raising=False)
    assert providers.resolve_model_name(name) == config.default_model

    monkeypatch.setenv(config.model_env, "environment-model")
    assert providers.resolve_model_name(name) == "environment-model"
    assert providers.resolve_model_name(name, "explicit") == "explicit"
    assert providers.resolve_model_name(name, "") == "environment-model"

    monkeypatch.setenv(config.model_env, "")
    assert providers.resolve_model_name(name) == config.default_model


@pytest.mark.parametrize(
    ("name", "credential_env"),
    [
        ("openai", "OPENAI_API_KEY"),
        ("anthropic", "ANTHROPIC_API_KEY"),
        ("foundry", "FOUNDRY_PROJECT_ENDPOINT"),
    ],
)
def test_credential_controls_readiness_and_missing_configuration(
    monkeypatch: pytest.MonkeyPatch, name: str, credential_env: str
) -> None:
    monkeypatch.delenv(credential_env, raising=False)

    assert providers.provider_is_ready(name) is False
    with pytest.raises(RuntimeError, match=credential_env) as error:
        providers.create_chat_client(name)
    assert name in str(error.value)
    assert "--provider offline" in str(error.value)

    monkeypatch.setenv(credential_env, "synthetic-test-configuration")
    assert providers.provider_is_ready(name) is True


@pytest.mark.parametrize("name", ["offline", "foundry-local"])
def test_credential_free_providers_are_ready(name: str) -> None:
    assert providers.provider_is_ready(name) is True


def test_provider_display_order_is_stable() -> None:
    configs = providers.list_provider_configs()

    assert isinstance(configs, tuple)
    assert tuple(config.name for config in configs) == (
        "openai",
        "anthropic",
        "foundry",
        "foundry-local",
        "offline",
    )


def test_offline_factory_forwards_script_and_model() -> None:
    from agent_framework import Message

    client = providers.create_chat_client(
        "offline",
        model_name="workshop-script",
        replies=["Proposal ready."],
        tool_plan=[("price_pilot", {"weeks": 1})],
    )
    assert isinstance(client, ScriptedChatClient)
    assert client.model == "workshop-script"
    contents, finish_reason = client._next_contents()
    assert finish_reason == "tool_calls"
    assert contents[0].name == "price_pilot"
    assert contents[0].arguments == {"weeks": 1}

    async def reply() -> None:
        response = await client.get_response(
            [Message(role="user", contents=["Draft the pilot."])]
        )
        assert response.text == "Proposal ready."
        assert response.model == "workshop-script"

    asyncio.run(reply())


@pytest.mark.parametrize(
    ("name", "module", "constructor", "credential_env"),
    [
        (
            "openai",
            "agent_framework.openai",
            "OpenAIChatClient",
            "OPENAI_API_KEY",
        ),
        (
            "anthropic",
            "agent_framework.anthropic",
            "AnthropicClient",
            "ANTHROPIC_API_KEY",
        ),
    ],
)
def test_cloud_clients_receive_the_resolved_model(
    monkeypatch: pytest.MonkeyPatch,
    name: str,
    module: str,
    constructor: str,
    credential_env: str,
) -> None:
    monkeypatch.setenv(credential_env, "synthetic-test-key")
    _install_module(monkeypatch, module, **{constructor: _Client})

    client = providers.create_chat_client(name, model_name="selected-model")

    assert isinstance(client, _Client)
    assert client == _Client(model="selected-model")


def test_foundry_client_receives_endpoint_and_credential(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    endpoint = "https://synthetic-project.example.test"
    credential = object()
    monkeypatch.setenv("FOUNDRY_PROJECT_ENDPOINT", endpoint)
    _install_module(
        monkeypatch, "agent_framework.foundry", FoundryChatClient=_Client
    )
    _install_module(
        monkeypatch,
        "azure.identity",
        DefaultAzureCredential=lambda: credential,
    )

    client = providers.create_chat_client("foundry", model_name="deployment")

    assert isinstance(client, _Client)
    assert client == _Client(
        model="deployment", project_endpoint=endpoint, credential=credential
    )


@pytest.mark.parametrize(
    "endpoint",
    [
        "http://127.0.0.1:1234",
        "http://127.0.0.1:1234/",
        "http://127.0.0.1:1234/v1",
        "http://127.0.0.1:1234/v1/",
    ],
)
def test_foundry_local_explicit_url_skips_discovery(
    monkeypatch: pytest.MonkeyPatch, endpoint: str
) -> None:
    _install_module(
        monkeypatch,
        "agent_framework.openai",
        OpenAIChatCompletionClient=_Client,
    )
    # An explicit URL must avoid importing the discovery SDK.
    monkeypatch.setitem(sys.modules, "foundry_local_sdk", None)

    client = providers.create_chat_client(
        "foundry-local", model_name="local-model", base_url=endpoint
    )

    assert isinstance(client, _Client)
    assert client == _Client(
        model="local-model",
        base_url="http://127.0.0.1:1234/v1",
        api_key=providers.LOCAL_API_KEY,
    )


@pytest.mark.parametrize("has_manager", [False, True])
def test_foundry_local_requires_a_running_service(
    monkeypatch: pytest.MonkeyPatch, has_manager: bool
) -> None:
    manager = _LocalManager([], _LocalCatalog(None)) if has_manager else None
    _install_module(
        monkeypatch,
        "agent_framework.openai",
        OpenAIChatCompletionClient=_Client,
    )
    _install_module(
        monkeypatch,
        "foundry_local_sdk",
        FoundryLocalManager=SimpleNamespace(instance=manager),
    )

    with pytest.raises(RuntimeError, match="Foundry Local is not running"):
        providers.create_chat_client("foundry-local")


@pytest.mark.parametrize("has_model", [False, True])
def test_foundry_local_resolves_the_model_id_from_its_catalog(
    monkeypatch: pytest.MonkeyPatch, has_model: bool
) -> None:
    model = _LocalModel("resolved-model-id") if has_model else None
    catalog = _LocalCatalog(model)
    manager = _LocalManager(
        ["http://127.0.0.1:1234/", "http://127.0.0.1:5678/"], catalog
    )
    _install_module(
        monkeypatch,
        "agent_framework.openai",
        OpenAIChatCompletionClient=_Client,
    )
    _install_module(
        monkeypatch,
        "foundry_local_sdk",
        FoundryLocalManager=SimpleNamespace(instance=manager),
    )

    if has_model:
        client = providers.create_chat_client(
            "foundry-local", model_name="requested-alias"
        )
        assert isinstance(client, _Client)
        assert client == _Client(
            model="resolved-model-id",
            base_url="http://127.0.0.1:1234/v1",
            api_key=providers.LOCAL_API_KEY,
        )
    else:
        with pytest.raises(RuntimeError, match="no model named 'missing'"):
            providers.create_chat_client("foundry-local", model_name="missing")

    assert catalog.requested == ["requested-alias" if has_model else "missing"]

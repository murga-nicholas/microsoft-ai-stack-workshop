"""One module is the entire model-provider switch.

Everything downstream depends on the Agent Framework chat-client
contract, never on a vendor client. Swapping OpenAI for Anthropic or
for a Microsoft Foundry deployment is a change here and nowhere else.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final, cast

from msai_demo.offline import OFFLINE_MODEL, ScriptedChatClient
from msai_demo.runtime import (
    PROVIDERS,
    ProviderName,
    env_is_present,
    normalize_provider,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from agent_framework import SupportsChatGetResponse


@dataclass(frozen=True)
class ProviderConfig:
    """Non-secret facts about one provider.

    Attributes:
        name: Canonical provider name.
        default_model: Model used when nothing else is configured.
        model_env: Environment variable that overrides the model.
        package: Distribution that supplies the client.
        credential_env: Environment variable that gates readiness, or
            ``None`` when the provider needs no credential.
        setup_hint: One line a listener can act on.
    """

    name: ProviderName
    default_model: str
    model_env: str
    package: str
    credential_env: str | None
    setup_hint: str


# Foundry Local is loopback-only and accepts any key; the OpenAI
# client still insists on being given one.
LOCAL_API_KEY: Final[str] = "foundry-local"

PROVIDER_CONFIGS: Final[dict[ProviderName, ProviderConfig]] = {
    "openai": ProviderConfig(
        name="openai",
        default_model="gpt-5.4-mini",
        model_env="OPENAI_CHAT_MODEL",
        package="agent-framework-openai",
        credential_env="OPENAI_API_KEY",
        setup_hint="Set OPENAI_API_KEY to use the OpenAI path.",
    ),
    "anthropic": ProviderConfig(
        name="anthropic",
        default_model="claude-haiku-4-5",
        model_env="ANTHROPIC_CHAT_MODEL",
        package="agent-framework-anthropic",
        credential_env="ANTHROPIC_API_KEY",
        setup_hint="Set ANTHROPIC_API_KEY to use the Anthropic path.",
    ),
    "foundry": ProviderConfig(
        name="foundry",
        default_model="gpt-4o-mini",
        model_env="FOUNDRY_MODEL",
        package="agent-framework-foundry",
        credential_env="FOUNDRY_PROJECT_ENDPOINT",
        setup_hint=(
            "Set FOUNDRY_PROJECT_ENDPOINT and sign in with a Microsoft "
            "Entra credential."
        ),
    ),
    "foundry-local": ProviderConfig(
        name="foundry-local",
        default_model="phi-4-mini",
        model_env="FOUNDRY_LOCAL_MODEL",
        package="foundry-local-sdk",
        credential_env=None,
        setup_hint=(
            "Install Foundry Local and start the service; no key needed."
        ),
    ),
    "offline": ProviderConfig(
        name="offline",
        default_model=OFFLINE_MODEL,
        model_env="MSAI_OFFLINE_MODEL",
        package="agent-framework-core",
        credential_env=None,
        setup_hint="Always available. Real framework, scripted tokens.",
    ),
}


def get_provider_config(provider: str | None = None) -> ProviderConfig:
    """Look up the non-secret settings for a provider."""
    return PROVIDER_CONFIGS[normalize_provider(provider)]


def resolve_model_name(
    provider: str | None = None,
    model_name: str | None = None,
) -> str:
    """Resolve the model name for a provider.

    Args:
        provider: Provider name or alias.
        model_name: Explicit override that wins over everything.

    Returns:
        The model name this provider will ask for.
    """
    config = get_provider_config(provider)
    return model_name or os.getenv(config.model_env) or config.default_model


def provider_is_ready(provider: str | None = None) -> bool:
    """Report whether a provider could make a live call.

    Presence only. Whether the credential authenticates, has quota or
    can reach the model is something the first real call decides.
    """
    config = get_provider_config(provider)
    if config.credential_env is None:
        return True
    return env_is_present(config.credential_env)


def list_provider_configs() -> tuple[ProviderConfig, ...]:
    """Return every provider in a stable display order."""
    return tuple(PROVIDER_CONFIGS[name] for name in PROVIDERS)


def create_chat_client(
    provider: str | None = None,
    *,
    model_name: str | None = None,
    base_url: str | None = None,
    replies: Sequence[str] = (),
    tool_plan: Sequence[tuple[str, dict[str, Any]]] = (),
) -> SupportsChatGetResponse[Any]:
    """Build a chat client without reading or printing a secret.

    Args:
        provider: Provider name or alias.
        model_name: Optional model override.
        base_url: An endpoint the caller has already discovered. Used
            only by ``foundry-local``, where it skips service
            discovery entirely - which is what makes that path
            testable without starting the local service.
        replies: Scripted replies, used only by the offline provider.
        tool_plan: Scripted tool calls, used only by the offline
            provider.

    Returns:
        A client that satisfies the Agent Framework chat contract.

    Raises:
        RuntimeError: If a live provider is selected without its
            credential, so the failure names the missing variable
            instead of surfacing as a vendor authentication error.
    """
    config = get_provider_config(provider)
    model = resolve_model_name(config.name, model_name)

    if config.name == "offline":
        return ScriptedChatClient(
            replies=replies,
            tool_plan=tool_plan,
            model=model,
        )

    if not provider_is_ready(config.name):
        message = (
            f"Provider {config.name!r} needs {config.credential_env}. "
            f"{config.setup_hint} Use --provider offline to run the "
            f"same code with no credentials."
        )
        raise RuntimeError(message)

    if config.name == "openai":
        from agent_framework.openai import OpenAIChatClient

        return OpenAIChatClient(model=model)

    if config.name == "anthropic":
        from agent_framework.anthropic import AnthropicClient

        # The preview package ships no type information yet.
        return cast(
            "SupportsChatGetResponse[Any]",
            AnthropicClient(model=model),
        )

    if config.name == "foundry":
        from agent_framework.foundry import FoundryChatClient
        from azure.identity import DefaultAzureCredential

        return cast(
            "SupportsChatGetResponse[Any]",
            FoundryChatClient(
                project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
                model=model,
                credential=DefaultAzureCredential(),
            ),
        )

    return _create_foundry_local_client(model, base_url)


def _create_foundry_local_client(
    model: str,
    base_url: str | None = None,
) -> SupportsChatGetResponse[Any]:
    """Point the OpenAI client at the Foundry Local endpoint.

    Foundry Local exposes an OpenAI-compatible endpoint, which is the
    documented way to consume it. Two details are worth knowing, and
    both bite people who follow an older blog post:

    * The Agent Framework connector is skipped on purpose. Its current
      preview pins ``foundry-local-sdk>=0.5.1,<0.5.2`` while the
      shipping SDK is 2.x.
    * The SDK renamed its own module. 0.5.x exported
      ``foundry_local``; 2.x exports ``foundry_local_sdk``, and the
      manager is constructed from a ``Configuration`` rather than from
      a model alias.

    Raises:
        RuntimeError: If the local service is not running, or does not
            have the requested model. Both are actionable, so they say
            which one happened.
    """
    from agent_framework.openai import OpenAIChatCompletionClient

    if base_url is not None:
        return OpenAIChatCompletionClient(
            model=model,
            base_url=_normalise_local_url(base_url),
            api_key=LOCAL_API_KEY,
        )

    from foundry_local_sdk import FoundryLocalManager

    manager = FoundryLocalManager.instance
    if manager is None or not manager.urls:
        message = (
            "Foundry Local is not running. Start the service, then "
            "retry. Use --provider offline to run without it."
        )
        raise RuntimeError(message)

    resolved = manager.catalog.get_model(model)
    if resolved is None:
        message = (
            f"Foundry Local has no model named {model!r}. Pull it "
            f"first, or set FOUNDRY_LOCAL_MODEL to one it has."
        )
        raise RuntimeError(message)

    return OpenAIChatCompletionClient(
        model=str(resolved.id),
        base_url=_normalise_local_url(manager.urls[0]),
        api_key=LOCAL_API_KEY,
    )


def _normalise_local_url(endpoint: str) -> str:
    """Return an endpoint that ends in exactly one ``/v1``."""
    return endpoint.rstrip("/").removesuffix("/v1") + "/v1"

# Module specification — read this before writing any demo module

Every demo module in `src/msai_demo/` follows this contract. It exists so that
thirty-two modules across two lanes stay readable, testable and honest.

---

## 1. House style (enforced, not advisory)

- Python 3.11+ syntax. `from __future__ import annotations` at the top of every file.
- **Ruff at 79 columns**, docstring lines at **72**. Rule set is in `pyproject.toml`.
- **Google-style docstrings** on every public function and class.
- `mypy --strict` must pass. `Any` only at a third-party boundary, converted to a
  local `TypedDict` or `Protocol` immediately.
- Imports of optional SDKs go **inside the function** (Ruff `PLC0415` is disabled for
  exactly this reason), so a missing package is a reported mode, not an ImportError
  at startup.
- Never print, log or return a credential value.
- Every module opens with a docstring that says what the technology is, whether it is
  legacy or current, and the exact `uv run msai-demo ...` command that runs it.

## 2. The result contract

Import from `msai_demo.contracts`:

```python
from msai_demo.contracts import (
    DemoResult, evidence, missing_configuration, result,
)
```

`result(...)` returns a `DemoResult` TypedDict. Required keyword arguments:

| Argument | Meaning |
|---|---|
| `demo` | CLI name, e.g. `"ai-search"` |
| `technology` | Product/package name shown on the slide |
| `lane` | `"legacy"` \| `"current"` \| `"shared"` |
| `mode` | how it ran — see below |
| `status` | `"ok"` \| `"paused"` \| `"blocked"` \| `"error"` |
| `headline` | one sentence for the console and the slide |
| `evidence` | built by `evidence(...)` |
| `data` | technology-specific payload, or `None` |
| `next_steps` | concrete missing prerequisites |

### `mode` vocabulary — pick exactly one

| `mode` | Use when |
|---|---|
| `local_execution` | Real local computation or protocol execution. Nothing simulated. |
| `local_contract` | Real SDK/application code, **explicitly synthetic** external response. Requires `fixture_id`. |
| `live_model` | A model was actually invoked. |
| `live_identity` | A token was actually acquired from Microsoft Entra. |
| `live_service` | A non-model service was actually called. |
| `not_run` | Preconditions stopped it. Use `missing_configuration(...)`. |
| `batch` | Container only. |

`contracts.result()` **raises** if the evidence contradicts the mode:
a live mode must set `network_attempted=True`; a non-live mode must not claim
`service_executed=True`; `local_contract` must name a `fixture_id`.

**`status` is separate from `mode`.** A real HTTP 403 is a *successful* demonstration
of an authorisation boundary: `mode="live_service"`, `status="blocked"`,
`error={"code": "authorization_denied", ...}`. It is not an error in the demo.

## 3. The shape of a module

Each module has exactly one public async runner plus a narrow adapter seam:

```python
class SomethingPort(Protocol):
    """The one external call this demo makes."""

    mode: Mode

    async def fetch(self, query: str) -> list[dict[str, Any]]: ...


class FixturePort:
    """Deterministic synthetic response. Names its fixture."""

    mode: Mode = "local_contract"
    fixture_id = "ai-search-v1"
    ...


class LivePort:
    """The real SDK call. Constructed only when configured."""

    mode: Mode = "live_service"
    ...


async def run_x_demo(*, execution: str = "offline", port: SomethingPort | None = None) -> DemoResult:
    """..."""
```

Rules for the seam:

- `run_*_demo` takes an **optional injected port**. Tests pass a fake; nothing is
  monkey-patched.
- `execution="offline"` (the default) uses the fixture port.
- `execution="live"` builds the live port, and **fails before any call** when
  configuration is missing — return `missing_configuration(...)`.
- A missing optional SDK still permits the local contract path, with
  `sdk_invoked=False`.
- Never catch broad exceptions and manufacture success. Map known failures
  (401/403, throttling, timeout) to a structured `error`; let the rest raise.
- Missing usage/token counts are `None`, never an invented `0`.

## 4. Verified API facts (read 2026-09-14, do not guess)

Agent Framework Python 1.18.0, current names only:

```python
from agent_framework import Agent, AgentSession, Content, Message, tool, FunctionTool
from agent_framework import WorkflowBuilder, FileCheckpointStorage, InMemoryCheckpointStorage
from agent_framework import create_harness_agent
from agent_framework.observability import configure_otel_providers, get_tracer, get_meter
from agent_framework.orchestrations import (
    GroupChatBuilder, GroupChatState, SequentialBuilder,
    ConcurrentBuilder, HandoffBuilder, MagenticBuilder,
)
from agent_framework.openai import OpenAIChatClient, OpenAIChatCompletionClient
from agent_framework.anthropic import AnthropicClient
from agent_framework.foundry import FoundryChatClient, FoundryAgent, FoundryEmbeddingClient
```

- `agent-framework-orchestrations` is a **separate package**; it is already a
  dependency.
- `agent.run(...)`, `agent.run(..., stream=True)`, `agent.create_session()`.
- Builders take **constructor kwargs**, never fluent `.participants(...)`.
- `workflow.run(message, stream=True)` returns a stream; `await stream.get_final_response()`.
- `event.type` is a string: `"output"`, `"intermediate"`, `"request_info"`,
  `"executor_invoked"`, `"status"`, …
- Checkpoints: `FileCheckpointStorage(path)`, `await storage.list_checkpoints(workflow_name=workflow.name)`.
- Tool approval: `@tool(approval_mode="always_require" | "never_require")`.
- Observability env: `ENABLE_INSTRUMENTATION` (default **true**),
  `ENABLE_SENSITIVE_DATA` (default false), `ENABLE_CONSOLE_EXPORTERS`,
  `OTEL_EXPORTER_OTLP_ENDPOINT`. Spans: `invoke_agent`, `chat`, `execute_tool`.
- **Agent Framework does not read `.env`.** `msai_demo.runtime.load_env_file()` does.

Azure, current packages:

```python
from azure.identity import ClientSecretCredential, DefaultAzureCredential, EnvironmentCredential
from azure.ai.projects import AIProjectClient          # azure-ai-projects 2.6.0
from azure.search.documents import SearchClient        # azure-search-documents 12.0.0
from azure.ai.evaluation import evaluate               # azure-ai-evaluation 1.18.5
from foundry_local import FoundryLocalManager          # foundry-local-sdk 2.0.1
```

Packages deliberately **not installed** (their pins conflict with the current lane;
demonstrate them with `local_contract` and `sdk_invoked=False`, and say why):

| Package | Pin it carries | Conflicts with |
|---|---|---|
| `semantic-kernel` 1.44.1 | `azure-ai-projects>=1.0,<2.5` | `azure-ai-projects` 2.6.0 |
| `promptflow-tracing` 1.18.5 | `opentelemetry-sdk>=1.22,<1.39` | `agent-framework-core` needs API `>=1.39` |
| `azure-ai-inference` 1.0.0b9 | last released 2025-02-15 | stalled beta |
| `azure-ai-contentsafety` 1.0.0 | last released 2023-12-12 | superseded by Foundry guardrails |
| `botbuilder-*` | Bot Framework LTS ended Dec 2025 | replaced by Microsoft 365 Agents SDK |

`autogen-agentchat` 0.7.5 **is** installed, via `uv sync --group legacy`.

## 5. Environment on the demo machine (verified)

- `OPENAI_API_KEY` present. `ANTHROPIC_API_KEY` absent.
- Azure service principal present (`AZURE_TENANT_ID`, `AZURE_CLIENT_ID`,
  `AZURE_CLIENT_SECRET`). It **successfully issues tokens** for
  `https://ai.azure.com/.default`, `https://cognitiveservices.azure.com/.default`,
  `https://search.azure.com/.default` and Microsoft Graph — and holds **zero
  subscription role assignments**, so every data-plane call would return 403.
- No `az` CLI, no `azd`. Windows 11, PowerShell.

So: identity demos genuinely run live. Resource demos do not, and must say so.

## 6. Shared scenario

Everything uses one business task from `msai_demo.scenario`: cost a six-week
customer-support pilot against a 25,000 USD budget and refuse to accept it without a
human approval. Use `scenario.BRIEF`, `scenario.price_pilot()`,
`scenario.proposal_is_acceptable()` rather than inventing new numbers.

## 7. Tests

`tests/test_<module>.py`, offline, no network, no monkey-patching of internals.
Inject the fake port. Cover: success, missing configuration, missing SDK, 403,
malformed response. Coverage is enforced at **100% statements and branches**.

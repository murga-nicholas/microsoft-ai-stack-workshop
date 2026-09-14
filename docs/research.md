# Microsoft AI stack — research notes

Everything below was read from official Microsoft documentation and the PyPI API on
**2026-09-14**. Each claim carries a source. Package versions are the ones PyPI
reported that day; run `uv run msai-demo doctor --packages` to print what is actually
installed on your machine rather than trusting this file.

This document is the evidence base for the deck. It is deliberately dated, because
this part of the ecosystem renames itself roughly twice a year.

---

## 1. The one-paragraph history

Microsoft arrived at today's stack from **two independent lineages** that were merged
on purpose:

- **AutoGen** (2023) — Microsoft Research. Pioneered multi-agent *group chat*, the
  `AssistantAgent` abstraction and an event-driven agent runtime. Research-first.
- **Semantic Kernel** (2023) — Microsoft product engineering. Kernel, plugins,
  planners, filters, telemetry, .NET-first enterprise concerns.

Both proved the ideas. Neither was the whole answer: AutoGen had the abstractions but
not the enterprise plumbing; Semantic Kernel had the plumbing but a heavier
programming model for multi-agent work.

- **Microsoft Agent Framework** (announced October 2025, **v1.0 GA 2026-04-03**) is the
  deliberate merge of the two, *built by the same teams*. Microsoft's own words:
  "Agent Framework is the next generation of both Semantic Kernel and AutoGen."
  ([overview](https://learn.microsoft.com/en-us/agent-framework/overview/agent-framework-overview))

On the cloud side the same consolidation happened under a different name:

| When | What happened |
|---|---|
| Nov 2023 | Azure AI Studio announced |
| Nov 2024 | Azure AI Studio → **Azure AI Foundry** |
| Nov 18 2025 | Ignite: Azure AI Foundry → **Microsoft Foundry** ("Azure" dropped on purpose) |
| Jan 1 2026 | Rename formalised in Microsoft Product Terms |
| 2026 | Foundry Agent Service, Foundry Observability and the Foundry portal reach GA |

The pattern is the same in both lanes: **many overlapping products collapsed into one
runtime with one identity model and one control plane.**

---

## 2. Package reality check (PyPI, read 2026-09-14)

This table is the single most persuasive slide in the deck, because it is not an
opinion — it is release dates.

| Package | Latest | Last release | Verdict |
|---|---|---|---|
| `autogen-agentchat` / `autogen-core` / `autogen-ext` | 0.7.5 | **2025-09-30** | **Legacy.** No release in ~12 months |
| `semantic-kernel` | 1.44.1 | 2026-08-06 | **Maintenance.** Bug + security fixes only |
| `agent-framework` | **1.18.0** | **2026-09-10** | **Current.** Ships weekly |
| `agent-framework-core` | 1.18.0 | 2026-09-10 | Current (minimal core) |
| `agent-framework-openai` | 1.14.3 | 2026-09-10 | Current |
| `agent-framework-foundry` | 1.13.0 | 2026-09-10 | Current |
| `agent-framework-anthropic` | 1.0.0b260910 | 2026-09-10 | Preview |
| `agent-framework-devui` | 1.0.0b260910 | 2026-09-10 | Preview (sample app, not production) |
| `azure-ai-projects` | **2.6.0** | 2026-09-04 | Current — the Foundry control-plane SDK |
| `azure-ai-agents` | 1.1.0 | 2025-08-05 | Superseded by `azure-ai-projects` 2.x |
| `azure-ai-evaluation` | 1.18.5 | 2026-09-04 | Current |
| `azure-search-documents` | 12.0.0 | 2026-05-01 | Current |
| `azure-ai-inference` | 1.0.0b9 | **2025-02-15** | Stalled at beta — use Foundry clients |
| `azure-ai-contentsafety` | 1.0.0 | **2023-12-12** | Standalone SDK; Foundry guardrails is the current path |
| `foundry-local-sdk` | 2.0.1 | 2026-08-31 | Current |
| `microsoft-agents-hosting-aiohttp` | 1.5.0 | 2026-08-26 | Current — Microsoft 365 Agents SDK |
| `promptflow` | 1.18.5 | 2026-05-01 | Legacy path; Foundry evaluations is current |

Semantic Kernel is **not dead** and saying so on stage is wrong. Microsoft's
commitment: SK v1.x keeps getting critical bug and security fixes, supported for at
least one year after Agent Framework went GA. New feature work happens in Agent
Framework.
([devblog](https://devblogs.microsoft.com/agent-framework/semantic-kernel-and-microsoft-agent-framework/))

---

## 3. Microsoft Agent Framework — what it actually is

Four primary areas
([overview](https://learn.microsoft.com/en-us/agent-framework/overview/agent-framework-overview)):

| Area | What it owns |
|---|---|
| **Agents** | One agent: model client, instructions, tools, MCP servers, sessions |
| **Harness Agent** | Opinionated long-horizon agent: planning/todos, context compaction, file memory, tool approval, observability |
| **Workflows** | Typed graph-based orchestration between agents and functions |
| **Integrations** | Model providers, agent services, tools, context providers, middleware, evaluation, UI |

Languages: **.NET, Python, Go** (Go is public preview).

### 3.1 Python install surface

`agent-framework-core` was deliberately slimmed; provider packages are explicit.

```bash
pip install agent-framework            # everything (core[all])
pip install agent-framework-core       # minimal core
pip install agent-framework-openai     # OpenAI *and* Azure OpenAI
pip install agent-framework-anthropic --pre
pip install agent-framework-foundry    # Microsoft Foundry cloud
pip install agent-framework-orchestrations  # GroupChat, Sequential, Handoff, Magentic
pip install agent-framework-devui      # local debug UI (sample, not production)
```

`agent-framework-foundry-local` also exists, but its preview pins
`foundry-local-sdk>=0.5.1,<0.5.2` against a shipping 2.0.1 — see section 8. The
orchestration builders are **not** in `agent-framework-core`; without the separate
package, `from agent_framework.orchestrations import GroupChatBuilder` fails.

### 3.2 The 2026 Python rename wave — the trap for anyone with older sample code

Every blog post older than ~February 2026 uses names that no longer exist.
([significant changes](https://learn.microsoft.com/en-us/agent-framework/support/upgrade/python-2026-significant-changes))

| Old | New |
|---|---|
| `ChatAgent` | `Agent` |
| `ChatMessage` | `Message` |
| `AgentThread` | `AgentSession` |
| `AIFunction` | `FunctionTool` |
| `@ai_function` | `@tool` |
| `agent.get_new_thread()` | `agent.create_session()` |
| `agent.run(..., thread=...)` | `agent.run(..., session=...)` |
| `agent.run_stream(...)` | `agent.run(..., stream=True)` |
| `OpenAIResponsesClient` | `OpenAIChatClient` |
| `OpenAIChatClient` (old meaning) | `OpenAIChatCompletionClient` |
| `AzureOpenAIResponsesClient` / `AzureOpenAIChatClient` | `OpenAIChatClient` / `OpenAIChatCompletionClient` + `azure_endpoint=` |
| `AzureAIAgentClient` | `FoundryChatClient` / `FoundryAgent` |
| `from agent_framework import SequentialBuilder, GroupChatBuilder` | `from agent_framework.orchestrations import ...` |
| `TextContent(text=...)` | `Content.from_text(text=...)` |
| `WorkflowOutputEvent` | `event.type == "output"` |
| `model_id=` | `model=` |
| `OPENAI_CHAT_MODEL_ID` | `OPENAI_CHAT_MODEL` |
| `HostedCodeInterpreterTool` | `client.get_code_interpreter_tool()` |
| fluent `.participants(...).with_termination_condition(...)` | constructor kwargs on the builder |

Also: **Agent Framework does not load `.env` automatically.** Call `load_dotenv()` or
read real environment variables. Instrumentation is **on** by default since 1.x;
sensitive-data capture is **off** by default.

### 3.3 Orchestration patterns (all stable in 1.0)

`from agent_framework.orchestrations import ...`

| Builder | Pattern | Use when |
|---|---|---|
| `SequentialBuilder` | fixed pipeline | ordered steps, each appends to one conversation |
| `ConcurrentBuilder` | fan-out / fan-in | independent analyses, ensemble decisions |
| `GroupChatBuilder` | **group chat** | iterative refinement, writer/reviewer, multi-perspective |
| `HandoffBuilder` | control transfer | escalation, expert routing |
| `MagenticBuilder` | manager-planned team | open-ended research where the plan is unknown |

`GroupChatBuilder` is the direct successor to AutoGen's `RoundRobinGroupChat` /
`SelectorGroupChat`. It takes *constructor* arguments, not fluent builders:

```python
from agent_framework.orchestrations import GroupChatBuilder, GroupChatState

def round_robin_selector(state: GroupChatState) -> str:
    names = list(state.participants.keys())
    return names[state.current_round % len(names)]

workflow = GroupChatBuilder(
    participants=[researcher, writer],
    selection_func=round_robin_selector,                 # or orchestrator_agent=...
    termination_condition=lambda conv: len(conv) >= 4,
    intermediate_output_from=[researcher, writer],
).build()
```

Speaker selection has three modes: `selection_func` (pure Python), `orchestrator_agent`
(an LLM picks the next speaker — the SelectorGroupChat replacement), or a custom
`orchestrator`. Internally it is a **star topology**: every participant keeps its own
`AgentSession`, and the orchestrator broadcasts each turn to all of them so context
stays synchronised.
([group chat](https://learn.microsoft.com/en-us/agent-framework/workflows/orchestrations/group-chat))

### 3.4 What group chat actually gains over AutoGen

**Correction to the first draft of this document.** The obvious comparison table —
"AutoGen cannot do human-in-the-loop / state / multiple vendors" — is **wrong**, and an
architect in the room will say so. Verified against the installed `autogen-agentchat`
0.7.5 on 2026-09-14:

```python
>>> hasattr(RoundRobinGroupChat, "save_state"), hasattr(RoundRobinGroupChat, "load_state")
(True, True)
>>> from autogen_agentchat.agents import UserProxyAgent      # human in the loop
>>> from autogen_ext.models.anthropic import AnthropicChatCompletionClient
```

AutoGen has team state persistence, a human proxy agent, and first-party Anthropic,
Azure, Ollama and llama.cpp clients. Any slide claiming otherwise is false.

The honest comparison is about **who owns the integration work** and **how long the
code stays supported**:

| Dimension | AutoGen 0.7.5 | Agent Framework 1.18 | Honest verdict |
|---|---|---|---|
| Group chat with round robin | ✅ `RoundRobinGroupChat` | ✅ `GroupChatBuilder(selection_func=...)` | **Parity** |
| LLM-chosen speaker | ✅ `SelectorGroupChat` | ✅ `orchestrator_agent=` | **Parity** |
| Mixed vendors in one team | ✅ per-agent `model_client` | ✅ per-agent `client` | **Parity** |
| Human in the loop | ✅ `UserProxyAgent`, in-run | ✅ `request_info` + `run(responses=...)`, survives process exit | **Different shape** |
| Durable state | ✅ `save_state` / `load_state` you wire yourself | ✅ `checkpoint_storage=` owned by the workflow | **Less glue in AF** |
| Approval → action gate | application code around the team | typed workflow executors and edges | **Less glue in AF** |
| Telemetry | OTel, wired by the application | OTel GenAI semconv, on by default | **Less glue in AF** |
| Support | last release **2025-09-30** | releases weekly | **The real argument** |

So the migration case is not "AutoGen can't". It is:

> Migrate the workflows where integrated approval, recovery and tracing remove code
> your team would otherwise write and maintain — and stop building new work on a
> package that has not shipped in a year.

([AutoGen migration](https://learn.microsoft.com/en-us/agent-framework/migration-guide/from-autogen/))

Note the migration guide still lists "SelectorGroupChat" as a future pattern — that
page is dated 2026-04-01 and is stale. The group-chat page (2026-07-01) documents
`orchestrator_agent`, which is that feature, shipped.

### 3.5 The cost of staying, measured in dependency pins

This is the part that is not an opinion. Every line below was read from the PyPI
metadata API on 2026-09-14 and each one was reproduced by running `uv lock`.

| Package | Pin it carries | Current reality | Consequence |
|---|---|---|---|
| `semantic-kernel` 1.44.1 | `azure-ai-projects>=1.0,<2.5` | `azure-ai-projects` **2.6.0** | SK and the current Foundry SDK **cannot share a lockfile** |
| `semantic-kernel[autogen]` | `autogen-agentchat>=0.2,<0.4` | AutoGen is **0.7.5** | SK's own AutoGen bridge is three generations behind |
| `promptflow-tracing` 1.18.5 | `opentelemetry-sdk>=1.22,<1.39` | `agent-framework-core` needs `opentelemetry-api>=1.39` | prompt flow and Agent Framework **cannot share a lockfile** |
| `agent-framework-foundry-local` (preview) | `foundry-local-sdk>=0.5.1,<0.5.2` | `foundry-local-sdk` **2.0.1** | use Foundry Local's OpenAI-compatible endpoint instead |
| `autogen-ext[openai]` 0.7.5 | `openai>=1.93` | `agent-framework-openai` needs `openai>=2.25,<4` | **compatible** — AutoGen and Agent Framework *do* coexist |

Two conclusions a buyer can act on. First, AutoGen and Agent Framework install side by
side, so the migration can be incremental and the comparison in this repo runs in one
environment. Second, maintenance mode is not free: staying on Semantic Kernel caps the
Azure SDK you are allowed to install, and staying on prompt flow caps your
OpenTelemetry stack.

### 3.6 Model providers (Python)

| Provider | Package | Import | Client |
|---|---|---|---|
| OpenAI (Responses, recommended) | `agent-framework-openai` | `agent_framework.openai` | `OpenAIChatClient` |
| OpenAI (Chat Completions) | same | same | `OpenAIChatCompletionClient` |
| Azure OpenAI | same | same | same clients + `azure_endpoint=` / `credential=` |
| Microsoft Foundry | `agent-framework-foundry` | `agent_framework.foundry` | `FoundryChatClient`, `FoundryAgent`, `FoundryEmbeddingClient` |
| Foundry Local | `agent-framework-foundry-local` | `agent_framework.foundry` | `FoundryLocalClient` |
| Anthropic | `agent-framework-anthropic` | `agent_framework.anthropic` | `AnthropicClient`, `AnthropicFoundryClient`, `AnthropicBedrockClient`, `AnthropicVertexClient` |
| Ollama, Bedrock, Gemini, Mistral, ONNX, Dapr | various | — | — |

Environment variables that matter for this repo:

```
OPENAI_API_KEY            OPENAI_CHAT_MODEL          # Responses client
                          OPENAI_CHAT_COMPLETION_MODEL
ANTHROPIC_API_KEY         ANTHROPIC_CHAT_MODEL
FOUNDRY_PROJECT_ENDPOINT  FOUNDRY_MODEL
AZURE_OPENAI_ENDPOINT     AZURE_OPENAI_CHAT_MODEL    AZURE_OPENAI_API_VERSION
```

### 3.7 Harness Agent — the long-horizon bundle

`create_harness_agent(client=...)` returns a normal `Agent` pre-composed with todo
tracking, plan/execute modes, session file memory, per-call history persistence,
compaction, tool auto-approval rules, web search where the client supports it, and
OpenTelemetry. Everything is switchable (`disable_todo`, `disable_compaction`, ...).
It is the Microsoft answer to "the task outlives one context window".
([harness](https://learn.microsoft.com/en-us/agent-framework/concepts/harness))

### 3.8 Observability

`agent_framework.observability.configure_otel_providers()` reads the standard
`OTEL_*` variables. Spans follow the OpenTelemetry **GenAI semantic conventions**:
`invoke_agent <name>`, `chat <model>`, `execute_tool <fn>`; metrics
`gen_ai.client.operation.duration`, `gen_ai.client.token.usage`,
`agent_framework.function.invocation.duration`.

Controls: `ENABLE_INSTRUMENTATION` (default **true**), `ENABLE_SENSITIVE_DATA`
(default **false**), `ENABLE_CONSOLE_EXPORTERS` (default false).
`FoundryChatClient.configure_azure_monitor()` wires Application Insights straight from
the Foundry project.
([observability](https://learn.microsoft.com/en-us/agent-framework/agents/observability))

---

## 4. Agent services — when the *service* owns the agent

| Service | Python | What the service owns |
|---|---|---|
| Microsoft Foundry Agent Service | ✅ | Prompt/Hosted agent definition, versions, hosted tools, conversations, server-side execution |
| GitHub Copilot | ✅ | Coding-agent runtime, sessions, permissions, shell/file tools, MCP |
| Copilot Studio | ✅ | Published topics, knowledge, actions, plugins, remote execution |
| Anthropic Claude Agent SDK | ✅ | Claude coding-agent runtime, permissions, built-in tools |
| A2A | ✅ | Remote A2A-compliant agent, tasks, sessions |

([agent services](https://learn.microsoft.com/en-us/agent-framework/integrations/by-component/agent-services/))

**Foundry Agent Service** reached GA in 2026 with next-gen runtime, private
networking and MCP auth. Multi-agent shipped as two things: **Connected Agents**
(preview, point-to-point delegation) and **Multi-Agent Workflows** (preview, stateful
orchestration with persistent context).

**Foundry hosted tools** available from `FoundryChatClient` (GA unless noted): code
interpreter, file search, web search, image generation, hosted MCP; plus Bing
grounding (experimental), Azure AI Search (experimental), SharePoint, Fabric, memory
search, computer use, browser automation, A2A (all preview).

---

## 5. Azure services — legacy vs current

| Legacy name / path | Current name / path | Why it changed |
|---|---|---|
| Azure Cognitive Services | Azure AI services | Umbrella rename (2023) |
| Azure AI Studio | Azure AI Foundry → **Microsoft Foundry** | Platform, not a studio |
| Azure OpenAI Service (standalone) | **Foundry Models** (Azure OpenAI still reachable) | One catalogue, one endpoint, model router |
| Azure Cognitive Search | **Azure AI Search** + **Foundry IQ** | Retrieval became a first-class knowledge plane |
| Azure AI Agent Service (classic) | **Foundry Agent Service** | New runtime, private networking, MCP auth |
| `azure-ai-inference` beta | Foundry clients / OpenAI v1 surface | Beta stalled Feb 2025 |
| Azure AI Content Safety SDK | **Foundry guardrails and controls** | Guardrails move to intervention points: input, tool call, tool response, output |
| Azure ML prompt flow | **Foundry evaluations + observability** | Evaluation became part of the control plane |
| Azure Bot Service + Bot Framework SDK | **Microsoft 365 Agents SDK** | Bot Framework LTS ended December 2025 |
| Service principal for an app | **Microsoft Entra Agent ID** (GA April 2026) | Agents get governable, revocable identities |

Key Foundry primitives as of 2026: **Workflows**, **Foundry IQ** (serverless retrieval
over Work IQ, Fabric IQ, Azure SQL, file search and MCP sources behind one SLA-backed
endpoint), **Toolboxes** (versioned tool bundles, MCP), **Model Router**, **Memory
Stores**, **Red Teams**, **Foundry Control Plane** observability.

`azure-ai-projects` 2.6.0 `AIProjectClient` operation groups: agents, toolboxes,
deployments, connections, datasets, indexes, evaluations, memory stores, skills,
red teams.

---

## 6. Identity — the part every architect asks about

The whole Azure AI data plane authenticates through **Microsoft Entra**. The service
principal in this repo proves the chain end to end without needing any resource:

```python
from azure.identity import EnvironmentCredential      # reads AZURE_TENANT_ID / CLIENT_ID / CLIENT_SECRET
cred = EnvironmentCredential()
cred.get_token("https://ai.azure.com/.default")                # Foundry
cred.get_token("https://cognitiveservices.azure.com/.default") # Azure AI services
cred.get_token("https://search.azure.com/.default")            # Azure AI Search
```

Verified on 2026-09-14 against the workshop service principal: all four audiences
(including Microsoft Graph) issue tokens; the principal holds **no** subscription
role assignments, so data-plane calls would return 403. That is exactly the lesson:
**authentication and authorisation are separate**, and the stack makes the seam
visible.

Entra Agent ID (GA April 2026) extends this: an agent is a directory object you can
see, govern and revoke like a user.

---

## 7. Standards the stack now speaks

- **MCP (Model Context Protocol)** — tools. Local (`MCPStdioTool`,
  `MCPStreamableHTTPTool`, `MCPWebsocketTool`) and hosted (`client.get_mcp_tool(...)`).
  Agent Framework propagates W3C trace context into MCP `tools/call` `_meta` for
  client-opened transports.
- **A2A (Agent2Agent)** — agent-to-agent calls, exposed both as an agent service and
  as `FoundryChatClient.get_a2a_tool(...)`.
- **OpenTelemetry GenAI semantic conventions** — traces, metrics and logs.

Microsoft's own framing for 1.0 was "native MCP and A2A interoperability".

---

## 8. Found while building (verified against the installed packages)

Documentation lags packages. These were discovered by running the code on
2026-09-14, not by reading about it, and each one is handled in the repository.

| Finding | Evidence | Where it is handled |
|---|---|---|
| Orchestration builders ship in a **separate** package, `agent-framework-orchestrations` 1.1.1, not in `agent-framework-core` | `ModuleNotFoundError: agent_framework_orchestrations` until installed | `pyproject.toml` dependencies |
| `foundry-local-sdk` 2.x renamed its module: `import foundry_local_sdk`, not the 0.5.x `foundry_local`; the manager is built from a `Configuration`, and a running one is `FoundryLocalManager.instance` | `import foundry_local` fails on 2.0.1 | `providers.py`, `foundry_local_demo.py` |
| A chat client needs `FunctionInvocationLayer` in its bases, or `Agent` warns "does not support function invoking" and tools never run | Warning raised by `agent_framework._agents` | `offline.py` |
| `FileCheckpointStorage.list_checkpoints` requires `workflow_name=`; the built workflow's `.name` is generated | `TypeError` without it | `group_chat_demo.py` |
| An `approval_mode="always_require"` tool inside `GroupChatBuilder` pauses the whole workflow with a `request_info` event, and `run(checkpoint_id=..., responses=...)` resumes it in a separate OS process that discovers the pending request from the checkpoint files alone | Observed end to end: the resume process read 5 checkpoint files; a replayed resume executed no action | `group_chat_demo.py`, `resume_worker.py` |
| AutoGen's own `ReplayChatCompletionClient` reports `function_calling=False`, so `AssistantAgent` refuses tools on the offline path | `ValueError: The model does not support function calling.` | `autogen_demo.py` |
| Span provider names differ by layer: `invoke_agent` reports `gen_ai.provider.name = microsoft.agent_framework`, while `chat` reports the model provider | Captured with an in-memory exporter | `observability_demo.py`, deck slide 30 |
| `azure-ai-evaluation` 1.18 still pulls `azure-ai-inference` 1.0.0b9 transitively, so the stalled beta is installed even though nothing here imports it | `msai-demo doctor --packages` | deck slide 16 |
| Microsoft's observability page says `opentelemetry-sdk` is installed by default, but `agent-framework-core` 1.18 requires only `opentelemetry-api`; without the SDK an in-memory exporter cannot be built | `ModuleNotFoundError: opentelemetry.sdk` in a fresh environment | `pyproject.toml` dependencies |
| numpy stubs pulled in by the OpenAI and Anthropic SDKs need Python 3.12 to parse, so `mypy` runs at 3.12 while Ruff enforces 3.11 syntax | `Type statement is only supported in Python 3.12` | `pyproject.toml` |

---

## 9. Sources

Microsoft Learn — Agent Framework:
[overview](https://learn.microsoft.com/en-us/agent-framework/overview/agent-framework-overview) ·
[harness](https://learn.microsoft.com/en-us/agent-framework/concepts/harness) ·
[workflow orchestrations](https://learn.microsoft.com/en-us/agent-framework/workflows/orchestrations/) ·
[group chat](https://learn.microsoft.com/en-us/agent-framework/workflows/orchestrations/group-chat) ·
[observability](https://learn.microsoft.com/en-us/agent-framework/agents/observability) ·
[model providers](https://learn.microsoft.com/en-us/agent-framework/integrations/by-component/model-providers/) ·
[agent services](https://learn.microsoft.com/en-us/agent-framework/integrations/by-component/agent-services/) ·
[AutoGen migration](https://learn.microsoft.com/en-us/agent-framework/migration-guide/from-autogen/) ·
[Semantic Kernel migration](https://learn.microsoft.com/en-us/agent-framework/migration-guide/from-semantic-kernel/) ·
[Python 2026 significant changes](https://learn.microsoft.com/en-us/agent-framework/support/upgrade/python-2026-significant-changes) ·
[MCP tools](https://learn.microsoft.com/en-us/agent-framework/agents/tools/local-mcp-tools) ·
[A2A agents](https://learn.microsoft.com/en-us/agent-framework/integrations/by-component/agent-services/a2a)

Microsoft Learn — Foundry, Azure and Microsoft 365:
[Foundry Agent Service](https://learn.microsoft.com/en-us/azure/foundry/agents/overview) ·
[guardrails](https://learn.microsoft.com/en-us/azure/foundry/guardrails/guardrails-overview) ·
[Foundry IQ](https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/what-is-foundry-iq) ·
[AI Search document-level access](https://learn.microsoft.com/en-us/azure/search/search-document-level-access-overview) ·
[Foundry Local](https://learn.microsoft.com/en-us/azure/foundry-local/what-is-foundry-local) ·
[Bot Framework → Microsoft 365 Agents SDK (Python)](https://learn.microsoft.com/en-us/microsoft-365/agents-sdk/bf-migration-python)

Microsoft Learn — identity:
[Microsoft Entra Agent ID](https://learn.microsoft.com/en-us/entra/agent-id/what-is-microsoft-entra-agent-id) ·
[autonomous agent token flow](https://learn.microsoft.com/en-us/entra/agent-id/autonomous-agent-authentication-authorization-flow)

Microsoft blogs:
[Semantic Kernel and Microsoft Agent Framework](https://devblogs.microsoft.com/agent-framework/semantic-kernel-and-microsoft-agent-framework/) ·
[Agent Framework 1.0](https://devblogs.microsoft.com/agent-framework/microsoft-agent-framework-version-1-0/) ·
[orchestration patterns reach 1.0](https://devblogs.microsoft.com/agent-framework/agent-frameworks-orchestration-patterns-reach-1-0/)

PyPI JSON API, read 2026-09-14, for every version in section 2.

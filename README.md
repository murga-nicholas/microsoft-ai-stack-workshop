# Microsoft AI stack — a runnable workshop

Every technology Microsoft ships for building agents in Python, in one repository:
**Microsoft Agent Framework**, **Microsoft Foundry**, **Microsoft 365 Agents SDK**,
**Entra**, **MCP** and **A2A** — beside the **AutoGen**, **Semantic Kernel**,
**Bot Framework**, **prompt flow** and **Content Safety** code they replace.

**Built by Mykola Murha — Data and AI Engineer, DataArt.**

Twenty-four technologies, twenty-four modules, one command each. There is a
companion deck, but you do not need it: this README is self-contained, and every
command below has been run against the code in this repository.

## The thing that makes this repo different

**Every demo runs on a laptop with no cloud account, no API key and no Azure
subscription — and none of them pretend.**

Each result carries a `mode` saying exactly how it was produced:

| `mode` | Meaning |
|---|---|
| `local_execution` | Real local computation or protocol execution. Nothing simulated. |
| `local_contract` | Real SDK and application code, with an explicitly synthetic external response. Names its fixture. |
| `live_model` | A model was actually invoked. |
| `live_identity` | A token was actually acquired from Microsoft Entra. |
| `live_service` | A non-model service actually ran the work. |
| `not_run` | A prerequisite was missing. It says which. |

`status` is separate: a real HTTP 403 is `mode="live_service"`, `status="blocked"` —
a *successful* demonstration of an authorisation boundary, not a broken demo.
`contracts.result()` raises if a payload's evidence contradicts its mode, so a green
console cannot quietly become a claim nobody checked.

## What this project proves

| # | Claim | Where to look |
|---|---|---|
| 1 | AutoGen and Agent Framework run the **same task, in one environment**, judged on identical computed checks | [`group_chat_demo.py`](src/msai_demo/group_chat_demo.py) |
| 2 | The simulated business action cannot run before a human approves — in Agent Framework the tool's `approval_mode` gates it, in AutoGen application code does | [`group_chat_demo.py`](src/msai_demo/group_chat_demo.py), [`autogen_demo.py`](src/msai_demo/autogen_demo.py) |
| 3 | Both lanes resume in a **separate OS process** from disk alone, and a replayed resume executes nothing | [`resume_worker.py`](src/msai_demo/resume_worker.py) |
| 4 | Who owns each recovery responsibility is named function by function, and a test imports every function named | [`responsibility_matrix()`](src/msai_demo/group_chat_demo.py) |
| 5 | Staying on the legacy packages carries three verifiable dependency constraints | [`docs/research.md` §3.5](docs/research.md) |
| 6 | Model choice is one module; nothing downstream knows the vendor | [`providers.py`](src/msai_demo/providers.py) |
| 7 | The offline path is the **real** framework — a chat client in the same class hierarchy as `OpenAIChatClient` | [`offline.py`](src/msai_demo/offline.py) |
| 8 | Microsoft Entra authentication genuinely runs, and shows that a token is not access | [`azure_identity_demo.py`](src/msai_demo/azure_identity_demo.py) |
| 9 | No credential value is ever printed, logged or returned | [`doctor.py`](src/msai_demo/doctor.py) |
| 10 | Figures, transcripts and the workflow graph on the slides are read from recorded runs | [`deck/collect_facts.py`](deck/collect_facts.py) |

---

## Quickstart

About five minutes on a clean machine. Every command runs from the repository root.

### 1. Install `uv`

The Python package and project manager
([official docs](https://docs.astral.sh/uv/getting-started/installation/)):

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Restart the terminal, then confirm:

```bash
uv --version
```

### 2. Get the code and build the environment

```powershell
git clone <this-repository>
cd microsoft-ai-stack-workshop
Copy-Item .env.example .env
uv sync --frozen --group legacy
```

```bash
git clone <this-repository>
cd microsoft-ai-stack-workshop
cp .env.example .env
uv sync --frozen --group legacy
```

**Copy `.env.example` unchanged and leave every credential blank.** You do not need
a single key to continue.

`--group legacy` installs AutoGen alongside Agent Framework, which is what makes the
side-by-side comparison run in one environment.

### 3. See what you have

```bash
uv run msai-demo list
```

```bash
uv run msai-demo doctor
```

`doctor` prints installed package versions, credential **presence** (never a value),
and which demos can run their live path on this machine. Every demo that cannot will
still run — it just tells you which path it took.

### 4. Run the centrepiece

```bash
uv run msai-demo group-chat
```

One business task — cost a six-week support pilot and refuse to accept it without a
human — run twice: once on AutoGen's `RoundRobinGroupChat`, once on Agent Framework's
`GroupChatBuilder`. Both lanes **pause** before the simulated business action and
write their state under `.msai_checkpoints/`. A separate Python process then
resumes each run from disk and applies the decision; a second resume proves the
action is not executed twice. The JSON output (`--format json`) records both
process ids, the files each resume read, and the computed checks.

```bash
uv run msai-demo all --lane current
```

```bash
uv run msai-demo all
```

---

## The technologies, and the command for each

Each one has its own module, its own test module, and its own slide.

### The legacy estate

| Command | Technology | What it shows |
|---|---|---|
| `msai-demo autogen` | AutoGen 0.7.5 | Round-robin group chat, termination, `save_state`/`load_state` |
| `msai-demo semantic-kernel` | Semantic Kernel 1.44 | Kernel, plugin, filter — and the `azure-ai-projects<2.5` pin |
| `msai-demo bot-framework` | Bot Framework SDK | One channel activity through the retired adapter |
| `msai-demo promptflow` | prompt flow | A small local DAG flow, and its OpenTelemetry pin conflict |
| `msai-demo azure-ai-inference` | `azure-ai-inference` | The stalled beta request, beside its replacement |
| `msai-demo content-safety` | Azure AI Content Safety | Classify one prompt, then apply a threshold yourself |

### The current runtime

| Command | Technology | What it shows |
|---|---|---|
| `msai-demo agent-framework` | Agent Framework | Agent, session, tool, streaming, structured output, grounding |
| `msai-demo group-chat` | Both lanes | Separate-process resume, computed checks, responsibility matrix |
| `msai-demo workflow` | Agent Framework Workflows | Typed graph, conditional edge, approval pause, checkpoints |
| `msai-demo harness` | Harness Agent | Planning, todos, memory, compaction, tool approval |

### Channels and protocols

| Command | Technology | What it shows |
|---|---|---|
| `msai-demo m365-agents` | Microsoft 365 Agents SDK | The same handler, a new adapter |
| `msai-demo mcp` | Model Context Protocol | Discover and call a tool over MCP |
| `msai-demo a2a` | Agent2Agent | Delegate a task, track status, collect an artifact |

### Microsoft Foundry

| Command | Technology | What it shows |
|---|---|---|
| `msai-demo azure-ai-projects` | `azure-ai-projects` 2.6 | List model deployments through `AIProjectClient` |
| `msai-demo foundry-models` | Foundry Models | `FoundryChatClient`, its hosted tools and their lifecycle |
| `msai-demo foundry-agent-service` | Foundry Agent Service | When the service owns the agent, not your process |
| `msai-demo foundry-local` | Foundry Local | Inference on the laptop, through an OpenAI-compatible port |
| `msai-demo ai-search` | Azure AI Search | Hybrid query and citations over an index you own |
| `msai-demo foundry-iq` | Foundry IQ | A managed knowledge base over configured sources, on AI Search |
| `msai-demo foundry-guardrails` | Foundry guardrails | Four intervention points, not one prompt classification |

### Identity, operations, quality

| Command | Technology | What it shows |
|---|---|---|
| `msai-demo azure-identity` | Microsoft Entra | **Real tokens**, and the authorisation gate behind them |
| `msai-demo entra-agent-id` | Entra Agent ID | An agent as a governable directory object |
| `msai-demo otel` | OpenTelemetry GenAI | The span tree a run produces, and the opt-in export |
| `msai-demo evaluation` | `azure-ai-evaluation` | Real `evaluate()` over JSONL with two code evaluators; one case fails on purpose |

Every command accepts `--execution offline|live` and `--format pretty|json`.

---

## Going live

Live paths are opt-in, never a silent fallback, and they fail **before** spending
money if something is missing.

### OpenAI and Anthropic — the cross-vendor group chat

```dotenv
OPENAI_API_KEY=sk-proj-...
ANTHROPIC_API_KEY=sk-ant-...
```

```bash
uv run msai-demo group-chat --execution live
```

**This spends money.** Both keys are required: there is no OpenAI substitute for the
Anthropic participant, because a cross-vendor demo with one vendor is not a
cross-vendor demo.

### Microsoft Entra — this one works with only a service principal

```dotenv
AZURE_TENANT_ID=...
AZURE_CLIENT_ID=...
AZURE_CLIENT_SECRET=...
```

```bash
uv run msai-demo azure-identity --execution live
```

```bash
uv run msai-demo doctor --probe
```

Acquires a real token for four Azure AI audiences and reports the `aud` claim, the
expiry and the `roles` claim — never the token. Then calls ARM and shows the
subscription list, which for a principal with no role assignments is **empty**. That
is the lesson: authentication and authorisation are different things.

### Microsoft Foundry

```dotenv
FOUNDRY_PROJECT_ENDPOINT=https://<resource>.services.ai.azure.com/api/projects/<project>
FOUNDRY_MODEL=gpt-4o-mini
AZURE_SEARCH_ENDPOINT=https://<resource>.search.windows.net
```

```bash
uv run msai-demo foundry-models --execution live
```

Without a role assignment these return `status="blocked"`,
`error.code="authorization_denied"` — the correct, honest outcome, and exactly what
an unprovisioned tenant looks like.

### Semantic Kernel — deliberately not installed

Semantic Kernel 1.44.1 pins `azure-ai-projects>=1.0,<2.5`; this repository needs
2.6. They cannot share a lockfile. `msai-demo semantic-kernel` explains that and
prints the command that runs it anyway, in an isolated environment:

```bash
uv run --isolated --with "semantic-kernel>=1.44,<2" python -c "import semantic_kernel; print(semantic_kernel.__version__)"
```

---

## Observability

Nothing leaves the machine unless you ask. Agent Framework instruments by default, so
this repository turns it **off** before any client is constructed, and only `--trace`
turns it back on.

```bash
uv run msai-demo otel
```

```bash
uv run msai-demo otel --trace azure
```

`ENABLE_SENSITIVE_DATA` records prompts, responses, tool arguments and tool results.
Leave it off outside development.

---

## Build the deck

```bash
uv run --group deck python deck/collect_facts.py
```

```bash
uv run --group deck python deck/build_deck.py
```

The first command runs the demos the deck quotes — the group chat, the workflow,
evaluation, guardrails, OpenTelemetry and, when a service principal is configured,
a **live** Entra identity run — and writes their payloads to `deck/facts.json`,
with paths made repository-relative. The second renders 48 slides (36 presented,
plus a take-home appendix) from that, the installed package versions and the
shared pilot costing. Process ids, event logs, the responsibility matrix, scores,
span names, the workflow graph and dollar figures are read from those runs, and the
build refuses to start without `facts.json`. Explanatory text is still authored,
so it is reviewed like any other prose.

The build also refuses to write a deck whose shapes overflow the safe area, whose
text boxes are too small for their text, or whose headline wraps to a second line —
layout is a test, not a proofread. `--draft` writes the file anyway, for inspecting
a failing layout; never present a draft build.

The presenter script lives in `deck/speaker_notes.md`, one timed section per slide.
The build copies each section into that slide's presenter notes and fails if a slide
has no section or a section no longer matches a slide.

---

## Tests and quality gates

```bash
uv run ruff format --check src/ tests/ deck/
```

```bash
uv run ruff check src/ tests/ deck/
```

```bash
uv run mypy
```

```bash
uv run pytest --cov=msai_demo --cov-report=term-missing
```

```bash
uv lock --check
```

All five must pass before this is shared or presented.

Know what the suite does and does not cover. These are **offline unit and contract
tests**: they never call OpenAI, Anthropic, Azure or a local model service. They
prove the application behaviour under controlled responses. They do **not** prove an
Azure integration works against a provisioned tenant — that is what `doctor --probe`
and a live run are for, and that distinction is exactly why `mode` exists.

- Ruff formats and lints at 79 columns across 26 rule families.
- `mypy --strict` covers every source module. `Any` is confined to SDK boundaries and
  converted into local `TypedDict` contracts immediately.
- Coverage is enforced at **100% statements and branches**, with no `pragma` escapes.
- Offline tests use *first-party* fakes — AutoGen's `ReplayChatCompletionClient`, and
  a chat client built on Agent Framework's own `BaseChatClient` — so neither
  framework is ever mocked by the other.

`mypy` is configured for Python 3.12 even though the package supports 3.11+: numpy,
pulled in transitively by the OpenAI and Anthropic SDKs, ships stubs that need 3.12
to parse, and a stub syntax error cannot be suppressed. Ruff's
`target-version = "py311"` is what actually keeps this code 3.11-compatible.

---

## Project map

```text
.
|-- data/microsoft_ai_stack_notes.md   # local, sourced grounding corpus
|-- docs/
|   |-- research.md                    # every external claim, dated and sourced
|   `-- module_spec.md                 # the contract every demo module follows
|-- src/msai_demo/
|   |-- cli.py                         # one entry point, one row per technology
|   |-- contracts.py                   # the mode/status result envelope
|   |-- scenario.py                    # the shared business task and its arithmetic
|   |-- runtime.py                     # .env, provider resolution, telemetry gate
|   |-- providers.py                   # the entire model-provider switch
|   |-- offline.py                     # a real chat client with scripted tokens
|   |-- doctor.py                      # readiness that never prints a value
|   |-- resume_worker.py               # the separate process that resumes a run
|   `-- <24 technology modules>.py
|-- deck/
|   |-- theme.py                       # the DataArt design system, as code
|   |-- components.py                  # the repeated slide shapes
|   |-- diagrams.py                    # architecture schemas as native shapes
|   |-- content_*.py                   # the slides
|   |-- collect_facts.py               # records the runs the slides quote
|   |-- facts.json                     # those recorded runs
|   `-- build_deck.py                  # build plus layout and headline checks
|-- tests/                             # offline, 100% statements and branches
|-- .env.example                       # every variable this code reads
|-- pyproject.toml                     # project, tooling and lint configuration
`-- uv.lock                            # the authoritative dependency set
```

---

## Safety, cost and generated files

- **No credential value is ever printed or committed.** `doctor` reports booleans,
  `.env` is git-ignored, `.env.example` ships blank fields.
- **Telemetry is off by construction**, not by convention.
- **Every loop is bounded** by a turn cap, so a runaway agent becomes a handled error
  rather than an open-ended bill.
- **Irreversible tools require approval.** `accept_proposal` is a simulated
  business action declared `approval_mode="always_require"`; it cannot execute
  before the decision arrives, and an idempotency store refuses to run it twice.
- **Treat retrieved text as untrusted.** Documents, tool output and other agents'
  replies all re-enter the prompt as text a model may obey. A virtual filesystem path
  is ergonomics, not a sandbox.
- **Cost**: the offline path is free. Live paths consume OpenAI, Anthropic or Azure
  credit and say so before they start.
- **Generated and git-ignored**: `.venv/`, `.msai_workspace/`, `.msai_checkpoints/`,
  `.pytest_tmp/` and the tool caches. Delete any of them safely.

---

## Troubleshooting

**`uv: command not found`** — restart the terminal after installing `uv`.

**`msai-demo group-chat --execution live` stops immediately** — it preflights both
keys before the first call, so a half-configured machine cannot spend money and then
fail. Set `ANTHROPIC_API_KEY` as well as `OPENAI_API_KEY`.

**A Foundry demo says `authorization_denied`** — the token was acquired and the
service was reached; the principal has no role assignment on that resource. Grant one
in the Azure portal, or keep running it offline.

**`msai-demo foundry-local --execution live` says `service_unavailable`** — install
Foundry Local and start the service. The offline run never needs it. Note that `foundry-local-sdk` 2.x exports `foundry_local_sdk`, not
the 0.5.x `foundry_local`; older blog posts use the old name.

**A value in `.env` seems ignored** — real shell variables always win over the file.
Check with `echo $env:OPENAI_API_KEY` (PowerShell) or `echo $OPENAI_API_KEY` (bash).

**`ModuleNotFoundError: anthropic.types.beta.beta_managed_agents_...` on Windows** — the
Anthropic SDK ships module filenames long enough to exceed Windows' 260-character
path limit when the repository lives in a deep folder. Clone to a short path such as
`C:\src\microsoft-ai-stack-workshop`, or enable long paths once from an elevated
PowerShell:

```powershell
New-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem" -Name LongPathsEnabled -Value 1 -PropertyType DWORD -Force
```

**`uv python install` warns about a missing target directory on Windows** — it is a
symlink permission warning; the interpreter is still installed and `uv sync` works.

---

## Further reading

**Microsoft Agent Framework** —
[overview](https://learn.microsoft.com/en-us/agent-framework/overview/agent-framework-overview) ·
[orchestrations](https://learn.microsoft.com/en-us/agent-framework/workflows/orchestrations/) ·
[group chat](https://learn.microsoft.com/en-us/agent-framework/workflows/orchestrations/group-chat) ·
[harness](https://learn.microsoft.com/en-us/agent-framework/concepts/harness) ·
[observability](https://learn.microsoft.com/en-us/agent-framework/agents/observability) ·
[migrate from AutoGen](https://learn.microsoft.com/en-us/agent-framework/migration-guide/from-autogen/) ·
[Python 2026 significant changes](https://learn.microsoft.com/en-us/agent-framework/support/upgrade/python-2026-significant-changes)

**Microsoft Foundry** —
[Agent Service](https://learn.microsoft.com/en-us/azure/foundry/agents/overview) ·
[guardrails](https://learn.microsoft.com/en-us/azure/foundry/guardrails/guardrails-overview) ·
[model providers](https://learn.microsoft.com/en-us/agent-framework/integrations/by-component/model-providers/) ·
[agent services](https://learn.microsoft.com/en-us/agent-framework/integrations/by-component/agent-services/)

**Platform** —
[Bot Framework to Microsoft 365 Agents SDK](https://learn.microsoft.com/en-us/microsoft-365/agents-sdk/bf-migration-python)

Everything above was read on **2026-09-14**; see [`docs/research.md`](docs/research.md)
for the claim-by-claim record.

---

## About

Built and maintained by **Mykola Murha**, Data and AI Engineer at **DataArt**.

I build agent systems that survive contact with production: explicit control flow,
typed boundaries, least-privilege tool access, approval as a durable state
transition, and observability wired in from the first commit rather than bolted on
after the first incident. This repository is a compact, honest demonstration of that
approach across the whole Microsoft AI stack.

Questions, corrections and merge requests are welcome.

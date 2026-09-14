# Microsoft AI stack — local retrieval corpus

Paraphrased notes from official Microsoft documentation, read 2026-09-14. Each note
carries an explicit `Source:` line. Keeping the corpus local is what makes retrieval
in this workshop repeatable and independent of any website being reachable.

---

## Section: agent-framework-overview

Microsoft Agent Framework is a multi-language SDK for building AI agents and
multi-agent workflows. It brings together four areas: agents, the Harness agent,
workflows, and integrations. It supports .NET, Python and Go, with Go in public
preview. Version 1.0 reached general availability on 2026-04-03.

Source: https://learn.microsoft.com/en-us/agent-framework/overview/agent-framework-overview

## Section: agent-framework-lineage

Agent Framework is the direct successor to both Semantic Kernel and AutoGen, created
by the same teams. It combines AutoGen's simple abstractions for single- and
multi-agent patterns with Semantic Kernel's enterprise features: session-based state
management, type safety, filters, telemetry, and broad model support. It adds
graph-based workflows for explicit control over multi-agent execution paths.

Source: https://learn.microsoft.com/en-us/agent-framework/overview/agent-framework-overview

## Section: semantic-kernel-status

Semantic Kernel v1.x is in maintenance mode, not retirement. Critical bugs and
security issues continue to be addressed, and support continues for at least one year
after Agent Framework reached general availability. New feature work happens in Agent
Framework.

Source: https://devblogs.microsoft.com/agent-framework/semantic-kernel-and-microsoft-agent-framework/

## Section: autogen-status

AutoGen started as a Microsoft Research project and pioneered group chat and the
event-driven agent runtime. Its concepts carried forward into Agent Framework. The
`autogen-agentchat` package last published version 0.7.5 on 2025-09-30.

Source: https://learn.microsoft.com/en-us/agent-framework/migration-guide/from-autogen/

## Section: agents-vs-workflows

Use an agent when the task is open-ended or conversational, when you need autonomous
tool use and planning, or when a single model call with tools is enough. Use a
workflow when the process has well-defined steps, when you need explicit control over
execution order, or when multiple agents and functions must coordinate. If you can
write a plain function to handle the task, write the function instead.

Source: https://learn.microsoft.com/en-us/agent-framework/overview/agent-framework-overview

## Section: orchestration-patterns

Agent Framework ships five orchestration patterns, all stable in 1.0: sequential
(fixed pipeline), concurrent (fan out and aggregate), group chat (a shared
conversation with an orchestrator choosing the next speaker), handoff (control
transfers between agents), and Magentic (a manager plans the work for a team of
specialists). They are built from `agent_framework.orchestrations`.

Source: https://learn.microsoft.com/en-us/agent-framework/workflows/orchestrations/

## Section: group-chat-topology

Group chat assembles agents in a star topology with an orchestrator in the middle.
Participants do not share one session object; after each turn the orchestrator
broadcasts the response to every other participant so each session is synchronised
with the full conversation before that participant speaks.

Source: https://learn.microsoft.com/en-us/agent-framework/workflows/orchestrations/group-chat

## Section: group-chat-selection

Speaker selection has three modes. A `selection_func` is ordinary Python over
`GroupChatState`. An `orchestrator_agent` is a full agent with tools, context and
observability that decides who speaks next. A custom `orchestrator` gives complete
control, but then `max_rounds` and `termination_condition` must be set on the
orchestrator itself because the builder's values are ignored.

Source: https://learn.microsoft.com/en-us/agent-framework/workflows/orchestrations/group-chat

## Section: human-in-the-loop

Agent Framework workflows add request and response: a workflow can pause, surface a
typed request, and continue when the answer arrives via `workflow.run(responses=...)`.
AutoGen's `Team` abstraction runs continuously once started and has no built-in way to
pause for human input, so that behaviour had to be written outside the framework.

Source: https://learn.microsoft.com/en-us/agent-framework/migration-guide/from-autogen/

## Section: harness-agent

The Harness is an opinionated, batteries-included agent runtime for long-running work.
`create_harness_agent` returns a normal `Agent` already composed with todo tracking,
plan and execute modes, session file memory, per-model-call history persistence,
compaction, tool auto-approval rules, and OpenTelemetry. Each capability can be
disabled individually.

Source: https://learn.microsoft.com/en-us/agent-framework/concepts/harness

## Section: observability

Agent Framework emits traces, logs and metrics following the OpenTelemetry GenAI
semantic conventions. The spans are `invoke_agent`, `chat` and `execute_tool`. The
metrics are `gen_ai.client.operation.duration`, `gen_ai.client.token.usage` and
`agent_framework.function.invocation.duration`. Instrumentation is enabled by default;
sensitive-data capture is disabled by default.

Source: https://learn.microsoft.com/en-us/agent-framework/agents/observability

## Section: model-providers

Python model providers include Azure OpenAI and OpenAI through
`agent_framework.openai`, Microsoft Foundry through `agent_framework.foundry`,
Anthropic through `agent_framework.anthropic`, plus Foundry Local, Ollama, Amazon
Bedrock, Google Gemini and Mistral. The provider supplies inference; the application
still owns the agent definition, tools, middleware and session policy.

Source: https://learn.microsoft.com/en-us/agent-framework/integrations/by-component/model-providers/

## Section: foundry-clients

`FoundryChatClient` connects to a model deployed in a Microsoft Foundry project and
uses the Responses endpoint; the application owns the agent. `FoundryAgent` connects
to a Prompt Agent or Hosted Agent that Foundry itself defines and runs. Both live in
the `agent-framework-foundry` package.

Source: https://learn.microsoft.com/en-us/agent-framework/integrations/by-component/model-providers/microsoft-foundry

## Section: foundry-rename

Azure AI Studio became Azure AI Foundry in November 2024, and Azure AI Foundry became
Microsoft Foundry at Ignite on 2025-11-18. The rename was formalised in the Microsoft
Product Terms effective 2026-01-01. Dropping "Azure" signals that agents are a
first-class Microsoft platform rather than one Azure service.

Source: https://azure.microsoft.com/en-us/products/ai-foundry

## Section: foundry-agent-service

Foundry Agent Service is generally available. It offers Connected Agents for
point-to-point delegation and Multi-Agent Workflows for stateful orchestration with
persistent shared context, and it connects agents to MCP-enabled tools. The service
owns the agent definition, versions, hosted tools, conversations and execution.

Source: https://learn.microsoft.com/en-us/azure/foundry/agents/overview

## Section: guardrails

Microsoft Foundry guardrails apply to both models and agents. A control names the risk
to detect, the intervention points to scan, and the action to take. Four intervention
points are supported: user input, tool call, tool response, and output. Tool call and
tool response are in preview. Guardrails replace hand-rolled Content Safety calls
around a single prompt.

Source: https://learn.microsoft.com/en-us/azure/foundry/guardrails/guardrails-overview

## Section: entra-agent-id

Microsoft Entra Agent ID has been generally available since April 2026. Agents get
first-class directory identities that are visible, governable and revocable in the
same way as users and service principals. Azure AI data planes authenticate through
Entra, so acquiring a token is the first step of every call.

Source: https://learn.microsoft.com/en-us/azure/foundry/agents/overview

## Section: microsoft-365-agents-sdk

The Bot Framework SDK is retired, with final long-term support ending in December
2025. The Microsoft 365 Agents SDK is the replacement and is generally available for
C#, JavaScript and Python. Migration keeps the existing Azure Bot registration and
swaps `botbuilder-*` packages for `microsoft-agents-*` packages.

Source: https://learn.microsoft.com/en-us/microsoft-365/agents-sdk/bf-migration-python

## Section: python-renames-2026

Agent Framework Python renamed many public names in 2026. `ChatAgent` became `Agent`,
`ChatMessage` became `Message`, `AgentThread` became `AgentSession`, `@ai_function`
became `@tool`, `run_stream(...)` became `run(..., stream=True)`, `model_id` became
`model`, and the orchestration builders moved to `agent_framework.orchestrations` and
take constructor arguments instead of fluent methods.

Source: https://learn.microsoft.com/en-us/agent-framework/support/upgrade/python-2026-significant-changes

## Section: dotenv-behaviour

Agent Framework does not load `.env` files automatically. Either call `load_dotenv()`
at the start of the application, set variables in the shell, or pass an explicit
`env_file_path` to `load_settings`.

Source: https://learn.microsoft.com/en-us/agent-framework/overview/agent-framework-overview

## Section: protocols

Agent Framework 1.0 shipped with native Model Context Protocol and Agent2Agent
interoperability. MCP tools are either local, opened by the agent process, or hosted
and invoked by the provider. Trace context is propagated into MCP `tools/call`
requests only for client-opened transports, because hosted calls are issued by the
provider runtime.

Source: https://learn.microsoft.com/en-us/agent-framework/agents/observability

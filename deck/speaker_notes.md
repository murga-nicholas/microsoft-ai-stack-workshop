# Speaker notes - Microsoft AI stack workshop

The presenter script for `microsoft_ai_stack.pptx`. The deck build copies each section into that slide's presenter notes, so the script and the slides stay together.

How to read it:

- Times follow the agenda on slide 3: 36 presented slides in 60 minutes, including five minutes of Q&A. The appendix (slides 37-48) is not presented; its notes are for questions and for readers.
- "Say" is the script. "Show" tells you where to point. "Demo" is an optional live command; skip it if you are behind. "If asked" holds facts for questions. "Next" is the bridge to the following slide.
- The audience is mixed: sales, managers, architects and Python developers. Each technology slide works on two levels: the use-case band for everyone, the schema and code for the technical half.
- Every demo command runs offline and prints its mode. Say the mode out loud when you run one; it is what keeps a local demonstration from sounding like a cloud call.

<!-- slide: content_open.slide_title -->
### 1. Cover - 0:00-0:45

Say:
Good morning. For the next hour we look at the Microsoft AI stack as it stands in September 2026: Microsoft Agent Framework for agent code, Microsoft Foundry for models and managed agents, Foundry Local for on-device inference, and Entra Agent ID for agent identity. We also look at the legacy pieces many teams still run, AutoGen and Semantic Kernel, and at what replaced them.

One promise before we start, and it is on the slide: every command I run demonstrates a mechanism and reports its mode - local execution, local contract, or live. The use-case bands you will see on every slide describe illustrative applications, not systems this repository deployed.

Next:
Let us start with what you can actually build.

<!-- slide: content_open.slide_jobs -->
### 2. Four jobs a junior can ship - 0:45-2:15

Say:
Before any product names, four jobs. On the left is Microsoft's own Foundry agent catalog - 48 starter agents in this capture. Each starter is a use-case pattern, not a finished product.

On the right, four jobs a junior developer can deliver:
- Knowledge Base Q&A: answers from your documents, with citations. That is Azure AI Search or Foundry IQ, slide 30.
- Meeting Notes Summarizer: decisions and owners from a transcript. A Foundry prompt agent with file search.
- Log File Analyzer: clusters errors and builds a timeline, using code interpreter.
- Test Case Generator: happy, edge and negative cases from a GitHub spec, using the GitHub MCP tool, slide 19.

Show:
Point at callout 1, Internal Policy Q&A, then read the line under the screenshot: pick a starter agent, inspect its tools and data, configure access, test.

Say:
Every job has the same shape: a model, instructions, one or two tools, and a human who reviews the draft. Keep that shape in mind; the whole talk is about which Microsoft piece provides each part.

If asked:
- The agent catalog is marked Preview in the portal. "48" is what was visible when the screenshot was taken on 2026-09-14.

Next:
Here is how the hour is organised.

<!-- slide: content_open.slide_agenda -->
### 3. Agenda - 2:15-3:00

Say:
Eight segments. Three more minutes of opening, then eight minutes of lineage - what replaced what, and what Foundry actually contains. Seven minutes on the legacy estate. Twelve on Agent Framework. Five on a direct AutoGen versus Agent Framework comparison. Seventeen on Microsoft Foundry. Three on choosing, and five for your questions.

The right-hand column is the command behind each segment. All of them run offline on this laptop, and each result states its mode, so nothing simulated passes as a cloud call.

Show:
Run a finger along the coloured bar: the Foundry segment is the longest because that is where most of the new services live.

Next:
Section one: lineage.

<!-- slide: content_lineage.slide_section -->
### 4. Section 01 - Lineage - 3:00-3:20

Say:
Microsoft renamed and merged a lot in two years. If you copy a sample from 2024, you may be copying an API that no longer exists. So we read the lineage first: frameworks and SDKs, Azure services, the portal today, and what sits inside Foundry.

<!-- slide: content_lineage.slide_framework_lineage -->
### 5. Frameworks and SDKs lineage - 3:20-5:20

Say:
Read each row left to right: before, the relationship, after, and the status on the right. The legend at the bottom matters: solid arrows mean rename, successor, migration or merge. Dashed arrows mean a relationship, not a replacement.

Top row: AutoGen from Microsoft Research and Semantic Kernel both started in 2023. Agent Framework is their successor - preview in October 2025, generally available on 3 April 2026. AutoGen's last release was 30 September 2025, and Semantic Kernel is in maintenance: supported, but new features land in Agent Framework.

Then the migrations a developer actually hits:
- Bot Framework SDK to the Microsoft 365 Agents SDK; Bot Framework's support ended in December 2025.
- prompt flow to Agent Framework workflows plus azure-ai-evaluation; prompt flow retires on 20 April 2027.
- azure-ai-inference to the openai package; azure-ai-inference retired on 26 August 2026.
- AzureOpenAI() to the standard OpenAI() client pointed at a /openai/v1 base URL - no more api-version parameters.
- azure-ai-generative merged into azure-ai-projects 2.x, one project client.
- The Assistants API, with threads and runs, to the Responses API and Agents v2; the Assistants API was sunset on 26 August 2026.

For managers, one sentence: a successor carries the ideas forward, but a migration still changes your code, and two of these dates are already behind us.

If asked:
- Sources: Microsoft Learn "What is Microsoft Foundry" and "Migrate from the Foundry (classic) portal", both current as of September 2026.
- azure-ai-ml maps to azure-ai-projects only for hub-to-project migration, so it is deliberately not on this slide.

Next:
The same story on the Azure service side.

<!-- slide: content_lineage.slide_service_lineage -->
### 6. Azure services lineage - 5:20-7:20

Say:
Product names changed faster than Azure resource types.

- Azure AI Studio in 2023 became Azure AI Foundry in 2024 and Microsoft Foundry in November 2025.
- Azure Cognitive Services became Azure AI Services and is now called Foundry Tools. The Azure resource type underneath is still Microsoft.CognitiveServices/accounts - which is why old scripts still find your resources.
- A hub plus Azure OpenAI plus AI Services merged into one Foundry resource with projects. Hub projects stay reachable in Foundry classic.
- Azure Search from 2015 became Azure Cognitive Search in 2019 and Azure AI Search in 2023. Notice the dashed arrow to Foundry IQ: Foundry IQ is built on AI Search, it does not replace it.
- Content Moderator is deprecated and retires on 15 March 2027; its successor is Azure AI Content Safety. And Foundry guardrails use Content Safety classifiers - again a dashed relationship, not a replacement.
- Entra Agent ID extends Microsoft Entra ID with agent identities and blueprints.
- Last row: Foundry portal Workflows, a preview feature, retire on 1 December 2026; Microsoft points new development to Agent Framework workflows.

Show:
Point at the two dashed rows so the room sees the difference between "replaced by" and "built on".

If asked:
- Foundry IQ is partially GA: the API is generally available, the portal experience is still preview.

Next:
You do not have to take my word for the coexistence - the Azure portal shows it.

<!-- slide: content_lineage.slide_portal -->
### 7. The Azure portal today - 7:20-9:00

Say:
These are real screenshots from the Azure portal, taken on 14 September 2026.

Left: All services, AI plus Machine Learning. Callout 1, the portal already labels the search service "AI Search (Foundry IQ)". Callout 2 is Microsoft Foundry, 3 is Azure OpenAI, and 4 is Bot Services - old and new in one list.

Right: the Microsoft Foundry blade. Callout 1, "Use with Foundry" groups Foundry, AI Hubs, Azure OpenAI and AI Search. Callout 2, "More services" holds Content Safety, Language, Speech and the other Foundry Tools. Further down that menu, QnA maker, Language understanding and Content moderator carry "(classic)" labels.

The lesson: current and classic services coexist, so a resource you find is not proof of which generation you are using.

Show:
Use-case band: a junior engineer who must find an existing AI resource goes All services, Microsoft Foundry, All resources, and opens the project - the right management page, not a guess.

Next:
So what is inside that Foundry resource?

<!-- slide: content_lineage.slide_foundry_architecture -->
### 8. Inside Microsoft Foundry - 9:00-11:00

Say:
One resource, many projects. This follows Microsoft's architecture page.

The outer box is the Foundry resource - technically Microsoft.CognitiveServices/accounts of kind AIServices. It is the governance boundary. At that level live the model deployments, the security settings - networking, keys and role-based access - and the connections.

Inside it, projects. Project A and Project B each hold their own agents, files and evaluations. That is the development boundary: two teams share model deployments but not each other's agents.

Below, outside the box: Azure Storage, Key Vault and Azure AI Search. They are separate resources with their own governance, referenced through connections. Securing Foundry does not secure your storage account.

Above: the surfaces you work from - the Foundry portal at ai.azure.com, the SDKs azure-ai-projects plus openai, azd, VS Code and MCP.

Right: what you build there - prompt agents and hosted agents, models, tools and knowledge including the Toolbox, Foundry IQ and memory in preview, evaluations and tracing, and guardrails.

Show:
Use-case band: a platform engineer supporting an HR team creates the Foundry resource, creates an HR project, deploys a model and connects knowledge, and assigns the Foundry User role. Result: a governed workspace for the HR assistant.

If asked:
- The Foundry RBAC roles were recently renamed: Foundry User, Foundry Project Manager, Foundry Owner, formerly Azure AI User and so on. Role IDs did not change.

Next:
Now the code most of you already have in production: the legacy estate.

<!-- slide: content_legacy.slide_section -->
### 9. Section 02 - The legacy estate - 11:00-11:15

Say:
What you already built still works. Before choosing a migration path, understand what each legacy piece does: AutoGen's alternating agents, Semantic Kernel's plugins and filters, Bot Framework's channel adapter, and prompt flow's graph.

<!-- slide: content_legacy.slide_autogen -->
### 10. AutoGen - 11:15-13:00

Say:
AutoGen invented this pattern, and it still works. AutoGen coordinates conversational agents with a team, a stopping rule and saved state.

Show:
Follow the schema: a task goes to a RoundRobinGroupChat, which alternates turn 0, the writer agent, and turn 1, the reviewer agent. save_state writes the team state to disk.

Say:
The table names the concepts: AssistantAgent is instructions plus a model client plus tools; the round-robin team alternates turns; termination is the word APPROVE or a maximum turn count; save_state and load_state persist the conversation.

The last row is the important one. The framework owns turn-taking and team state. Your application owns acceptance and business actions - there is no built-in approval gate.

Use case: a bid team needs a reviewed draft. A writer drafts, a reviewer challenges, they alternate until APPROVE or the limit, and a human checks the result.

Demo (optional, 20 seconds):
uv run msai-demo autogen - point out that it reports local_contract: the replay client is scripted.

If asked:
- Installed version 0.7.5; last release 30 September 2025.
- AutoGen and Agent Framework install side by side in one environment, which is why the comparison later can run both.

Next:
The other parent of Agent Framework: Semantic Kernel.

<!-- slide: content_legacy.slide_semantic_kernel -->
### 11. Semantic Kernel - 13:00-14:45

Say:
Semantic Kernel is in maintenance, and it has a ceiling. A Kernel holds plugins and model connectors, with filters wrapped around invocations.

Show:
Compare the two small diagrams. Left, Semantic Kernel: request, Kernel, a kernel function and a chat connector, with filters around the invocation. Right, Agent Framework: request, Agent, a tool and a ChatClient, with middleware at the agent, tool and model boundaries.

Say:
The mapping table is the migration guide in five rows:
- Kernel becomes Agent, which owns tools, session and middleware.
- @kernel_function becomes @tool, with the schema inferred from the signature.
- Connector becomes ChatClient, one client contract across providers.
- Filter becomes Middleware: typed interception of agent runs, tool calls and model calls.
- Planner becomes Workflow: an explicit graph you can test.

Use case: a helpdesk developer needs ticket status. The user gives a ticket number, the kernel calls a lookup plugin, and the model words the answer.

The ceiling, for architects: semantic-kernel 1.44.1 pins azure-ai-projects below 2.5, while the current Foundry SDK is 2.6, so the two cannot share one lockfile. The details are in the appendix, slide 42.

Next:
From code-level legacy to channel-level legacy.

<!-- slide: content_legacy.slide_channel -->
### 12. Bot Framework to Microsoft 365 Agents SDK - 14:45-16:15

Say:
The adapter changes; your handler does not. Both SDKs carry a channel activity into an application handler.

Show:
Top row: channel activity, BotFrameworkAdapter, handle_activity. Bottom row: channel activity, AgentApplication, the same handle_activity.

Say:
The Azure Bot registration stays. What you assess when moving the adapter is authentication, state and channels. The package table is the concrete part: botbuilder packages become microsoft-agents packages - hosting core, activity, the aiohttp hosting and MSAL authentication.

Two use cases, one business answer. An employee asks an existing Bot Framework bot for ticket status: message, adapter, handler queries tickets, reply in the channel. A Teams user asks the Microsoft 365 agent: activity, AgentApplication routes it, the same handler, a reply in Teams.

If asked:
- Bot Framework SDK long-term support ended in December 2025.
- Commands: uv run msai-demo bot-framework and m365-agents; both run the same handler.

Next:
The last legacy piece is the one with a hard retirement date.

<!-- slide: content_legacy.slide_prompt_flow -->
### 13. prompt flow becomes a workflow - 16:15-18:00

Say:
prompt flow retires on 20 April 2027, and its runtime images are already no longer updated. prompt flow connected prompt and Python nodes in a YAML or visual graph. Its replacement is a code-defined Agent Framework workflow.

Show:
Walk the mapping table from Microsoft's migration guide:
- the flow becomes WorkflowBuilder;
- a node becomes an Executor with a @handler method;
- an LLM node becomes FoundryChatClient().as_agent();
- an if node becomes add_edge with a condition;
- parallel nodes become add_fan_out_edges;
- an evaluation flow becomes azure-ai-evaluation evaluators;
- tracing becomes OpenTelemetry.

Say:
One honest trade-off for managers: Agent Framework has no visual editor. Teams that authored flows by drawing them must plan for code.

Use case: a support analyst needs repeatable ticket classification - load ticket text, run prompt and Python steps, validate the category. Result: the same pipeline, now a typed workflow you can evaluate.

Next:
Which brings us to the framework everything migrates to.

<!-- slide: content_runtime.slide_section -->
### 14. Section 03 - Microsoft Agent Framework - 18:00-18:15

Say:
Agents become parts of a workflow. Agent Framework is a Python runtime for agents, typed workflows and the tools around them. Four stops: the agent and its class family, workflow and harness, MCP and A2A, and traces.

<!-- slide: content_runtime.slide_agent -->
### 15. The agent - 18:15-20:00

Say:
An agent is four things: a client, instructions, tools and a session.

Show:
The code excerpt: Agent with a client, a name, instructions, a pricing tool and an in-memory history provider. Then create_session, and two run calls on the same session, so the second question remembers the first.

Show:
The schema: a question goes to the Agent; the Agent calls the ChatClient for the model and the @tool functions for actions; AgentSession holds the history.

Say:
Your process owns the tool loop and the session; the client only calls the model. That matters for security and cost: the model never executes your tools, your code does.

Use case: a new employee needs a leave-policy answer. They ask the agent, the agent calls a policy-search tool, and it answers from the returned passages with a source reference.

Demo (optional, 30 seconds):
uv run msai-demo agent-framework - offline, the scripted client drives the real tool loop, no API key needed.

Next:
Why can the same agent talk to OpenAI, Foundry or Anthropic? Inheritance.

<!-- slide: content_runtime_extra.slide_client_family -->
### 16. Class families - 20:00-21:30

Say:
Every provider plugs into the same client family. This diagram was read from the installed packages.

Show:
Left: BaseChatClient at the top. RawOpenAIChatClient and RawAnthropicClient derive from it, and RawFoundryChatClient derives from the OpenAI one - Foundry speaks the same protocol. Each public client - OpenAIChatClient, FoundryChatClient, AnthropicClient - is its raw client plus three shared layers: function invocation, chat middleware and chat telemetry.

Middle: the agent family. BaseAgent, RawAgent, then Agent; RawFoundryAgent and FoundryAgent. Agent and FoundryAgent add agent middleware and agent telemetry.

Right, faint, for comparison: AutoGen's ChatAgent, BaseChatAgent, AssistantAgent, and Team, BaseGroupChat, RoundRobinGroupChat.

Say:
The practical consequence for a developer: switching provider is choosing another client of the same family. Your agent code does not change; you verify provider behaviour with the same tests.

Note for accuracy: this is simplified - the public classes use multiple inheritance. The exact method resolution order is in the appendix, slide 40.

Next:
An agent decides one step at a time. When the steps must be explicit, you build a workflow.

<!-- slide: content_runtime.slide_workflow -->
### 17. The workflow - 21:30-23:15

Say:
The graph checks eligibility, then waits for a human decision.

Show:
Follow it: draft, review, then a switch - eligible? The Case branch goes to approve, the Default branch goes to revise. Both branches request a named human decision before accept.

Show:
The code line: WorkflowBuilder with a start executor and checkpoint storage, add_edge from draft to review, and ctx.request_info, which pauses the workflow and saves the pending request in a checkpoint.

Say:
The recorded run shows outputs before approval: zero; checkpoints: four; restored: true. Nothing is accepted before the human answers, and the pause survives in storage.

Clarify the naming trap: Agent Framework workflows are code. The Foundry portal's Workflows feature is a different, preview product that retires on 1 December 2026.

Use case: a merchandiser needs reviewed product copy - draft, check required fields, pause for approval, publish after approval. A controlled update.

Next:
Some tasks are too long for one context window. That is the harness.

<!-- slide: content_runtime.slide_harness -->
### 18. The harness - 23:15-24:45

Say:
create_harness_agent() composes an Agent with planning, file memory, compaction and approval.

Show:
The table's SDK DEFAULT column: todo tracking on - the plan is state; plan and execute modes on; session file memory on - findings live outside the context; compaction bounds context growth per call; tool auto-approval applies standing rules; OpenTelemetry on; shared files and child agents opt-in.

Say:
Two honest notes. This demo disables compaction to keep a short lesson deterministic, and telemetry is opt-in in the demo. And a virtual file path is not a sandbox: the demo writes only into .msai_workspace and gates irreversible tools.

Use case: an analyst needs a multi-document briefing - create a todo list, read the documents, save findings to files, assemble the report. The draft is backed by persistent notes instead of a context window that forgets.

Next:
An agent is only as useful as its tools. MCP gives it tools you did not write.

<!-- slide: content_runtime_extra.slide_mcp -->
### 19. MCP - 24:45-26:30

Say:
MCP, the Model Context Protocol, is a protocol for discovering and calling tools supplied by a server.

Show:
The schema: your agent, an MCP client, the MCP server. tools/list discovers what the server offers, tools/call invokes one, and the tool result comes back.

Say:
The server exposes capabilities; your application still decides which tools the agent may use. That is the security boundary: an MCP server is third-party code with access to something real.

Show:
The screenshot: Foundry's tools catalog showed 1,626 tools on the day of the capture, most of them MCP servers - GitHub, databases, Microsoft 365 connectors.

Use case: a developer needs test ideas for a GitHub issue. Connect the GitHub MCP server, discover its tools, fetch the issue, draft test cases. Result: reviewable test cases - the agent drafts, a person decides.

If asked:
- Remote MCP servers receive prompt content; review what they are allowed to see and log the calls.

Next:
MCP calls a tool. A2A hands the whole task to another agent.

<!-- slide: content_runtime_extra.slide_a2a -->
### 20. A2A - 26:30-28:00

Say:
A2A, Agent-to-Agent, lets independent agents exchange a task, follow its state and return an artifact.

Show:
The schema: your agent, an A2A client, the remote agent. The client sends message/send and polls tasks/get. The remote agent owns the task's status and artifacts and returns them.

Say:
Discovery starts at /.well-known/agent-card.json, then you send the task, follow it from working to completed, and collect the artifact.

Show:
The comparison table: MCP's unit of work is a tool call, request and response, discovered with tools/list. A2A's unit of work is a task with a lifecycle, discovered through the agent card.

Use case: a support assistant needs specialist log analysis. Discover the diagnostics agent, send the task, follow its status, collect the report. The specialist team shares an answer without sharing its code.

Next:
With agents, tools and other agents in play, you need to see what happened.

<!-- slide: content_runtime.slide_observability -->
### 21. Observability - 28:00-30:00

Say:
A useful trace explains the whole decision. OpenTelemetry connects the agent, model and tool spans so a developer can follow one answer end to end.

Show:
The recorded span tree: invoke_agent PilotArchitect, a chat span on the scripted model, and execute_tool price_support_pilot. Three spans, recorded offline, not exported, no token usage because the offline client does not report it.

Show:
The controls table: ENABLE_INSTRUMENTATION is on in the SDK and the demo opts in; ENABLE_SENSITIVE_DATA is off because it adds prompts and tool arguments to traces; console exporters off; an OTLP endpoint sends to your collector; the Application Insights connection string enables Azure Monitor.

Say:
In this repository ordinary commands force instrumentation off; only --trace turns it on. Sensitive data stays off outside development.

Use case: a developer investigates a slow answer - find the trace, inspect the model and tool spans, spot the slow step. One component to fix, instead of a guess.

Demo (optional):
uv run msai-demo otel --trace local

Next:
Now the head-to-head we promised: the same task in AutoGen and in Agent Framework.

<!-- slide: content_compare.slide_section -->
### 22. Section 04 - The comparison - 30:00-30:15

Say:
One customer task, two implementations. Same brief and acceptance rules, framework- specific adapters: one approval gate, one restart, one replay.

<!-- slide: content_compare.slide_comparison -->
### 23. Same task, two frameworks - 30:15-32:45

Say:
The experiment. Held constant: a six-week support-pilot brief, a fictional 25,000 USD budget, the same source corpus, turn cap, pricing and acceptance checks. In live mode an OpenAI architect drafts and an Anthropic reviewer challenges; the recorded run on these slides is scripted and offline.

Three words for the juniors: an agent is a model, instructions, tools and a session; a workflow is explicit execution steps; a checkpoint is saved workflow state, including pending requests.

Show:
Left panel, AutoGen: the application owns the gate. It saves team state and its own pending-approval file, and a separate resume process reads both back, reloads the team and applies the approval.

Right panel, Agent Framework: the tool is declared approval_mode always_require, the group chat gets FileCheckpointStorage, and the resume process loads the pending request from the checkpoint and answers it with workflow.run(responses=...).

Say:
Disclosures, because this goes to a client: same brief and acceptance rules, but framework-specific adapters. The demo supplies a preselected decision; --decision reject exercises the rejection path. And accept_proposal is a simulated business action.

Use case: an architect and a risk reviewer prepare a client proposal - draft, review, a named human approves, accept. Nothing is accepted without the human.

Demo (optional, 60 seconds):
uv run msai-demo group-chat - point at the two lanes and the "batch ok" summary.

Next:
Both lanes pass. The difference is who owns the machinery.

<!-- slide: content_compare.slide_recovery_evidence -->
### 24. Restart evidence and ownership - 32:45-35:00

Say:
Both survive a restart; they differ in who owns what.

Show:
The event logs, read top to bottom. In each lane the gate is reached in the parent process, the approval is recorded and the action executes in a separate resume process with a different process ID, and a replay in a third process records the approval again but executes nothing. Actions after replay: zero in both lanes. The Agent Framework resume read five checkpoint files.

Show:
The responsibility table on the right. The pending approval record, durable state and the action gate are application code in AutoGen and framework features in Agent Framework. Restart routing, idempotency and the audit log are application code in both.

Say:
This is the fair version of the migration argument. AutoGen can do it - you write and maintain the approval record, the state files and the gate. Agent Framework's checkpoints include pending approvals and its tool API gates execution. Both still need your code to launch recovery, record decisions and enforce idempotency.

If asked:
- The process IDs are from the recorded run in deck/facts.json; a new run produces new IDs.
- Full transcripts are in the appendix, slide 38, and the persisted-approval diagram on slide 39.

Next:
Section five: the managed side, Microsoft Foundry.

<!-- slide: content_foundry.slide_section -->
### 25. Section 05 - Microsoft Foundry - 35:00-35:15

Say:
The cloud takes real responsibility. Models, agents and knowledge share a project, and each service has its own runtime and governance boundary. Six stops: models and clients, prompt and hosted agents, Foundry Local and Ollama, search and Foundry IQ, guardrails, identity and evaluation.

<!-- slide: content_foundry.slide_models -->
### 26. Models and project clients - 35:15-37:30

Say:
One catalog, one project endpoint, the openai package.

Show:
The model catalog screenshot: 804 models visible on the capture date.

Show:
The client schema: AIProjectClient manages the project - deployments and connections. get_openai_client() returns an OpenAI client pointed at the project's /openai/v1 endpoint, which calls the Responses API. FoundryChatClient is Agent Framework's adapter over the same endpoint. Every call carries an Entra token for the audience https://ai.azure.com/.default.

Say:
The SDK migration line is the practical part: azure-ai-inference retired on 26 August 2026 in favour of the openai package; AzureOpenAI() becomes OpenAI() with a base URL; azure-ai-projects 1.x becomes 2.x.

Show:
The legacy and current rows of the meeting-summarizer example. Legacy: transcript, ChatCompletionsClient.complete(), summary draft - SDK retired. Current: transcript, OpenAI with the project base URL, responses.create(), summary draft. The command uv run msai-demo azure-ai-inference is a local contract: it validates the legacy request shape and decodes a synthetic response; no SDK or model runs.

Use cases: an analyst picks a model for meeting summaries by running the same transcript through a shortlist and comparing omissions and latency; a developer authenticates to the project, lists deployments and chooses the one the app will call.

Next:
Once you have a model, who runs the agent: Foundry or your code?

<!-- slide: content_foundry.slide_agent_service -->
### 27. Prompt agents or hosted agents - 37:30-39:30

Say:
Foundry runs both. The question is who runs the code.

Show:
Left, the prompt agent: instructions plus a model plus tools, defined declaratively. Foundry's runtime hosts the model and tool loop, and your application calls a managed endpoint.

Right, the hosted agent: your framework and agent code - Agent Framework, LangGraph, Semantic Kernel or plain Python - packaged as a container. Foundry runs it and provides scaling, identity and observability; your application calls the same kind of managed endpoint.

Say:
Rule of thumb: start declarative; move to a hosted agent when you need custom logic or dependencies. In this repository the offline mode is a local contract that exercises requests and replies - live hosting needs a Foundry project and a role.

Use cases: an HR administrator builds policy Q&A by picking a model, writing instructions, attaching knowledge and testing - no runtime to operate. A Python team hosts its log analyzer by packaging the code, deploying the container and calling the endpoint - their logic, managed hosting.

If asked:
- Hosted agents and publishing agents to Microsoft 365 Copilot and Teams are generally available; memory is preview.

Next:
The opposite end of the spectrum: no cloud at all.

<!-- slide: content_foundry.slide_foundry_local -->
### 28. Foundry Local - 39:30-41:30

Say:
Foundry Local runs the model inside your app. It is an embedded native runtime for on-device inference, with SDKs for C#, JavaScript, Python and Rust.

Show:
Follow the schema: your app calls the language SDK, which calls the Foundry Local Core API - an in-process native library, not a separate service - which runs ONNX Runtime. ONNX Runtime selects the best execution provider automatically: NVIDIA CUDA, WebGPU, Qualcomm or AMD NPUs, Intel OpenVINO, or the CPU as a fallback. Models come from the Foundry Catalog on first use and are cached locally. An optional OpenAI-compatible REST endpoint lets tools like LangChain talk to it.

Say:
Precise wording on privacy: inference inputs and outputs stay on the device, and cached models work offline. Model and component downloads, and optional diagnostics, do use the network.

Two SDK traps from building this demo: the Python module was renamed from foundry_local to foundry_local_sdk at 2.x, and the agent-framework-foundry-local adapter still pins the old 0.5.1 SDK, so this repository calls the OpenAI-compatible endpoint instead.

Use case: a field technician needs notes summarised offline. The app downloads the model once, loads it in-process and summarises local text - an on-device draft, no cloud call.

Next:
The question you asked before the talk: is this an Ollama replacement?

<!-- slide: content_foundry.slide_local_comparison -->
### 29. Foundry Local or Ollama - 41:30-43:30

Say:
Overlap, not a drop-in swap. Both run local models; the app integration, model formats and runtime ownership differ.

Show:
Walk the rows:
- What it is: Foundry Local is a native library embedded in your app; Ollama is a local model server with a CLI.
- How you call it: Foundry Local through the in-process SDK, with an optional OpenAI endpoint; Ollama through its REST API on localhost port 11434, with /v1 OpenAI compatibility.
- Models: Foundry Local uses curated ONNX variants optimised per hardware, or ONNX models you compile; Ollama uses the ollama.com library, GGUF imports through a Modelfile, and optional cloud models.
- Hardware: Foundry Local picks the execution provider automatically; with Ollama the server handles it.
- Built for: Foundry Local for shipping on-device AI inside apps, single user; Ollama for local development and experimentation.
- Cloud account: neither requires one for local models.

Say:
The verdict: for local development they overlap. If you ship AI inside a Windows, macOS or Linux application, choose Foundry Local. If you want to tinker with community models behind a local server, choose Ollama. For high-throughput shared serving, prefer a serving stack such as vLLM.

If asked:
- This is an architecture recommendation, not a capability claim: Ollama does handle concurrent requests and network serving.

Next:
Back to the cloud, and to the job from slide 2: answers from your documents.

<!-- slide: content_foundry.slide_knowledge -->
### 30. AI Search and Foundry IQ - 43:30-45:30

Say:
AI Search is the engine; Foundry IQ is the knowledge layer built on it.

Show:
Top row: your query runs a hybrid query on Azure AI Search and gets ranked passages with sources. You design the index, the schema, the refresh and the ranking.

Bottom row: an agent request goes to a Foundry IQ knowledge base, which plans the retrieval, runs and merges subqueries, and returns grounded context with citations. You configure knowledge sources and retrieval settings. The dashed "built on" arrow points from Foundry IQ down to AI Search.

Say:
Permissions are the part architects must get right. With AI Search you use security filters, or native ACL and RBAC where the source supports it, some of it in preview. With Foundry IQ, supported sources sync their ACLs and results are trimmed at query time. Either way, configure permission trimming before content reaches the model.

Use cases: a support engineer indexes the manuals and runs a hybrid query to get ranked passages with sources. An employee asks an agent a cross-document policy question; the knowledge base returns cited context and a grounded answer.

If asked:
- Foundry IQ: API generally available, portal still preview.

Next:
Grounded answers are half of trust. The other half is stopping the wrong action.

<!-- slide: content_foundry.slide_guardrails -->
### 31. Content Safety and guardrails - 45:30-47:45

Say:
Classifying a prompt is not the same as intervening. Content Safety returns severity scores and your application applies the threshold. Guardrails use classifiers and configured actions at the input, tool and output boundaries.

Show:
The pipeline: user input, model or agent, tool call, tool response, output. Availability underneath: input and output are GA for models and preview for agents; tool call and tool response interception are preview. Agent guardrails apply to Foundry Agent Service agents.

Show:
The recorded local run: user input allowed; tool call blocked by "keep budget" and "require approval"; tool response annotated as untrusted; output annotated to disclose estimates.

Say:
Read the dark box out loud: this is a LOCAL CONTRACT. The signals are synthetic and the budget gate is application code. Two cases were evaluated and both were blocked at the tool call. Foundry's own enforcement needs a separate live validation - we are showing the mechanism, not proving the service.

Use cases: a community moderator submits text, reads the severity scores and applies a threshold - allow, block or review. An assistant owner attaches a guardrail that checks input, tool call and output and applies the configured action - the risky call never runs.

If asked:
- Content Moderator, the predecessor of Content Safety, retires on 15 March 2027.

Next:
Guardrails decide what an agent may do. Identity decides who the agent is.

<!-- slide: content_foundry.slide_identity -->
### 32. Identity - 47:45-50:00

Say:
A token proves who you are. It does not grant access. Microsoft Entra ID authenticates the app; roles on each resource authorise it. Entra Agent ID extends Entra ID with agent identities.

Show:
Top row, recorded live: an app identity gets an Entra token, the resource role decides, and the result is allowed or a 403. The recorded run acquired tokens for ai.azure.com, cognitiveservices.azure.com, search.azure.com and management.azure.com - and then listed zero subscriptions, because the principal has no role assignments. Token values are never printed.

Say:
That empty list is the lesson: authentication succeeded, authorisation gave it nothing.

Show:
Bottom, dashed row: agent blueprint, agent identity, scoped access, review or revoke. It is dashed because it models what a tenant administrator must create first. The workshop principal is an ordinary app registration, not an Agent ID; this repository did not provision one.

Use cases: a developer acquires a token, calls Search, and the role decides - allowed, or a clear 403. A tenant admin creates a blueprint and agent identity, grants scoped access, and can review or revoke it - agent access governed separately from people.

Next:
Last Foundry stop, and the one that makes every migration safe: evaluation.

<!-- slide: content_foundry.slide_evaluation -->
### 33. Evaluation - 50:00-52:00

Say:
Migration is only safe if the acceptance criteria survive.

Show:
The pipeline: cases in a JSONL file, azure-ai-evaluation's evaluate(), two evaluators - required_terms and source_sections - and rows plus metrics.

Show:
The results: costed-pilot passes, approval-gate passes, invented-source fails on purpose, because it cites a section that does not exist. evaluate() returned required_terms 1.00, source_sections 0.67, one failed case.

Say:
Two honest limits. These are code checks: no model and no project, recorded as local_execution. Model-graded evaluation is a separate, paid and non-deterministic run against a deployed model. And term and citation checks do not prove correctness - they prove the answer did not skip the required parts.

Why keep a failing case? An evaluation suite that only shows green is a dashboard, not a test.

Use case: a QA engineer prepares questions and expected sources, runs the evaluators, and inspects the failing cases - a regression report before release, with the failure kept visible.

Next:
We have seen the pieces. Two slides on how to choose.

<!-- slide: content_map.slide_architectures -->
### 34. Reference architecture - 52:00-53:45

Say:
Start on the laptop. Move the boundary when you must.

Show:
Row A is what ran in this room: msai-demo in your process, an Agent Framework agent or workflow, model clients that are scripted or remote, and checkpoints on disk. No Azure required.

Row B is an illustrative Azure target, not a deployed system: the Microsoft 365 Agents SDK as the channel, the same Agent Framework application as the runtime, models and knowledge from Foundry models and Search or Foundry IQ, and durable checkpoints.

Say:
Look at the identity path, because it is where designs usually go wrong. The runtime asks Microsoft Entra ID for a token and receives it; identity, RBAC and tracing span the runtime and the services instead of being one step at the end; guardrails sit at the model and agent interface.

Use case: an architect planning a policy assistant maps channel and runtime, then model and retrieval, then identity and telemetry - a design with explicit boundaries.

Next:
And the rule that keeps that design small.

<!-- slide: content_map.slide_decision -->
### 35. Choose the lowest abstraction - 53:45-55:00

Say:
Every step up buys capability and bills you in runtime behaviour you now have to own, test and observe.

Show:
The four steps:
1. A model call - one request, no tools, no state - when a single classification or rewrite is the whole job.
2. An Agent Framework agent - tools, a session, middleware - when the agent loop is the workflow.
3. An Agent Framework workflow - typed graph, conditional edges, checkpoints, approval - when you must pause, resume or replay.
4. Foundry Agent Service - versioned agents, private networking, server-side execution - when the platform, not your process, should own the agent.

Say:
And one rule on the harness: it sits beside step two, not above it. Right when the task outlives one context window; wrong when you can write the control flow down. If a plain function does the job, write the function.

Next:
Let me close with four things to take away.

<!-- slide: content_close.slide_close -->
### 36. Thank you and Q&A - 55:00-60:00

Say:
Thank you. If you remember one sentence: start with a job the user understands, then choose the smallest system that can deliver it.

Four takeaways:
1. Start from the job, not the brand. Name the user, the steps and the reviewable result.
2. New agent code goes on Agent Framework. Use the lineage slides to plan existing-system migrations.
3. Adopt identity, guardrails, traces and evaluation on day one.
4. Check the lineage before you trust a sample: confirm the package, the endpoint and the current API.

Everything you saw is in the repository: the deck, docs/research.md with every source, and three commands to reproduce it - uv sync --frozen --group legacy, then uv run msai-demo doctor, then uv run msai-demo group-chat.

Open the floor for questions. Useful appendix slides for answers: 38 transcripts, 39 persisted approval, 40 exact class order, 42 compatibility constraints, 43 platform choices, 44 cost and blast radius, 48 references.

<!-- slide: content_appendix.slide_section -->
### 37. Appendix divider - not presented

Use during Q&A or share afterwards. The appendix holds the lab material a Python developer needs to reproduce the talk: recorded transcripts and persisted approval, exact class order and compatibility constraints, the stack map, platform choices and operations, repository, readiness and automated checks, and the references.

<!-- slide: content_appendix.slide_transcripts -->
### 38. Both group-chat transcripts - reference

When asked "what did the agents actually say?": The AutoGen lane recorded two turns with text: the SolutionArchitect's JSON proposal and the RiskReviewer's "APPROVE". It stopped because the text APPROVE was mentioned; tool calling was not exercised by AutoGen's replay client. The Agent Framework lane recorded one turn with text - the architect's proposal - because the reviewer's contribution was the tool call that reached the approval gate; its stop reason is "resumed" and tool calling was exercised.

Be clear that both are scripted offline runs; the long proposal JSON is cut on the slide and complete in deck/facts.json. Reproduce with uv run msai-demo group-chat --format json.

<!-- slide: content_compare.slide_approval -->
### 39. Approval is a state transition - reference

When asked "where does the approval live while it waits?": Both lanes stop before the simulated business action and write the pending decision to disk. AutoGen: team.run() in the parent, pending-approval.json in a format you define, apply_approval() in a separate process. Agent Framework: workflow.run() in the parent, checkpoint JSON files holding pending_request_info_events in the SDK's format, run(responses=...) in a separate process.

The auditor's table: the pending approval is your file versus the SDK checkpoint; the action is stopped by application code versus the tool's approval_mode; both applications start the resume, and both use the same idempotency store so a replay is safe.

The point to land: if the pending decision lives only in process memory, a restart loses the approval. Both lanes avoid that here; only one had to invent the record to do it.

<!-- slide: content_runtime_extra.slide_mro -->
### 40. Exact method resolution order - reference

When a developer challenges the simplified class diagram on slide 16:
These chains are read from the installed packages at build time, left to right. For example FoundryChatClient resolves through FunctionInvocationLayer, ChatMiddlewareLayer, ChatTelemetryLayer, RawFoundryChatClient, RawOpenAIChatClient and BaseChatClient. Agent resolves through AgentMiddlewareLayer, AgentTelemetryLayer, RawAgent and BaseAgent. GroupChatBuilder.build() returns a Workflow. The repository's offline ScriptedChatClient has function invocation and middleware but no ChatTelemetryLayer.

<!-- slide: content_map.slide_stack_map -->
### 41. Stack map - reference

When someone asks for the one-picture summary: Five layers, five responsibilities, read downwards. Channel - the Microsoft 365 Agents SDK - decides who can talk to the agent. Runtime - Agent Framework - decides what the agent may do and what happens when a human must decide. Managed runtime - Foundry Agent Service - moves that runtime into a service with versions and networking. Models and knowledge - Foundry Models, AI Search, Foundry IQ - provide inference, retrieval and citations. The control plane - Entra, guardrails, observability, evaluation - is the only layer to adopt on day one, whatever else you choose.

<!-- slide: content_legacy.slide_cost_of_staying -->
### 42. Compatibility constraints - reference

When asked "can we keep the legacy packages next to the new ones?": Three constraints come with the legacy packages, each read from PyPI metadata and reproduced with uv lock. semantic-kernel 1.44.1 pins azure-ai-projects below 2.5 while the current SDK is 2.6.0. semantic-kernel's autogen extra pins autogen-agentchat below 0.4 while AutoGen is at 0.7.5. promptflow-tracing pins the OpenTelemetry SDK below 1.39 while Agent Framework needs 1.39 or later.

Two other facts: agent-framework-foundry-local pins foundry-local-sdk below 0.5.2 while the SDK is 2.0.1, so call the OpenAI-compatible local endpoint; and autogen-ext with openai coexists with Agent Framework, which is the good news - you do not have to migrate everything at once.

<!-- slide: content_map.slide_platform_decision -->
### 43. Platform decision - reference

When a manager asks "do we have to buy the whole stack?": No. Runtime, channel and cloud service are separate choices. Agent Framework needs only Python 3.10 or later. Foundry Agent Service needs a Foundry project and RBAC. The Microsoft 365 Agents SDK needs an Azure Bot registration. Azure AI Search needs a search service and an index; Foundry IQ needs AI Search plus configured knowledge sources. Foundry Models needs a Foundry project; Foundry Local needs only the local SDK and a cached model. The only mandatory row on day one is not on the table: instrument the thing, because traces and an evaluation set make every other choice reversible.

<!-- slide: content_close.slide_operations -->
### 44. Cost and blast radius - reference

When asked about cost or risk in production:
Both are decided at design time. Context is the bill: every turn resends the window, and a group chat broadcasts to every participant. Bound every loop with max_rounds, turn caps and tool-call limits. Blast radius equals tool permissions, not the good intentions of a system prompt - deny by default and gate the irreversible behind approval. Treat retrieved text, tool output and other agents' replies as untrusted. Measure per trace, not per month, using gen_ai.client.token.usage by tag, release and tenant.

<!-- slide: content_appendix.slide_repository -->
### 45. The repository - reference

When a developer asks how to reproduce everything:
One repository, one command-line tool, twenty-four technology demos, pinned with uv.lock, linted at 79 columns, strictly typed and tested without network access. Start with uv sync --frozen --group legacy, then uv run msai-demo list for the table of contents, doctor for versions and credential presence, group-chat for the comparison, and all --lane current for every current technology. Telemetry is off unless you ask for it. The supplementary code excerpts below come from the source at build time.

<!-- slide: content_appendix.slide_readiness -->
### 46. Readiness check - reference

Before the workshop, run uv run msai-demo doctor. It reports installed versions and which credentials are present - never a value - and which demos have a live path. It does not prove a credential is authorised; a live run does. On the recording machine one credential row said missing, and every demo still ran, reporting which path it took.

<!-- slide: content_appendix.slide_standard -->
### 47. Automated checks - reference

When asked about engineering quality:
Five commands must be green before anything is shown: ruff format check, ruff check, mypy in strict mode, pytest with coverage, and uv lock --check. The gates behind them: a 79-column limit with 30 Ruff rule families, strict typing with Any confined to SDK boundaries, and 100 percent statement and branch coverage enforced by fail_under in pyproject. Habits a reviewer can see: no credential is printed, telemetry is off by default, every claim carries a mode, tests never touch the network, one lockfile, and quoted figures come from recorded runs.

<!-- slide: content_appendix.slide_references -->
### 48. References - reference

Every title on this slide is a clickable link to official documentation: Agent Framework and its migration guides, Microsoft Foundry's overview, architecture, capability map, classic-portal migration and GA overview, Foundry Agent Service, guardrails, Foundry IQ, Foundry Local, Ollama's OpenAI compatibility page, the Bot Framework migration, Entra Agent ID, AI Search access control and rebrand history, the prompt flow migration, the Content Moderator retirement, and the PyPI JSON API. Run figures come from deck/facts.json and dated research facts from deck/research_facts.py.

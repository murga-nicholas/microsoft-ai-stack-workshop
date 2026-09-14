"""Dated documentation facts, separate from recorded workshop runs.

Reviewed for the client brief on 2026-09-14. Capture counts describe
the supplied screenshots only, never the size of a live catalog.
"""

# Source: https://ai.azure.com/ (supplied portal captures).
CAPTURE_DATE = "2026-09-14"
# Source: https://learn.microsoft.com/en-us/azure/foundry/what-is-foundry
RESEARCH_DATE = CAPTURE_DATE
# Source: https://ai.azure.com/ (foundry_agent_catalog.jpg).
AGENT_CATALOG_COUNT = 48
# Source: https://ai.azure.com/ (foundry_model_catalog.jpg).
MODEL_CATALOG_COUNT = 804
# Source: https://ai.azure.com/ (foundry_tools_catalog.jpg).
FOUNDRY_TOOLS_CAPTURE_COUNT = 1626

# Source: https://devblogs.microsoft.com/agent-framework/microsoft-agent-framework-version-1-0/
AGENT_FRAMEWORK_GA = "2026-04-03"
# Source: https://learn.microsoft.com/en-us/agent-framework/overview/
AGENT_FRAMEWORK_PREVIEW = "Oct 2025"
# Source: https://github.com/microsoft/autogen/releases
AUTOGEN_LAST_RELEASE = "2025-09-30"
# Source: https://github.com/microsoft/semantic-kernel
SEMANTIC_KERNEL_STATUS = "in maintenance"
# Source: https://learn.microsoft.com/en-us/microsoft-365/agents-sdk/
BOT_FRAMEWORK_LTS_ENDED = "Dec 2025"
# Source: https://learn.microsoft.com/en-us/azure/foundry-classic/how-to/prompt-flow-migration-overview
PROMPT_FLOW_RETIREMENT = "2027-04-20"
# Source: https://learn.microsoft.com/en-us/azure/foundry-classic/how-to/prompt-flow-migration-overview
PROMPT_FLOW_RUNTIME_STATUS = "Runtime images are no longer updated."
# Source: https://learn.microsoft.com/en-us/azure/foundry-classic/how-to/prompt-flow-migration-overview
PROMPT_FLOW_EDITOR_STATUS = (
    "No visual editor in Agent Framework: plan for code."
)
# Source: https://learn.microsoft.com/en-us/azure/foundry/how-to/navigate-from-classic
INFERENCE_RETIRED = "2026-08-26"
# Source: https://learn.microsoft.com/en-us/azure/foundry/how-to/navigate-from-classic
ASSISTANTS_SUNSET = "2026-08-26"
# Source: https://learn.microsoft.com/en-us/azure/foundry/concepts/general-availability
FOUNDRY_WORKFLOWS_RETIREMENT = "2026-12-01"
# Source: https://learn.microsoft.com/en-us/azure/foundry/what-is-foundry
FOUNDRY_RENAME = "Nov 2025"
# Source: https://learn.microsoft.com/en-us/azure/search/whats-new
AZURE_SEARCH_LAUNCH = "2015"
# Source: https://learn.microsoft.com/en-us/azure/search/whats-new
COGNITIVE_SEARCH_RENAME = "Oct 2019"
# Source: https://learn.microsoft.com/en-us/azure/search/whats-new
AI_SEARCH_RENAME = "Nov 2023"
# Source: https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/what-is-foundry-iq
FOUNDRY_IQ_PREVIEW = "Nov 2025"
# Source: https://learn.microsoft.com/en-us/azure/foundry/concepts/general-availability
FOUNDRY_IQ_STATUS = "API GA; portal preview"
# Source: https://learn.microsoft.com/en-us/azure/ai-services/content-moderator/overview
CONTENT_MODERATOR_DEPRECATED = "Feb 2024"
# Source: https://learn.microsoft.com/en-us/azure/ai-services/content-moderator/overview
CONTENT_MODERATOR_RETIRES = "2027-03-15"
# Source: https://learn.microsoft.com/en-us/azure/foundry/guardrails/guardrails-overview
GUARDRAILS_MODEL_AGENT_STATUS = "GA for models; preview for agents"
# Source: https://learn.microsoft.com/en-us/azure/foundry/guardrails/guardrails-overview
GUARDRAILS_TOOL_STATUS = "preview"
# Source: https://learn.microsoft.com/en-us/azure/foundry/concepts/architecture
FOUNDRY_ARCHITECTURE_UPDATED = "2026-08-21"

# Source: https://learn.microsoft.com/en-us/azure/foundry-local/concepts/foundry-local-architecture
FOUNDRY_LOCAL_ARCHITECTURE_URL = (
    "https://learn.microsoft.com/en-us/azure/foundry-local/"
    "concepts/foundry-local-architecture"
)
# Source: https://learn.microsoft.com/en-us/azure/foundry/agents/overview
FOUNDRY_AGENT_SERVICE_URL = (
    "https://learn.microsoft.com/en-us/azure/foundry/agents/overview"
)
# Source: https://docs.ollama.com/api/openai-compatibility
OLLAMA_COMPATIBILITY_URL = "https://docs.ollama.com/api/openai-compatibility"

# Source: https://www.microsoft.com/en-us/research/project/autogen/
# Source: https://devblogs.microsoft.com/semantic-kernel/hello-world/
FRAMEWORK_ORIGINS_YEAR = "2023"
# Source: https://azure.microsoft.com/en-us/blog/microsoft-azure-ai-data-and-application-innovations-help-turn-your-ai-ambitions-into-reality/
AI_STUDIO_YEAR = "2023"
# Source: https://azure.microsoft.com/en-us/blog/the-next-wave-of-azure-innovation-azure-ai-foundry-intelligent-data-and-more/
AI_FOUNDRY_YEAR = "2024"

# Source: https://learn.microsoft.com/en-us/azure/foundry/agents/overview
AGENT_SERVICE_DEFINITION = (
    "Foundry runs both. Prompt agents are instructions, a model "
    "and tools. Hosted agents package your own logic as a container."
)
# Source: https://learn.microsoft.com/en-us/azure/foundry-local/concepts/foundry-local-architecture
LOCAL_HARDWARE_NOTE = (
    "Core API is an in-process native library. ONNX Runtime "
    "automatically selects NVIDIA CUDA, WebGPU, Qualcomm / AMD NPU, "
    "Intel OpenVINO or CPU fallback."
)
# Source: https://learn.microsoft.com/en-us/azure/foundry-local/concepts/foundry-local-architecture
# Optional diagnostics wording follows the reviewed client brief.
LOCAL_NETWORK_NOTE = (
    "Inference inputs and outputs stay on the device. Cached "
    "models work offline; model and component downloads and optional "
    "diagnostics use the network."
)
# Source: https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/what-is-foundry-iq
FOUNDRY_IQ_DEFINITION = (
    "Foundry IQ is built on Azure AI Search. Search returns ranked "
    "passages; a knowledge base plans retrieval and returns "
    "grounded context."
)
# Sources: https://learn.microsoft.com/en-us/azure/foundry-local/concepts/foundry-local-architecture
# https://docs.ollama.com/api/openai-compatibility
# https://docs.ollama.com/import
# https://docs.ollama.com/faq
# https://github.com/microsoft/Foundry-Local
LOCAL_COMPARISON_ROWS = (
    (
        "What it is",
        "Native library embedded in your app",
        "Local model server + CLI",
    ),
    (
        "How you call it",
        "In-process SDK; optional OpenAI endpoint",
        "REST: http://localhost:11434; /v1 compatibility",
    ),
    (
        "Models",
        "Curated ONNX variants per hardware; compile your own",
        "ollama.com library; GGUF via Modelfile; optional cloud",
    ),
    (
        "Hardware",
        "Automatic CUDA, WebGPU, NPU, OpenVINO, CPU",
        "Handled by the server",
    ),
    (
        "Built for",
        "Shipping on-device AI inside apps; single user",
        "Local development and experimentation",
    ),
    ("Cloud account", "None required", "None required for local models"),
)

"""Microsoft Entra Agent ID: current identities for governed agents.

Agent ID reached GA in April 2026. This module validates a synthetic
blueprint, agent identity and token-exchange contract. The workshop's
ordinary application service principal is not an Agent ID.

Run it:

    uv run msai-demo entra-agent-id
    uv run msai-demo entra-agent-id --execution live
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from msai_demo import scenario
from msai_demo.contracts import (
    DemoResult,
    evidence,
    missing_configuration,
    result,
)

DEMO_NAME = "entra-agent-id"
TECHNOLOGY = "Microsoft Entra Agent ID"
FIXTURE_ID = "entra-agent-id-v1"
EXCHANGE_SCOPE = "api://AzureADTokenExchange/.default"
ASSERTION_TYPE = "urn:ietf:params:oauth:client-assertion-type:jwt-bearer"
ADMIN_PREREQUISITES = (
    "Create an agent identity blueprint and its tenant blueprint principal.",
    "Configure blueprint credentials, preferably federation or certificate.",
    "Assign business sponsors to the blueprint and each agent identity.",
    "Provision an agent identity linked to that blueprint.",
    "Grant the required resource permissions and administrator consent.",
    "Configure lifecycle governance, sign-in auditing and the Auth SDK.",
)


@dataclass(frozen=True)
class AgentIdentityContract:
    """Application-level references, never credentials or real tokens.

    Attributes:
        blueprint_id: Synthetic blueprint application identifier.
        principal_id: Synthetic tenant blueprint principal identifier.
        identity_id: Synthetic child agent client identifier.
        parent_id: Blueprint referenced by the child identity.
        identity_type: Directory object category of the child.
        sponsor_id: Business sponsor of the blueprint and agent.
        enabled: Whether lifecycle governance permits new tokens.
        exchange_scope: Scope of the initial blueprint token request.
        fmi_path: Child identity selected by the blueprint request.
        resource_scope: Resource scope requested in the second step.
    """

    blueprint_id: str
    principal_id: str
    identity_id: str
    parent_id: str
    identity_type: str
    sponsor_id: str
    enabled: bool
    exchange_scope: str
    fmi_path: str
    resource_scope: str


class AgentIdentityPort(Protocol):
    """Supply a synthetic directory contract for local validation."""

    async def read_contract(self) -> AgentIdentityContract:
        """Return identity references without acquiring credentials."""


class FixtureAgentIdentityPort:
    """Supply a blueprint and child identity that exist only locally."""

    async def read_contract(self) -> AgentIdentityContract:
        """Return the named fixture for the support-pilot agent."""
        return AgentIdentityContract(
            blueprint_id="fixture-support-blueprint",
            principal_id="fixture-blueprint-principal",
            identity_id="fixture-support-agent",
            parent_id="fixture-support-blueprint",
            identity_type="agentIdentity",
            sponsor_id="fixture-workshop-sponsor",
            enabled=True,
            exchange_scope=EXCHANGE_SCOPE,
            fmi_path="fixture-support-agent",
            resource_scope="https://ai.azure.com/.default",
        )


def validate_agent_contract(contract: AgentIdentityContract) -> list[str]:
    """Validate relationships before a token-exchange implementation.

    This checks application invariants only. Entra must still validate
    credentials, token signatures, grants and directory relationships.

    Args:
        contract: Synthetic blueprint, identity and request references.

    Returns:
        Every violated invariant; an empty list means locally valid.
    """
    checks = (
        (bool(contract.blueprint_id.strip()), "Blueprint ID is required."),
        (bool(contract.principal_id.strip()), "Blueprint principal required."),
        (bool(contract.identity_id.strip()), "Agent identity ID is required."),
        (
            contract.identity_type == "agentIdentity",
            "An ordinary application principal is not an Agent ID.",
        ),
        (
            contract.identity_id != contract.blueprint_id,
            "The blueprint and child must be distinct objects.",
        ),
        (
            contract.parent_id == contract.blueprint_id,
            "The identity must belong to the blueprint.",
        ),
        (bool(contract.sponsor_id.strip()), "A business sponsor is required."),
        (
            contract.enabled,
            "The agent is disabled; do not request new tokens.",
        ),
        (
            contract.exchange_scope == EXCHANGE_SCOPE,
            "The blueprint request must target AzureADTokenExchange.",
        ),
        (
            contract.fmi_path == contract.identity_id,
            "fmi_path must select the child agent identity.",
        ),
        (
            contract.resource_scope.startswith("https://")
            and contract.resource_scope.endswith("/.default"),
            "The resource must provide an HTTPS application scope.",
        ),
    )
    return [message for valid, message in checks if not valid]


def _contract_data(contract: AgentIdentityContract) -> dict[str, object]:
    """Describe directory ownership and the two request boundaries."""
    return {
        "scenario_id": scenario.SCENARIO_ID,
        "scenario": scenario.BRIEF,
        "cost": scenario.price_pilot(),
        "hierarchy": {
            "blueprint": contract.blueprint_id,
            "blueprint_principal": contract.principal_id,
            "agent_identity": contract.identity_id,
            "parent_blueprint": contract.parent_id,
            "resource": contract.resource_scope,
        },
        "token_exchange": {
            "endpoint": (
                "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"
            ),
            "blueprint_request": {
                "client_id": contract.blueprint_id,
                "grant_type": "client_credentials",
                "scope": contract.exchange_scope,
                "fmi_path": contract.fmi_path,
                "credential": "Reference to configured blueprint credential",
                "response_reference": "T1 (not acquired)",
            },
            "agent_request": {
                "client_id": contract.identity_id,
                "grant_type": "client_credentials",
                "scope": contract.resource_scope,
                "client_assertion_type": ASSERTION_TYPE,
                "client_assertion_reference": "T1 from blueprint request",
                "response_reference": "Resource access token (not acquired)",
            },
        },
        "governance": {
            "blueprint_and_agent_sponsor": contract.sponsor_id,
            "sponsor": "Business accountability and lifecycle decisions",
            "owner": "Technical administration of directory objects",
            "controls": [
                "Review access and remove grants when no longer needed.",
                "Disable the agent to prevent future token acquisition.",
                "Audit agent sign-ins and directory changes.",
            ],
            "revocation_limit": (
                "Disabling an identity does not prove every previously "
                "issued token has already stopped working."
            ),
        },
        "azure_identity_demo_contrast": (
            "azure_identity_demo uses EnvironmentCredential for an ordinary "
            "app registration. Its workshop service principal is NOT an "
            "Agent ID; those credentials do not provision this hierarchy."
        ),
        "admin_prerequisites": list(ADMIN_PREREQUISITES),
        "validation_scope": (
            "Local reference checks only; no Graph objects, SDK calls or "
            "token exchanges were performed."
        ),
        "sources": [
            "https://learn.microsoft.com/en-us/entra/agent-id/agent-blueprint",
            "https://learn.microsoft.com/en-us/entra/agent-id/"
            "autonomous-agent-authentication-authorization-flow",
            "https://learn.microsoft.com/en-us/entra/agent-id/"
            "agent-owners-sponsors-managers",
        ],
    }


async def run_entra_agent_id_demo(
    *,
    execution: str = "offline",
    port: AgentIdentityPort | None = None,
) -> DemoResult:
    """Validate the Agent ID hierarchy without impersonating an agent.

    Args:
        execution: ``offline`` or ``live``. Live needs tenant objects.
        port: Optional source of synthetic directory references.

    Returns:
        Contract validation and the explicit tenant prerequisites.

    Raises:
        ValueError: If execution is neither offline nor live.
    """
    if execution not in {"offline", "live"}:
        message = "execution must be 'offline' or 'live'."
        raise ValueError(message)
    if execution == "live":
        return missing_configuration(
            demo=DEMO_NAME,
            technology=TECHNOLOGY,
            lane="current",
            provider="microsoft-entra-agent-id",
            missing=["Agent ID blueprint, identity and resource grants"],
            next_steps=list(ADMIN_PREREQUISITES),
        )
    adapter = port if port is not None else FixtureAgentIdentityPort()
    try:
        contract = await adapter.read_contract()
    except PermissionError:
        return result(
            demo=DEMO_NAME,
            technology=TECHNOLOGY,
            lane="current",
            mode="local_contract",
            status="blocked",
            headline="Synthetic directory access was denied.",
            evidence=evidence(
                provider="microsoft-entra-agent-id", fixture_id=FIXTURE_ID
            ),
            error={
                "code": "authorization_denied",
                "message": "The injected directory fixture denied access.",
            },
        )
    failures = validate_agent_contract(contract)
    return result(
        demo=DEMO_NAME,
        technology=TECHNOLOGY,
        lane="current",
        mode="local_contract",
        status="blocked" if failures else "ok",
        headline=(
            "Local Agent ID relationships failed validation."
            if failures
            else "Blueprint and agent references pass local validation."
        ),
        evidence=evidence(
            provider="microsoft-entra-agent-id", fixture_id=FIXTURE_ID
        ),
        data={**_contract_data(contract), "validation_failures": failures},
        error=(
            {
                "code": "invalid_contract",
                "message": "Agent identity relationships are inconsistent.",
            }
            if failures
            else None
        ),
        next_steps=list(ADMIN_PREREQUISITES),
    )

"""Typed workflows in the current Microsoft Agent Framework runtime.

A proposal moves through draft, review, approve or revise, and accept.
The graph owns the approval pause and checkpoint recovery. Python owns
the arithmetic and policy, so generated prose cannot waive either.

Run it:

    uv run msai-demo workflow
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass, replace
from typing import TYPE_CHECKING, Protocol, TypeVar, cast

from msai_demo import scenario
from msai_demo.contracts import DemoResult, evidence, result

if TYPE_CHECKING:
    from agent_framework import (
        ChatOptions,
        InMemoryCheckpointStorage,
        SupportsChatGetResponse,
        Workflow,
        WorkflowContext,
    )

    from msai_demo.contracts import Status

DEMO_NAME = "workflow"
TECHNOLOGY = "Microsoft Agent Framework Workflows"
SOURCE = "agent-framework-overview"
REQUEST_ID = "support-pilot-approval"
_Handler = TypeVar("_Handler", bound=Callable[..., object])


@dataclass(frozen=True)
class Proposal:
    """Typed proposal carried between graph executors.

    Attributes:
        text: Draft prose, without model-generated arithmetic.
        cost: Deterministic costing from the shared scenario.
        cited_sources: Identifiers of grounding sections.
        revised: Whether the graph repaired scope or grounding.
        approved: Whether the named operator approved this version.
        decided_by: Name supplied with the human decision.
    """

    text: str
    cost: scenario.PilotCost
    cited_sources: list[str]
    revised: bool = False
    approved: bool = False
    decided_by: str = ""


@dataclass(frozen=True)
class HumanDecision:
    """Human input, kept separate from the generated proposal.

    Attributes:
        approved: The operator's explicit decision.
        decided_by: Name of the operator making that decision.
    """

    approved: bool
    decided_by: str


@dataclass(frozen=True)
class Acceptance:
    """Policy outcome emitted only by the terminal executor.

    Attributes:
        proposal: The exact version reviewed by the operator.
        accepted: Whether all shared acceptance rules passed.
        failures: Reasons the proposal could not be accepted.
    """

    proposal: Proposal
    accepted: bool
    failures: list[str]


class DraftPort(Protocol):
    """The local draft-generation seam; the graph owns all policy."""

    def check_available(self) -> None:
        """Check runtime dependencies before graph execution."""

    async def draft(self, brief: str) -> Proposal:
        """Return a typed draft for the supplied business brief."""


class ScriptedDraftPort:
    """Generate local draft prose through the real agent runtime.

    Args:
        client: Optional scripted client for deterministic exercises.
        cited_sources: Source identifiers to give the reviewer.
        team: Optional staffing to exercise the revision branch.
    """

    def __init__(
        self,
        client: SupportsChatGetResponse[ChatOptions] | None = None,
        *,
        cited_sources: tuple[str, ...] = (SOURCE,),
        team: dict[str, float] | None = None,
    ) -> None:
        """Keep dependencies lazy so importing needs no optional SDK."""
        self.client = client
        self.cited_sources = cited_sources
        self.team = team

    def check_available(self) -> None:
        """Load the optional runtime before claiming SDK execution."""
        from importlib import import_module

        import_module("agent_framework")

    async def draft(self, brief: str) -> Proposal:
        """Run one scripted agent turn and cost it with Python."""
        from agent_framework import Agent

        from msai_demo.providers import create_chat_client

        client = self.client
        if client is None:
            client = create_chat_client(
                "offline",
                replies=[
                    "Pilot scope: readiness, one agent and one tool, "
                    "retrieval, approval, telemetry and evaluation."
                ],
            )
        agent = Agent(
            client=client,
            name="WorkflowDrafter",
            instructions="Draft the pilot scope. Python computes its cost.",
        )
        response = await agent.run(brief)
        return Proposal(
            text=response.text,
            cost=scenario.price_pilot(team=self.team),
            cited_sources=list(self.cited_sources),
        )


class _MalformedDraftError(ValueError):
    """A draft response did not contain usable proposal text."""


def _context_annotation(
    context_type: object,
) -> Callable[[_Handler], _Handler]:
    """Resolve the context before SDK introspection of lazy imports.

    The SDK resolves deferred annotations against module globals.
    Binding this one annotation lets its decorators inspect locally
    imported WorkflowContext without importing the SDK at startup.
    """

    def decorate(function: _Handler) -> _Handler:
        function.__annotations__["ctx"] = context_type
        return function

    return decorate


def _content_is_ready(proposal: Proposal) -> bool:
    """Check content eligibility before requesting human approval."""
    # This predicate asks whether approval is the remaining requirement;
    # it records no approval. The accept executor checks the real vote.
    acceptable, _ = scenario.proposal_is_acceptable(
        cost=proposal.cost,
        approved=True,
        cited_sources=proposal.cited_sources,
    )
    return acceptable


def build_workflow(
    port: DraftPort,
    storage: InMemoryCheckpointStorage,
) -> Workflow:
    """Build the typed graph, including its resumable approval gates.

    Args:
        port: Local draft generation, isolated from policy decisions.
        storage: Checkpoint store shared with the resumed workflow.

    Returns:
        A real Agent Framework workflow with five named executors.
    """
    from agent_framework import (
        Case,
        Default,
        Executor,
        WorkflowBuilder,
        WorkflowContext,
        handler,
        response_handler,
    )

    class _Draft(Executor):
        @handler
        @_context_annotation(WorkflowContext[Proposal])
        async def draft(
            self, brief: str, ctx: WorkflowContext[Proposal]
        ) -> None:
            """Generate the draft without accepting any work."""
            proposal = await port.draft(brief)
            if not proposal.text.strip():
                message = "The draft response contained no proposal text."
                raise _MalformedDraftError(message)
            # A draft provider cannot supply its own approval.
            await ctx.send_message(
                replace(proposal, approved=False, decided_by="")
            )

    class _Review(Executor):
        @handler
        @_context_annotation(WorkflowContext[Proposal])
        async def review(
            self, proposal: Proposal, ctx: WorkflowContext[Proposal]
        ) -> None:
            """Send the proposal through the shared policy predicate."""
            await ctx.send_message(proposal)

    class _ApprovalGate(Executor):
        @handler
        @_context_annotation(WorkflowContext[Proposal])
        async def request_approval(
            self, proposal: Proposal, ctx: WorkflowContext[Proposal]
        ) -> None:
            """Request a human vote on the final proposal version."""
            if self.id == "revise":
                proposal = replace(
                    proposal,
                    text=(
                        "Revised scope: use the shared six-week pilot plan "
                        "and its default staffing. "
                        "Grounding: agent-framework-overview."
                    ),
                    cost=scenario.price_pilot(),
                    cited_sources=[SOURCE],
                    revised=True,
                )
            await ctx.request_info(
                proposal, HumanDecision, request_id=REQUEST_ID
            )

        @response_handler(
            request=Proposal, response=HumanDecision, output=Proposal
        )
        @_context_annotation(WorkflowContext[Proposal])
        async def record_decision(
            self,
            original_request: Proposal,
            decision: HumanDecision,
            ctx: WorkflowContext[Proposal],
        ) -> None:
            """Resume the checkpointed request that was answered."""
            await ctx.send_message(
                replace(
                    original_request,
                    approved=decision.approved,
                    decided_by=decision.decided_by.strip(),
                )
            )

    class _Accept(Executor):
        @handler
        @_context_annotation(WorkflowContext[Proposal, Acceptance])
        async def accept(
            self,
            proposal: Proposal,
            ctx: WorkflowContext[Proposal, Acceptance],
        ) -> None:
            """Apply every acceptance rule to the actual human vote."""
            acceptable, failures = scenario.proposal_is_acceptable(
                cost=proposal.cost,
                approved=proposal.approved and bool(proposal.decided_by),
                cited_sources=proposal.cited_sources,
            )
            # This is a local acceptance record, never a billing action.
            await ctx.yield_output(Acceptance(proposal, acceptable, failures))

    draft = _Draft(id="draft")
    review = _Review(id="review")
    approve = _ApprovalGate(id="approve")
    revise = _ApprovalGate(id="revise")
    accept = _Accept(id="accept")
    return (
        WorkflowBuilder(
            name="support-pilot-workflow-v1",
            start_executor=draft,
            checkpoint_storage=storage,
            max_iterations=8,
        )
        .add_edge(draft, review)
        .add_switch_case_edge_group(
            review,
            [
                Case(condition=_content_is_ready, target=approve),
                Default(revise),
            ],
        )
        .add_edge(approve, accept)
        .add_edge(revise, accept)
        .build()
    )


async def _execute_workflow(
    port: DraftPort,
    *,
    approve: bool | None,
    decided_by: str,
) -> DemoResult:
    """Run to the human gate, then rebuild and resume its checkpoint."""
    from agent_framework import InMemoryCheckpointStorage, WorkflowViz

    # Memory is disposable for the classroom. group_chat_demo.py uses
    # FileCheckpointStorage to survive a real process restart.
    storage = InMemoryCheckpointStorage()
    workflow = build_workflow(port, storage)
    first_run = await workflow.run(scenario.BRIEF)
    (request,) = first_run.get_request_info_events()
    proposal = cast("Proposal", request.data)
    checkpoints = await storage.list_checkpoints(workflow_name=workflow.name)
    latest = max(
        checkpoints, key=lambda checkpoint: checkpoint.iteration_count
    )
    # Mermaid export uses only stdlib; SVG/PNG export needs graphviz.
    data: dict[str, object] = {
        "graph": WorkflowViz(workflow).to_mermaid(),
        "graph_format": "mermaid",
        "proposal": asdict(proposal),
        "paused_for_approval": True,
        "outputs_before_approval": len(first_run.get_outputs()),
        "request_id": request.request_id,
        "checkpoint_id": latest.checkpoint_id,
        "checkpoint_count": len(checkpoints),
        "storage": "InMemoryCheckpointStorage",
        "restored": False,
        "accepted": False,
        "decision_source": "classroom operator decision replay",
        "usage": None,
    }
    status: Status = "paused"
    headline = "The typed workflow paused before accepting any work."
    if approve is not None:
        # A fresh graph proves that pending request state comes from the
        # checkpoint, rather than a variable retained by an executor.
        resumed_workflow = build_workflow(port, storage)
        resumed = await resumed_workflow.run(
            responses={REQUEST_ID: HumanDecision(approve, decided_by)},
            checkpoint_id=latest.checkpoint_id,
            checkpoint_storage=storage,
        )
        (output,) = resumed.get_outputs()
        acceptance = cast("Acceptance", output)
        data.update(asdict(acceptance))
        data["restored"] = True
        data["outputs_after_resume"] = len(resumed.get_outputs())
        status = "ok" if acceptance.accepted else "blocked"
        headline = (
            "The typed workflow resumed and accepted the approved pilot."
            if acceptance.accepted
            else "The typed workflow resumed and refused acceptance."
        )
    return result(
        demo=DEMO_NAME,
        technology=TECHNOLOGY,
        lane="current",
        mode="local_execution",
        status=status,
        headline=headline,
        evidence=evidence(provider="offline", sdk_invoked=True),
        data=data,
    )


async def run_workflow_demo(
    *,
    execution: str = "offline",
    port: DraftPort | None = None,
    approve: bool | None = True,
    decided_by: str = "workshop-operator",
) -> DemoResult:
    """Execute the local graph with an explicit classroom decision.

    Args:
        execution: CLI compatibility; both values run this local graph.
        port: Optional local draft adapter, independent of graph policy.
        approve: Decision to replay, or None to leave the graph paused.
        decided_by: Operator name required for acceptance.

    Returns:
        An honest local-execution result, including the Mermaid graph.

    Raises:
        ValueError: If execution is neither offline nor live.
    """
    if execution not in {"offline", "live"}:
        message = "execution must be 'offline' or 'live'."
        raise ValueError(message)
    adapter = port if port is not None else ScriptedDraftPort()
    try:
        adapter.check_available()
    except ImportError:
        return result(
            demo=DEMO_NAME,
            technology=TECHNOLOGY,
            lane="current",
            mode="local_contract",
            status="blocked",
            headline="The SDK is unavailable; only local costing ran.",
            evidence=evidence(
                provider="offline",
                fixture_id="workflow-missing-sdk-v1",
            ),
            data={
                "cost": scenario.price_pilot(),
                "graph": None,
                "paused_for_approval": False,
                "restored": False,
                "accepted": False,
            },
            error={
                "code": "missing_sdk",
                "message": "Install agent-framework-core to run the graph.",
            },
            next_steps=["Run uv sync to install the workshop dependencies."],
        )
    try:
        return await _execute_workflow(
            adapter,
            approve=approve,
            decided_by=decided_by,
        )
    except _MalformedDraftError:
        return _failure(
            "malformed_response", "The draft contained no proposal text."
        )
    except PermissionError:
        return _failure(
            "authorization_denied",
            "The local draft adapter denied access.",
        )
    except TimeoutError:
        return _failure("timeout", "The local draft adapter timed out.")


def _failure(code: str, message: str) -> DemoResult:
    """Report known failures without inventing execution or success."""
    return result(
        demo=DEMO_NAME,
        technology=TECHNOLOGY,
        lane="current",
        mode="local_execution",
        status="blocked" if code == "authorization_denied" else "error",
        headline=message,
        evidence=evidence(provider="offline", sdk_invoked=True),
        error={"code": code, "message": message},
        next_steps=[message],
    )

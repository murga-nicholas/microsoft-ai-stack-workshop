"""The result envelope every demo returns.

One shape for thirty-two demos. That is what lets the CLI, the tests
and the slides all read the same output, and it is what stops a green
console from being mistaken for a working Azure integration.

Two fields carry that weight:

``mode``
    *How* the result was produced. Did real SDK code run? Did a packet
    leave the machine? Did a cloud service actually execute?

``status``
    *What happened*. A real HTTP 403 is a successful demonstration of
    an authorisation boundary: ``mode="live_service"`` with
    ``status="blocked"``. It is not an error in the demo.

Keeping the two apart is the difference between an honest workshop and
a slide deck of green ticks.
"""

from __future__ import annotations

from typing import Any, Literal, NotRequired, TypedDict

SCHEMA_VERSION: int = 1

Mode = Literal[
    # Real local computation or protocol execution. Nothing simulated.
    "local_execution",
    # Real application and SDK code, with a clearly synthetic external
    # response. Proves the request, decoding and policy, nothing more.
    "local_contract",
    # A model was actually invoked, locally or remotely.
    "live_model",
    # A token was actually acquired from Microsoft Entra.
    "live_identity",
    # A non-model service was actually called.
    "live_service",
    # Preconditions stopped the demo before it ran.
    "not_run",
    # A container of child results; each child carries its own mode.
    "batch",
]

Status = Literal["ok", "paused", "blocked", "error"]

LIVE_MODES: frozenset[str] = frozenset(
    {"live_model", "live_identity", "live_service"}
)


class Evidence(TypedDict):
    """What actually happened, recorded rather than asserted.

    Attributes:
        sdk_invoked: Real vendor SDK code executed in this process.
        network_attempted: A request was sent off this machine.
        service_executed: A remote service ran the work and answered.
        provider: Provider or service the demo targeted.
        fixture_id: Identifier of the synthetic payload, when one was
            used. ``None`` whenever nothing was simulated.
        requested_model: Model the demo asked for, if any.
        observed_model: Model the response reported, if any.
    """

    sdk_invoked: bool
    network_attempted: bool
    service_executed: bool
    provider: str
    fixture_id: str | None
    requested_model: str | None
    observed_model: str | None


class DemoError(TypedDict):
    """A structured failure, never a bare string.

    Attributes:
        code: Stable machine-readable code, such as
            ``authorization_denied`` or ``missing_configuration``.
        message: One sentence a human can act on. Never a secret.
    """

    code: str
    message: str


class DemoResult(TypedDict):
    """The envelope every ``run_*_demo`` function returns.

    Attributes:
        schema_version: Bumped when this shape changes.
        demo: CLI name of the demo, such as ``group-chat``.
        technology: Product or package the demo teaches.
        lane: ``legacy``, ``current`` or ``shared``.
        mode: How the result was produced. See :data:`Mode`.
        status: What happened. See :data:`Status`.
        headline: One sentence for the console and the slide.
        evidence: What actually ran.
        data: Technology-specific payload, or ``None``.
        error: Structured failure, or ``None``.
        next_steps: Concrete prerequisites still missing.
        children: Child results when ``mode`` is ``batch``.
    """

    schema_version: int
    demo: str
    technology: str
    lane: Literal["legacy", "current", "shared"]
    mode: Mode
    status: Status
    headline: str
    evidence: Evidence
    data: dict[str, Any] | None
    error: DemoError | None
    next_steps: list[str]
    children: NotRequired[list[DemoResult]]


def evidence(
    *,
    provider: str,
    sdk_invoked: bool = False,
    network_attempted: bool = False,
    service_executed: bool = False,
    fixture_id: str | None = None,
    requested_model: str | None = None,
    observed_model: str | None = None,
) -> Evidence:
    """Build an :class:`Evidence` record with honest defaults.

    Everything defaults to "did not happen", so a demo has to opt in
    to every claim it makes.
    """
    return {
        "sdk_invoked": sdk_invoked,
        "network_attempted": network_attempted,
        "service_executed": service_executed,
        "provider": provider,
        "fixture_id": fixture_id,
        "requested_model": requested_model,
        "observed_model": observed_model,
    }


def result(
    *,
    demo: str,
    technology: str,
    lane: Literal["legacy", "current", "shared"],
    mode: Mode,
    status: Status,
    headline: str,
    evidence: Evidence,
    data: dict[str, Any] | None = None,
    error: DemoError | None = None,
    next_steps: list[str] | None = None,
) -> DemoResult:
    """Build a :class:`DemoResult`.

    Raises:
        ValueError: If a live mode claims no network was attempted, or
            a non-live mode claims a service executed. Those two
            combinations are the ones that would quietly mislead a
            room, so they fail loudly instead.
    """
    _check_consistency(mode, evidence)
    return {
        "schema_version": SCHEMA_VERSION,
        "demo": demo,
        "technology": technology,
        "lane": lane,
        "mode": mode,
        "status": status,
        "headline": headline,
        "evidence": evidence,
        "data": data,
        "error": error,
        "next_steps": next_steps or [],
    }


def batch(
    *,
    demo: str,
    headline: str,
    children: list[DemoResult],
) -> DemoResult:
    """Wrap several results, keeping each child's own mode intact."""
    failed = [
        child for child in children if child["status"] in {"blocked", "error"}
    ]
    envelope = result(
        demo=demo,
        technology="msai-demo",
        lane="shared",
        mode="batch",
        status="error" if failed else "ok",
        headline=headline,
        evidence=evidence(provider="none"),
        data={
            "total": len(children),
            "failed": [child["demo"] for child in failed],
        },
    )
    envelope["children"] = children
    return envelope


def missing_configuration(
    *,
    demo: str,
    technology: str,
    lane: Literal["legacy", "current", "shared"],
    provider: str,
    missing: list[str],
    next_steps: list[str],
) -> DemoResult:
    """Report that a live path could not start, and say exactly why."""
    names = ", ".join(missing)
    return result(
        demo=demo,
        technology=technology,
        lane=lane,
        mode="not_run",
        status="blocked",
        headline=f"{technology} needs {names}.",
        evidence=evidence(provider=provider),
        error={
            "code": "missing_configuration",
            "message": f"Set {names} to run the live path.",
        },
        next_steps=next_steps,
    )


def _check_consistency(mode: Mode, record: Evidence) -> None:
    """Reject evidence that would overstate what happened."""
    if mode in LIVE_MODES and not record["network_attempted"]:
        message = (
            f"mode={mode!r} claims a live call but evidence says no "
            f"network was attempted."
        )
        raise ValueError(message)
    if mode not in LIVE_MODES and record["service_executed"]:
        message = (
            f"mode={mode!r} is not a live mode, so evidence cannot "
            f"claim a service executed."
        )
        raise ValueError(message)
    if mode == "local_contract" and record["fixture_id"] is None:
        message = (
            "mode='local_contract' means a synthetic response was "
            "used, so evidence must name its fixture_id."
        )
        raise ValueError(message)

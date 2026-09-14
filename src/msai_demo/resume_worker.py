"""Resume either group-chat lane across a real process boundary.

Current and legacy lanes share only the process transport, recorded
evidence and business checks. Each rebuilds its own SDK objects.

Run it:

    uv run msai-demo group-chat --format json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from contextlib import redirect_stdout
from pathlib import Path
from typing import TYPE_CHECKING, Protocol, TypedDict, cast

from pydantic import BaseModel, ConfigDict, ValidationError

from msai_demo import scenario

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Mapping, Sequence
    from types import ModuleType

    from msai_demo.contracts import DemoError, Status


class ResumeResult(TypedDict):
    """Evidence returned by one independent resume process."""

    pid: int
    files_read: list[str]
    checkpoint_id: str
    actions: list[dict[str, object]]
    restored: bool


class ResumePort(Protocol):
    """The transport seam for starting one resume process."""

    async def resume(
        self, directory: Path, approve: bool, *, execution: str
    ) -> ResumeResult:
        """Resume from disk with the explicit execution mode."""


class ResumeError(RuntimeError):
    """A safe, structured failure without child stderr or endpoints."""

    def __init__(self, code: str) -> None:
        """Keep a stable error code and a credential-free message."""
        self.code = code
        super().__init__(
            "The resume worker could not complete; inspect the run directory."
        )


def model_failure(
    error: Exception,
    *,
    sdk_loader: Callable[[str], ModuleType] | None = None,
) -> tuple[Status, DemoError] | None:
    """Classify known vendor failures without exposing error text.

    Frameworks may wrap the vendor error in their own exception, so
    follow its cause chain. An unknown failure returns ``None`` and
    must be re-raised by the caller, never converted into success.

    Args:
        error: Failure raised by a parent-process model call.
        sdk_loader: Optional import seam for missing-package tests.

    Returns:
        A status and safe structured error, or ``None`` when unknown.
    """
    from importlib import import_module

    loader = sdk_loader or import_module
    definitions: tuple[tuple[str, Status, str, str], ...] = (
        (
            "AuthenticationError",
            "error",
            "authentication_failed",
            "The model provider rejected authentication.",
        ),
        (
            "PermissionDeniedError",
            "blocked",
            "authorization_denied",
            "The model provider denied this operation.",
        ),
        (
            "RateLimitError",
            "error",
            "rate_limited",
            "The model provider throttled the request; retry later.",
        ),
        (
            "APITimeoutError",
            "error",
            "timeout",
            "The model provider did not respond before the timeout.",
        ),
    )
    known: list[tuple[type[BaseException], Status, DemoError]] = []
    for package in ("openai", "anthropic"):
        try:
            sdk = loader(package)
        except ImportError:
            # Missing optional SDKs must not replace the original error.
            continue
        for name, status, code, message in definitions:
            exception_type = cast("type[BaseException]", getattr(sdk, name))
            known.append(
                (exception_type, status, {"code": code, "message": message})
            )
    cause: BaseException | None = error
    visited: set[int] = set()
    while cause is not None and id(cause) not in visited:
        visited.add(id(cause))
        for exception_type, status, details in known:
            if isinstance(cause, exception_type):
                return status, details
        cause = cause.__cause__ or cause.__context__
    return None


class ChildProcess(Protocol):
    """The minimal subprocess surface used by the transport."""

    @property
    def returncode(self) -> int | None:
        """Return the OS exit code after communication completes."""

    async def communicate(self) -> tuple[bytes, bytes]:
        """Wait for exit and read the single stdout response."""


class SpawnPort(Protocol):
    """Inject only process creation when testing transport failures."""

    async def __call__(
        self, *arguments: str, stdout: int, stderr: int
    ) -> ChildProcess:
        """Start a process without invoking a command shell."""


class _ResumeDocument(BaseModel):
    """Validate an untrusted child JSON response at the boundary."""

    model_config = ConfigDict(extra="forbid", strict=True)
    pid: int
    files_read: list[str]
    checkpoint_id: str
    actions: list[dict[str, object]]
    restored: bool


class SubprocessResumePort:
    """Start a fresh Python interpreter for every resume attempt."""

    def __init__(self, *, spawn: SpawnPort | None = None) -> None:
        """Accept a narrow process factory for failure-path tests."""
        self._spawn = spawn or _spawn_process

    async def resume(
        self, directory: Path, approve: bool, *, execution: str
    ) -> ResumeResult:
        """Pass only a disk location, human decision and explicit mode.

        Child stderr goes directly to the OS null device. It can never
        become part of a result envelope, including on process failure.
        """
        try:
            process = await self._spawn(
                sys.executable,
                "-m",
                "msai_demo.resume_worker",
                str(directory.resolve()),
                "approve" if approve else "reject",
                "--execution",
                execution,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
            stdout, _stderr = await process.communicate()
        except OSError as exc:
            code = "resume_worker_start_failed"
            raise ResumeError(code) from exc
        if process.returncode != 0:
            code = "resume_worker_failed"
            raise ResumeError(code)
        try:
            decoded = _ResumeDocument.model_validate_json(stdout)
        except ValidationError as exc:
            code = "resume_worker_invalid_output"
            raise ResumeError(code) from exc
        return cast("ResumeResult", decoded.model_dump())


async def _spawn_process(
    *arguments: str, stdout: int, stderr: int
) -> ChildProcess:
    """Use Python's real subprocess API without a shell."""
    return await asyncio.create_subprocess_exec(
        *arguments, stdout=stdout, stderr=stderr
    )


def write_json(path: Path, value: Mapping[str, object]) -> None:
    """Persist a JSON object under a run directory."""
    path.write_text(json.dumps(value, indent=2), encoding="utf-8")


def read_json(path: Path, files_read: list[str]) -> dict[str, object]:
    """Read and record an actual disk access, rejecting non-objects."""
    decoded: object = json.loads(path.read_text(encoding="utf-8"))
    files_read.append(str(path.resolve()))
    if not isinstance(decoded, dict):
        message = "The persisted state must be a JSON object."
        raise TypeError(message)
    return cast("dict[str, object]", decoded)


async def run_worker(
    directory: Path,
    approve: bool,
    execution: str,
    *,
    dispatch: Callable[[Path, bool, str], Awaitable[ResumeResult]]
    | None = None,
) -> ResumeResult:
    """Route one independent process using only persisted configuration.

    Args:
        directory: Run directory created by phase one.
        approve: Human decision supplied to the new process.
        execution: Explicit offline or live selection.
        dispatch: Optional lane seam for isolated routing tests.

    Returns:
        Measured evidence from the rebuilt lane.
    """
    if execution not in {"offline", "live"}:
        code = "invalid_execution"
        raise ResumeError(code)
    reads: list[str] = []
    configuration = read_json(directory / "run.json", reads)
    if configuration.get("execution", execution) != execution:
        code = "execution_mismatch"
        raise ResumeError(code)
    implementation = configuration.get("implementation")
    if implementation not in {"agent-framework", "autogen"}:
        code = "unknown_implementation"
        raise ResumeError(code)
    if dispatch is None:
        dispatch = _lane_handler(str(implementation))
    resumed = await dispatch(directory, approve, execution)
    resumed["files_read"] = list(dict.fromkeys(reads + resumed["files_read"]))
    return resumed


def _lane_handler(
    implementation: str,
) -> Callable[[Path, bool, str], Awaitable[ResumeResult]]:
    """Load only the SDK lane selected by the saved configuration."""
    if implementation == "agent-framework":
        from msai_demo.group_chat_demo import resume_agent_framework

        return resume_agent_framework
    from msai_demo.autogen_demo import resume_autogen

    return resume_autogen


def recovery_summary(
    directory: Path,
    parent_pid: int,
    first: ResumeResult | None,
    second: ResumeResult | None,
) -> dict[str, object]:
    """Summarize process and disk evidence from both resumes."""
    return {
        "run_directory": str(directory.resolve()),
        "parent_pid": parent_pid,
        "resume_pid": first["pid"] if first else None,
        "second_resume_pid": second["pid"] if second else None,
        "files_read": first["files_read"] if first else [],
        "second_resume_files_read": second["files_read"] if second else [],
        "checkpoint_id": first["checkpoint_id"] if first else None,
        "restored": bool(first and first["restored"]),
        "state_read_from_disk": _disk_recovery(first),
        "action_count": len(scenario.EventStore(directory).actions()),
        "second_resume_action_count": len(second["actions"]) if second else 0,
    }


def execution_checks(
    proposal: Mapping[str, object],
    events: list[dict[str, object]],
    parent_pid: int,
    first: ResumeResult | None,
    second: ResumeResult | None,
    *,
    approve: bool,
) -> dict[str, bool]:
    """Compute acceptance from the proposal, events and OS PIDs."""
    action_count = sum(event["name"] == "action_executed" for event in events)
    survived = bool(
        first
        and second
        and first["pid"] != parent_pid
        and second["pid"] != parent_pid
        and _disk_recovery(first)
        and _disk_recovery(second)
    )
    return {
        **scenario.proposal_checks(proposal),
        "paused_for_approval": any(
            event["name"] == "gate_reached" for event in events
        ),
        "no_action_before_approval": _approval_precedes_actions(events),
        "one_action_after_resume": bool(first)
        and action_count == (1 if approve else 0),
        "survived_process_boundary": survived,
        "idempotent_second_resume": bool(
            survived
            and first
            and second
            and first["checkpoint_id"] == second["checkpoint_id"]
            and not second["actions"]
        ),
    }


def _disk_recovery(resumed: ResumeResult | None) -> bool:
    """Require a checkpoint, configuration read and state read."""
    if resumed is None:
        return False
    files = {Path(path).name for path in resumed["files_read"]}
    return bool(
        resumed["restored"]
        and resumed["checkpoint_id"]
        and "run.json" in files
        and files - {"run.json", "events.sqlite3"}
    )


def _approval_precedes_actions(events: list[dict[str, object]]) -> bool:
    """Evaluate order and decision values without trusting a summary."""
    approved = False
    for event in events:
        if event["name"] == "approval_recorded":
            details = cast("dict[str, object]", event["details"])
            approved = details.get("approved") is True
        if event["name"] == "action_executed" and not approved:
            return False
    return True


def main(
    arguments: Sequence[str] | None = None,
    *,
    dispatch: Callable[[Path, bool, str], Awaitable[ResumeResult]]
    | None = None,
) -> int:
    """Print one JSON document; keep SDK diagnostic text on stderr."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("decision", choices=("approve", "reject"))
    parser.add_argument(
        "--execution", choices=("offline", "live"), required=True
    )
    options = parser.parse_args(arguments)
    try:
        with redirect_stdout(sys.stderr):
            resumed = asyncio.run(
                run_worker(
                    options.directory,
                    options.decision == "approve",
                    options.execution,
                    dispatch=dispatch,
                )
            )
    except (ResumeError, OSError, TypeError, ValueError, ImportError):
        print(json.dumps({"error": {"code": "resume_worker_failed"}}))
        return 1
    print(json.dumps(resumed))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Job lifecycle transitions (product plan §42).

Rule 4: every expensive op is observable + cancellable — the lifecycle
below is the state machine every job honors.
"""

from __future__ import annotations

from shared.domain import JobStatus


class InvalidTransitionError(ValueError):
    """Raised when a job transition is not allowed (§42)."""


ALLOWED_TRANSITIONS: dict[JobStatus, frozenset[JobStatus]] = {
    JobStatus.CREATED: frozenset({JobStatus.QUEUED, JobStatus.CANCELLED}),
    JobStatus.QUEUED: frozenset({JobStatus.RUNNING, JobStatus.CANCELLED}),
    JobStatus.RUNNING: frozenset(
        {JobStatus.PAUSED, JobStatus.FAILED, JobStatus.CANCELLED, JobStatus.COMPLETED}
    ),
    JobStatus.PAUSED: frozenset({JobStatus.RUNNING, JobStatus.CANCELLED}),
    JobStatus.FAILED: frozenset({JobStatus.QUEUED}),
    JobStatus.CANCELLED: frozenset(),  # terminal
    JobStatus.COMPLETED: frozenset(),  # terminal
}


def transition(current: JobStatus, to: JobStatus) -> JobStatus:
    """Move a job from `current` to `to`; raise InvalidTransitionError if illegal."""
    allowed = ALLOWED_TRANSITIONS.get(current, frozenset())
    if to not in allowed:
        raise InvalidTransitionError(
            f"Invalid job transition: {current.value} -> {to.value} "
            f"(allowed: {sorted(s.value for s in allowed) or 'none — terminal state'})"
        )
    return to

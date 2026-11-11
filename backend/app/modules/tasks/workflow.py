"""The one place that decides which task status changes are allowed, and by whom.

Requirements: TASK-002..004, TASK-009.

Kinds of actor:
- "assign": a user holding tasks.assign in the task's project (Project Admin, Super Admin)
- "moderator": the task's active moderator assignee
- "system": only the platform's own modules (recording, audio QC); never reachable through the
  generic transition API, so a status cannot be faked by hand.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.errors import AppError

TERMINAL = frozenset({"APPROVED", "REJECTED", "CANCELLED"})

# Exception states need a reason code from a fixed list; OTHER also needs a comment.
REASONS: dict[str, frozenset[str]] = {
    "ON_HOLD": frozenset(
        {"WAITING_FOR_PARTICIPANT", "TECHNICAL_PROBLEM", "CLIENT_REQUEST", "OTHER"}
    ),
    "CANCELLED": frozenset(
        {"PARTICIPANT_UNAVAILABLE", "CONSENT_REFUSED", "DUPLICATE_TASK", "CLIENT_REQUEST", "OTHER"}
    ),
    "REJECTED": frozenset({"AUDIO_QUALITY", "CONSENT_PROBLEM", "WRONG_SPEAKERS", "OTHER"}),
    "RETURNED": frozenset({"RE_RECORD", "NEEDS_CORRECTION", "OTHER"}),
}

_T: dict[str, dict[str, str]] = {
    "DRAFT": {"ASSIGNED": "system", "ON_HOLD": "assign", "CANCELLED": "assign"},
    "ASSIGNED": {"IN_PROGRESS": "moderator", "ON_HOLD": "assign", "CANCELLED": "assign"},
    "IN_PROGRESS": {"RECORDED": "system", "ON_HOLD": "assign", "CANCELLED": "assign"},
    # D-092: the moderator listens first and sends the recording on, or records it again.
    "RECORDED": {"AUDIO_QC": "moderator", "IN_PROGRESS": "moderator", "CANCELLED": "assign"},
    # A pass at audio QC goes to the project admin for the final word (D-092); a fail or a return
    # is the QC Executive's decision as before (D-062: no manual transcription).
    "AUDIO_QC": {"ADMIN_REVIEW": "system", "REJECTED": "system", "RETURNED": "system"},
    "ADMIN_REVIEW": {"APPROVED": "assign", "REJECTED": "assign", "RETURNED": "assign"},
    "RETURNED": {"ASSIGNED": "assign", "CANCELLED": "assign"},
    "ON_HOLD": {"CANCELLED": "assign"},  # resuming to the held status is handled below
}

FORWARD_PATH = (
    "DRAFT",
    "ASSIGNED",
    "IN_PROGRESS",
    "RECORDED",
    "AUDIO_QC",
    "ADMIN_REVIEW",
    "APPROVED",
)


@dataclass(frozen=True)
class Actor:
    system: bool = False
    can_assign: bool = False
    is_moderator: bool = False


SYSTEM = Actor(system=True)


def required_kind(current: str, target: str, held_from: str | None) -> str | None:
    if current == "ON_HOLD" and target == held_from:
        return "assign"
    return _T.get(current, {}).get(target)


def check(
    current: str,
    target: str,
    actor: Actor,
    *,
    held_from: str | None,
    reason_code: str | None,
    comment: str,
) -> None:
    kind = required_kind(current, target, held_from)
    if kind is None:
        raise AppError(
            f"A task cannot move from {current} to {target}",
            code="INVALID_TRANSITION",
            status_code=409,
        )
    if kind == "system" and not actor.system:
        raise AppError(
            f"{target} is set automatically by the platform, not by hand",
            code="INVALID_TRANSITION",
            status_code=409,
        )
    if not actor.system:
        allowed = (kind == "assign" and actor.can_assign) or (
            kind == "moderator" and actor.is_moderator
        )
        if not allowed:
            raise AppError(
                "You do not have permission to do this", code="FORBIDDEN", status_code=403
            )
    if target in REASONS:
        if reason_code not in REASONS[target]:
            raise AppError(
                f"Choose a reason: {', '.join(sorted(REASONS[target]))}",
                code="REASON_REQUIRED",
                status_code=422,
            )
        if reason_code == "OTHER" and not comment.strip():
            raise AppError(
                "Explain the reason in the comment", code="COMMENT_REQUIRED", status_code=422
            )


def user_options(current: str, held_from: str | None, actor: Actor) -> list[str]:
    """Statuses this user may move the task to now (drives the UI; the server re-checks)."""
    options = []
    targets = dict(_T.get(current, {}))
    if current == "ON_HOLD" and held_from:
        targets[held_from] = "assign"
    for target, kind in targets.items():
        if (kind == "assign" and actor.can_assign) or (kind == "moderator" and actor.is_moderator):
            options.append(target)
    return sorted(options)

"""The platform checks itself and tells the people who run it (OPS-006, D-109).

With every recovery sweep (each web process, every RECOVERY_INTERVAL_SECONDS) the platform looks
for things that need a person:

- STORAGE_UNREACHABLE, REDIS_UNREACHABLE: a part it depends on does not answer;
- RECORDINGS_FAILED: recordings whose processing failed;
- RECORDINGS_STUCK: uploads waiting for processing far longer than recovery should allow;
- CALLS_NEED_PERSON: phone calls whose recording a person must pick or fetch again;
- EXPORTS_FAILED: exports that failed in the last day.

What it finds is kept in `operation_alerts` and shown on the Super Admin's System status page.
When ALERT_EMAIL is set, one email names everything that is wrong: when something new appears,
then again every ALERT_REPEAT_HOURS while anything is still wrong, and once more when all is
clear. Several web processes run the sweep; a database lock lets one of them do this at a time.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.email import EmailSender, OutgoingEmail
from app.modules.exports.models import ExportJob
from app.modules.operations.models import OperationAlert
from app.modules.recordings.models import Recording
from app.modules.telephony.models import Call

logger = logging.getLogger("app.operations")

LOCK_KEY = 0x0CC9A1E7  # one process reviews at a time (pg_try_advisory_xact_lock)
STUCK_FACTOR = 4  # times PROCESSING_STALE_MINUTES before waiting uploads count as stuck


@dataclass(frozen=True)
class Problem:
    code: str
    count: int
    summary: str


def _plural(n: int, one: str, many: str) -> str:
    return f"{n} {one if n == 1 else many}"


def find_problems(db: Session, settings: Settings, checks: dict[str, Any]) -> list[Problem]:
    """What needs a person now. `checks` are the component checks of /health/ready."""
    problems: list[Problem] = []
    if checks.get("storage") == "error":
        problems.append(
            Problem(
                "STORAGE_UNREACHABLE",
                1,
                "File storage does not answer: nothing can be stored or played.",
            )
        )
    if checks.get("redis") == "error":
        problems.append(
            Problem(
                "REDIS_UNREACHABLE",
                1,
                "The work queue (Redis) does not answer: recordings wait to be processed.",
            )
        )
    now = datetime.now(UTC)
    failed = int(
        db.scalar(select(func.count()).select_from(Recording).where(Recording.state == "FAILED"))
        or 0
    )
    if failed:
        problems.append(
            Problem(
                "RECORDINGS_FAILED",
                failed,
                f"{_plural(failed, 'recording', 'recordings')} could not be processed.",
            )
        )
    waiting_since = now - timedelta(minutes=settings.processing_stale_minutes * STUCK_FACTOR)
    stuck = int(
        db.scalar(
            select(func.count())
            .select_from(Recording)
            .where(
                Recording.state.in_(("UPLOADED", "PROCESSING")),
                Recording.updated_at < waiting_since,
            )
        )
        or 0
    )
    if stuck:
        problems.append(
            Problem(
                "RECORDINGS_STUCK",
                stuck,
                f"{_plural(stuck, 'recording has', 'recordings have')} waited for processing "
                f"for over {settings.processing_stale_minutes * STUCK_FACTOR} minutes.",
            )
        )
    calls = int(
        db.scalar(
            select(func.count())
            .select_from(Call)
            .where(Call.state.in_(("NEEDS_MATCH", "FETCH_FAILED")))
        )
        or 0
    )
    if calls:
        problems.append(
            Problem(
                "CALLS_NEED_PERSON",
                calls,
                f"{_plural(calls, 'phone call waits', 'phone calls wait')} for a person to pick "
                "or fetch the recording.",
            )
        )
    exports = int(
        db.scalar(
            select(func.count())
            .select_from(ExportJob)
            .where(ExportJob.state == "FAILED", ExportJob.finished_at >= now - timedelta(days=1))
        )
        or 0
    )
    if exports:
        problems.append(
            Problem(
                "EXPORTS_FAILED",
                exports,
                f"{_plural(exports, 'export', 'exports')} failed in the last 24 hours.",
            )
        )
    return problems


def recipients(settings: Settings) -> list[str]:
    return [a.strip() for a in (settings.alert_email or "").split(",") if a.strip()]


def active(db: Session) -> list[OperationAlert]:
    return list(
        db.scalars(
            select(OperationAlert)
            .where(OperationAlert.active.is_(True))
            .order_by(OperationAlert.first_seen_at)
        )
    )


def review(
    db: Session, settings: Settings, sender: EmailSender, problems: list[Problem]
) -> str | None:
    """Records what was found and emails when there is something new to say. Returns what was
    sent: "problems", "all_clear" or None (also None when another process is at it)."""
    if not db.execute(text("SELECT pg_try_advisory_xact_lock(:k)"), {"k": LOCK_KEY}).scalar():
        db.rollback()
        return None
    now = datetime.now(UTC)
    rows = {r.code: r for r in db.scalars(select(OperationAlert))}
    was_active = [r for r in rows.values() if r.active]
    found = {p.code: p for p in problems}
    new: list[str] = []
    for code, problem in found.items():
        row = rows.get(code)
        if row is None:
            row = OperationAlert(code=code, first_seen_at=now, last_seen_at=now)
            db.add(row)
            rows[code] = row
        if not row.active:
            row.active = True
            row.first_seen_at = now
            row.resolved_at = None
            row.last_emailed_at = None
            new.append(code)
        row.count = problem.count
        row.summary = problem.summary
        row.last_seen_at = now
    for row in was_active:
        if row.code not in found:
            row.active = False
            row.resolved_at = now
    still = [rows[code] for code in found]
    to = recipients(settings)
    repeat = timedelta(hours=settings.alert_repeat_hours)
    told = [r.last_emailed_at for r in still if r.last_emailed_at is not None]
    due = bool(still) and (bool(new) or not told or now - max(told) >= repeat)
    sent: str | None = None
    if to and due:
        if _send(sender, to, _problems_email(settings, still)):
            for row in still:
                row.last_emailed_at = now
            sent = "problems"
    elif to and not still and any(r.last_emailed_at for r in was_active):
        _send(sender, to, _clear_email(settings, was_active))
        sent = "all_clear"
    db.commit()
    if new:
        logger.warning("operation_alerts_new", extra={"codes": new})
    return sent


def _problems_email(settings: Settings, rows: list[OperationAlert]) -> tuple[str, str]:
    lines = [f"- {r.summary} (since {r.first_seen_at:%Y-%m-%d %H:%M} UTC)" for r in rows]
    subject = (
        f"[Conversation Collection] {_plural(len(rows), 'thing needs', 'things need')} attention"
    )
    body = "\n".join(
        [
            "The platform checked itself and found:",
            "",
            *lines,
            "",
            f"System status: {settings.public_app_url.rstrip('/')}/status",
            "What to do for each of these is in docs/OPERATIONS_RUNBOOK.md, section 4.",
            "",
            f"This message is repeated every {settings.alert_repeat_hours} hours while anything"
            " is still wrong, and you get one more when all is clear.",
        ]
    )
    return subject, body


def _clear_email(settings: Settings, rows: list[OperationAlert]) -> tuple[str, str]:
    lines = [f"- {r.summary}" for r in rows]
    body = "\n".join(
        [
            "Everything the platform reported earlier is in order again:",
            "",
            *lines,
            "",
            f"System status: {settings.public_app_url.rstrip('/')}/status",
        ]
    )
    return "[Conversation Collection] All clear", body


def _send(sender: EmailSender, to: list[str], message: tuple[str, str]) -> int:
    """Sends to every address; returns how many were sent. One that cannot be sent must not
    stop the sweep: the problem stays on the status page and the email is tried again."""
    subject, body = message
    done = 0
    for address in to:
        try:
            sender.send(OutgoingEmail(to=address, subject=subject, body=body))
            done += 1
        except Exception:
            logger.exception("operation_alert_email_failed")
    return done

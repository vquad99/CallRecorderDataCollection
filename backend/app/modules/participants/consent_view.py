"""One participant's consent form as answered (D-074): what staff see behind "View" on the
Participants page, and the same thing as a printable file.

It shows the participant's own latest answer on the project's consent form - the form text they
answered, its version, the answer, when, and the staff review - plus their earlier answers. It
needs the same right as the consent history, and names the participant by code only in the file.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from html import escape

from sqlalchemy.orm import Session

from app.modules.audit import service as audit
from app.modules.auth.deps import Principal
from app.modules.participants import service
from app.modules.participants.models import ConsentRecord

ANSWER_WORDS = {"GIVEN": "Agreed", "REFUSED": "Did not agree", "WITHDRAWN": "Withdrew consent"}
REVIEW_WORDS = {"PENDING": "Waiting for review", "APPROVED": "Approved", "REJECTED": "Sent back"}


@dataclass
class Answer:
    status: str
    answered_at: datetime
    policy_version: str
    review_status: str | None
    review_note: str
    reviewed_at: datetime | None


@dataclass
class ConsentForm:
    participant_code: str
    project_code: str
    project_name: str
    form_text: str  # the text of the latest answer; the project's current form if none yet
    form_version: str
    answered: bool
    current: Answer | None
    earlier: list[Answer]


def _answer(r: ConsentRecord) -> Answer:
    return Answer(
        status=r.status,
        answered_at=r.created_at,
        policy_version=r.policy_version,
        review_status=r.review_status,
        review_note=r.review_note,
        reviewed_at=r.reviewed_at,
    )


def get(
    db: Session, principal: Principal, project_id: uuid.UUID, participant_id: uuid.UUID
) -> ConsentForm:
    # Same access rule as the consent history (raises 403 / 404 itself).
    history = service.consent_history(db, principal, project_id, participant_id)
    project, participant = service.get_in_project(db, principal, project_id, participant_id)
    own = [r for r in history if r.task_id is None and r.captured_by is None]  # newest first
    latest = own[0] if own else None
    return ConsentForm(
        participant_code=participant.participant_code,
        project_code=project.code,
        project_name=project.name,
        form_text=latest.form_text if latest and latest.form_text else project.consent_text,
        form_version=latest.policy_version if latest else project.consent_policy_version,
        answered=latest is not None,
        current=_answer(latest) if latest else None,
        earlier=[_answer(r) for r in own[1:]],
    )


def _when(value: datetime | None) -> str:
    return value.astimezone(UTC).strftime("%Y-%m-%d %H:%M UTC") if value else "-"


def _row(label: str, value: str) -> str:
    return f"<tr><th>{escape(label)}</th><td>{escape(value)}</td></tr>"


def as_file(
    db: Session,
    principal: Principal,
    project_id: uuid.UUID,
    participant_id: uuid.UUID,
    ip: str | None,
) -> tuple[str, str]:
    """(file name, printable HTML) for one participant's consent form."""
    form = get(db, principal, project_id, participant_id)
    rows = [_row("Project", f"{form.project_code} - {form.project_name}")]
    rows.append(_row("Participant", form.participant_code))
    rows.append(_row("Form version", form.form_version))
    if form.current:
        c = form.current
        rows.append(_row("Answer", ANSWER_WORDS.get(c.status, c.status)))
        rows.append(_row("Answered on", _when(c.answered_at)))
        rows.append(_row("Answered by", "The participant, on their personal page"))
        if c.review_status:
            rows.append(_row("Review", REVIEW_WORDS.get(c.review_status, c.review_status)))
            if c.reviewed_at:
                rows.append(_row("Reviewed on", _when(c.reviewed_at)))
            if c.review_note:
                rows.append(_row("Review note", c.review_note))
    else:
        rows.append(_row("Answer", "Not answered yet"))
    earlier = "".join(
        f"<tr><td>{escape(_when(a.answered_at))}</td>"
        f"<td>{escape(ANSWER_WORDS.get(a.status, a.status))}</td>"
        f"<td>{escape(a.policy_version)}</td></tr>"
        for a in form.earlier
    )
    css = (
        "body{font-family:system-ui,sans-serif;max-width:800px;margin:32px auto;padding:0 20px;"
        "color:#111;line-height:1.5}h1{font-size:22px}h2{font-size:16px;margin-top:26px}"
        "table{border-collapse:collapse;width:100%}td,th{border:1px solid #ccc;padding:6px 10px;"
        "text-align:left;font-size:14px}th{background:#f3f3f3;width:30%}"
        ".form{white-space:pre-wrap;border:1px solid #ccc;padding:14px;background:#fafafa}"
        ".foot{margin-top:28px;color:#555;font-size:12px}"
    )
    html = (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        f"<title>Consent form {escape(form.participant_code)}</title><style>{css}</style></head>"
        f"<body><h1>Consent form - participant {escape(form.participant_code)}</h1>"
        f"<table>{''.join(rows)}</table><h2>Form text</h2>"
        f'<div class="form">{escape(form.form_text) or "No consent form published."}</div>'
        + (
            "<h2>Earlier answers</h2><table><tr><th>When</th><th>Answer</th><th>Version</th></tr>"
            f"{earlier}</table>"
            if earlier
            else ""
        )
        + f'<p class="foot">Generated {_when(datetime.now(UTC))} by Conversation Collection. '
        "The participant is shown by code only.</p></body></html>"
    )
    project, participant = service.get_in_project(db, principal, project_id, participant_id)
    audit.record(
        db,
        action="consent.form_downloaded",
        entity_type="participant",
        entity_id=participant.id,
        project_id=project.id,
        actor_id=principal.user_id,
        ip=ip,
    )
    db.commit()
    return f"consent_{form.project_code}_{form.participant_code}.html", html


__all__ = ["ConsentForm", "as_file", "get"]

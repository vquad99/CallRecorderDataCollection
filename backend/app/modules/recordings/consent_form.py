"""The consent record that travels with a recording (D-068): one printable HTML file per
recording, downloaded together with the audio.

It holds, for both participants of the recording's task: the consent the moderator recorded for
this task, and the participant's own answers on the project's consent form, each with the form
text they answered, its version and the time. Participants appear by code only, so the file can be
handed over with the audio without carrying names or phone numbers. HTML, not PDF: it prints the
same, needs no font files, and shows any script (Hindi and other Indian languages) correctly.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from html import escape

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.permissions import Perm
from app.modules.audit import service as audit
from app.modules.auth.deps import Principal
from app.modules.participants.models import ConsentRecord, Participant
from app.modules.projects.models import Project
from app.modules.recordings import service
from app.modules.recordings.models import AudioAsset, Recording
from app.modules.tasks.models import Task

STATUS_WORDS = {"GIVEN": "Consent given", "REFUSED": "Consent refused", "WITHDRAWN": "Withdrawn"}
METHOD_WORDS = {
    "VERBAL_RECORDED": "spoken, on the recording",
    "VERBAL_NOTED": "spoken, noted by the moderator",
    "WRITTEN": "written",
    "DIGITAL": "online form",
}
CSS = (
    "body{font-family:system-ui,sans-serif;max-width:820px;margin:32px auto;padding:0 20px;"
    "color:#111;line-height:1.5}h1{font-size:22px}h2{font-size:17px;margin-top:28px;"
    "border-bottom:1px solid #ccc;padding-bottom:4px}table{border-collapse:collapse;width:100%}"
    "td,th{border:1px solid #ccc;padding:6px 10px;text-align:left;vertical-align:top;"
    "font-size:14px}th{background:#f3f3f3;width:32%}.form{white-space:pre-wrap;border:1px solid "
    "#ccc;padding:12px;background:#fafafa;font-size:14px}.none{color:#a00}"
    ".foot{margin-top:32px;color:#555;font-size:12px}"
)


def _when(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y-%m-%d %H:%M UTC")


def _row(label: str, value: str) -> str:
    return f"<tr><th>{escape(label)}</th><td>{escape(value)}</td></tr>"


def _events(records: list[ConsentRecord], *, own: bool) -> str:
    if not records:
        return '<p class="none">Nothing on record.</p>'
    parts = []
    for r in records:
        rows = [
            _row("Answer", STATUS_WORDS.get(r.status, r.status)),
            _row("When", _when(r.created_at)),
            _row("How", METHOD_WORDS.get(r.method, r.method)),
            _row("Form version", r.policy_version),
            _row(
                "Recorded by",
                (
                    "The participant's personal page, from a link handed out by staff"
                    if r.link_shown_to is not None
                    else "The participant"
                )
                if own
                else "The moderator of this session",
            ),
        ]
        if r.note and not own:
            rows.append(_row("Note", r.note))
        block = f"<table>{''.join(rows)}</table>"
        if own and r.form_text.strip():
            block += f'<p>Form text answered:</p><div class="form">{escape(r.form_text)}</div>'
        parts.append(block)
    return "<br>".join(parts)


def build(
    db: Session, principal: Principal, recording_id: uuid.UUID, ip: str | None
) -> tuple[str, str]:
    """(file name, HTML). Needs the same rights as downloading the recording itself."""
    rec, task = service.get_recording(db, principal, recording_id)
    if not principal.can_in_project(Perm.RECORDINGS_DOWNLOAD, task.project_id):
        raise AppError("You do not have permission to do this", code="FORBIDDEN", status_code=403)
    project = db.get(Project, task.project_id)
    assert project is not None  # noqa: S101  (foreign key guarantees it)
    html = render(db, rec, task, project)
    audit.record(
        db,
        action="recording.consent_form_download",
        entity_type="recording",
        entity_id=rec.id,
        project_id=task.project_id,
        actor_id=principal.user_id,
        ip=ip,
    )
    db.commit()
    return f"consent_{task.task_code}_{rec.id}.html", html


def render(db: Session, rec: Recording, task: Task, project: Project) -> str:
    """The consent record's HTML, for a caller that has already checked access (D-094)."""
    assets = db.scalars(
        select(AudioAsset)
        .where(AudioAsset.recording_id == rec.id, AudioAsset.deleted_at.is_(None))
        .order_by(AudioAsset.kind)
    ).all()
    sections = []
    for letter, participant_id in (("A", task.participant_a_id), ("B", task.participant_b_id)):
        participant = db.get(Participant, participant_id)
        assert participant is not None  # noqa: S101
        records = db.scalars(
            select(ConsentRecord)
            .where(
                ConsentRecord.participant_id == participant_id,
                ConsentRecord.project_id == task.project_id,
                or_(ConsentRecord.task_id == task.id, ConsentRecord.task_id.is_(None)),
            )
            .order_by(ConsentRecord.created_at)
        ).all()
        session = [r for r in records if r.task_id == task.id]
        own = [r for r in records if r.task_id is None and r.captured_by is None]
        sections.append(
            f"<h2>Participant {letter}: {escape(participant.participant_code)}</h2>"
            f"<table>{_row('Language', participant.language_code)}</table>"
            f"<h3>Consent for this session</h3>{_events(session, own=False)}"
            f"<h3>Participant's own answers on the consent form</h3>{_events(own, own=True)}"
        )
    files = "".join(_row(a.kind.replace("_", " ").title(), f"SHA-256 {a.sha256}") for a in assets)
    html = (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        f"<title>Consent record {escape(task.task_code)}</title><style>{CSS}</style></head><body>"
        f"<h1>Consent record for recording {escape(task.task_code)}</h1><table>"
        + _row("Project", f"{project.code} - {project.name}")
        + _row("Session", task.task_code)
        + _row("Recording", str(rec.id))
        + _row("Recorded on", _when(rec.started_at))
        + _row("Type", "Phone call" if task.recording_mode == "TELEPHONY" else "In person")
        + _row("Current form version", project.consent_policy_version)
        + "</table>"
        + "".join(sections)
        + (f"<h2>Files this record belongs to</h2><table>{files}</table>" if files else "")
        + f'<p class="foot">Generated {_when(datetime.now(UTC))} from the consent records held by '
        "Conversation Collection. Participants are shown by code only.</p></body></html>"
    )
    return html


__all__ = ["build", "render"]

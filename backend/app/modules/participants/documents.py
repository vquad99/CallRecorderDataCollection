"""Uploaded participant documents (D-144): a participant's scanned signed consent form for one
project, and their address proof (one for the person, whatever the project).

Files live in the private object storage under keys nobody can guess; people open them through
short-lived links (STOR-005). A new upload replaces the current one of its kind; the older one
stays, marked replaced, with who uploaded it and when. Only PDF, JPEG and PNG files are taken,
recognised by their first bytes, at most MAX_DOCUMENT_BYTES (the request limit in front of the
upload route is the same, core/middleware.py and frontend/nginx.conf). Every upload, replacement
and link is audited, without the file.

Who may do what - one rule, `Access`:
- people who manage participants in the project (Super Admin, Project Admin): both kinds, view
  and upload;
- the moderator of an open task (not approved, rejected or cancelled) with the participant: view
  and upload the consent form for that project, so a form can be put right on the task;
- a QC Executive who decides the QC of a task with the participant (audio_qc.may_decide): view
  that consent form.
Anyone else in the project gets 403, anyone outside it 404 (participants.get_in_project). A
consent form is uploaded only while the project takes uploads (`consent_mode` UPLOAD), and only
there does it count as consent (participants/consent.py).
"""

from __future__ import annotations

import hashlib
import logging
import uuid
from collections.abc import Collection
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import unquote

from botocore.exceptions import BotoCoreError, ClientError
from sqlalchemy import ColumnElement, or_, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import AppError, forbidden, not_found
from app.core.permissions import Perm, Role
from app.core.storage import ObjectStorage, configured
from app.modules.audio_qc import service as audio_qc
from app.modules.audit import service as audit
from app.modules.auth.deps import Principal
from app.modules.participants import consent
from app.modules.participants import service as participants
from app.modules.participants.models import (
    ADDRESS_PROOF,
    CONSENT_FORM,
    DOCUMENT_KINDS,
    Participant,
    ParticipantDocument,
    current_documents,
    of_project,
)
from app.modules.projects.models import Project
from app.modules.tasks.models import Task, TaskAssignment
from app.modules.users.service import display_names

logger = logging.getLogger(__name__)

# The largest file taken: 10 MB, enough for a few scanned pages.
MAX_DOCUMENT_BYTES = 10 * 1024 * 1024
TOO_LARGE = (
    f"The file is larger than {MAX_DOCUMENT_BYTES // (1024 * 1024)} MB. Scan it again at a lower "
    "resolution, or save it as a smaller PDF."
)
# How the upload route names each kind.
KIND_PATHS = {"consent-form": CONSENT_FORM, "address-proof": ADDRESS_PROOF}
# A file's first bytes, its type and the extension it is stored with.
_SIGNATURES = (
    (b"%PDF-", "application/pdf", "pdf"),
    (b"\xff\xd8\xff", "image/jpeg", "jpg"),
    (b"\x89PNG\r\n\x1a\n", "image/png", "png"),
)


@dataclass(frozen=True)
class Access:
    """What the caller may do with one participant's documents in one project."""

    manager: bool = False  # manages participants in the project
    moderator: bool = False  # moderates an open task with the participant
    qc: bool = False  # decides the QC of a task with the participant

    @property
    def any(self) -> bool:
        return self.manager or self.moderator or self.qc

    def may_view(self, kind: str) -> bool:
        return self.any if kind == CONSENT_FORM else self.manager

    def may_upload(self, kind: str) -> bool:
        return self.manager or (kind == CONSENT_FORM and self.moderator)


def _decides_qc_with(
    db: Session, principal: Principal, project_id: uuid.UUID, participant_id: uuid.UUID
) -> bool:
    """The caller decides the QC of a task with this participant in the project."""
    if not principal.can_in_project(Perm.AUDIO_QC_REVIEW, project_id):
        return False
    checked = db.scalars(
        select(Task)
        .join(TaskAssignment, TaskAssignment.task_id == Task.id)
        .where(
            TaskAssignment.user_id == principal.user_id,
            TaskAssignment.role_code == Role.QC_EXECUTIVE.value,
            TaskAssignment.active.is_(True),
            Task.project_id == project_id,
            or_(Task.participant_a_id == participant_id, Task.participant_b_id == participant_id),
        )
    )
    return any(audio_qc.may_decide(db, principal, task) for task in checked)


def access(
    db: Session, principal: Principal, project: Project, participant_id: uuid.UUID
) -> Access:
    """The caller's rights over this participant's documents in the project (see the top)."""
    if principal.can_in_project(Perm.PARTICIPANTS_MANAGE, project.id):
        return Access(manager=True)
    if participants.moderator_assigned(db, principal.user_id, participant_id, project.id):
        return Access(moderator=True)
    return Access(qc=_decides_qc_with(db, principal, project.id, participant_id))


def file_type(data: bytes) -> tuple[str, str]:
    """(content type, extension) of an uploaded file, from its first bytes: 422 for an empty file
    or one that is not a PDF, JPEG or PNG, 413 for one over the limit."""
    if len(data) > MAX_DOCUMENT_BYTES:
        raise AppError(TOO_LARGE, code="PAYLOAD_TOO_LARGE", status_code=413)
    if not data:
        raise AppError("The file is empty.", code="INVALID_FILE", status_code=422)
    for magic, content_type, extension in _SIGNATURES:
        if data.startswith(magic):
            return content_type, extension
    raise AppError(
        "Only PDF, JPEG or PNG files can be uploaded, and this file is none of them. "
        "Scan the page again as a PDF or a photo.",
        code="INVALID_FILE_TYPE",
        status_code=422,
    )


def clean_name(sent: str | None, kind: str, extension: str) -> str:
    """The file's name as people see it: the browser's name (sent percent-encoded) without any
    folder or control characters, at most 200 characters; a plain name when none was sent."""
    name = unquote(sent or "").replace("\\", "/").rsplit("/", 1)[-1]
    name = "".join(ch for ch in name if ch.isprintable()).strip()
    return (name or f"{kind.lower()}.{extension}")[:200]


def _storage_key(project: Project, participant: Participant, kind: str, doc_id: uuid.UUID) -> str:
    where = project.code if kind == CONSENT_FORM else "person"
    return f"documents/{participant.participant_code}/{kind.lower()}/{where}/{doc_id}"


def _store(storage: ObjectStorage, key: str, data: bytes, content_type: str, sha256: str) -> None:
    """Puts the file into storage and checks that it arrived whole; 503 when storage fails."""
    try:
        storage.put_bytes(key, data, content_type=content_type, sha256=sha256)
        stored = storage.head(key)
    except (BotoCoreError, ClientError):
        logger.exception("document_storage_unavailable")
        stored = None
    if stored is None or (stored.size, stored.sha256) != (len(data), sha256):
        raise AppError(
            "The file could not be stored right now. Try again shortly.",
            code="STORAGE_UNAVAILABLE",
            status_code=503,
            headers={"Retry-After": "5"},
        )


def upload(
    db: Session,
    storage: ObjectStorage | None,
    principal: Principal,
    project_id: uuid.UUID,
    participant_id: uuid.UUID,
    kind: str,
    data: bytes,
    sent_name: str | None,
    ip: str | None,
) -> ParticipantDocument:
    """Stores a new document of this kind for the participant; it replaces the current one."""
    project, participant = participants.get_in_project(db, principal, project_id, participant_id)
    if not access(db, principal, project, participant.id).may_upload(kind):
        raise forbidden()
    if participant.deleted_at is not None:
        raise AppError("This participant was deleted", code="PARTICIPANT_DELETED", status_code=409)
    if kind == CONSENT_FORM and not consent.takes_uploads(project):
        raise AppError(
            "This project takes consent online: the participant agrees on their personal page. "
            "To upload signed consent forms, set the project's Consent to Upload.",
            code="CONSENT_ONLINE",
            status_code=409,
        )
    content_type, extension = file_type(data)
    store = configured(storage)
    doc_id = uuid.uuid4()
    key = _storage_key(project, participant, kind, doc_id)
    digest = hashlib.sha256(data).hexdigest()
    _store(store, key, data, content_type, digest)
    # One current document of a kind: uploads at the same moment take turns, the participant's
    # row is locked until the commit. A file stored but never saved here is cleaned up by the
    # storage-orphans command (O12).
    db.execute(select(Participant.id).where(Participant.id == participant.id).with_for_update())
    previous = db.scalar(current_documents(project.id, [participant.id], (kind,)))
    now = datetime.now(UTC)
    if previous is not None:
        previous.replaced_at = now
        previous.replaced_by = principal.user_id
        db.flush()
    doc = ParticipantDocument(
        id=doc_id,
        participant_id=participant.id,
        project_id=project.id if kind == CONSENT_FORM else None,
        kind=kind,
        storage_key=key,
        file_name=clean_name(sent_name, kind, extension),
        content_type=content_type,
        size_bytes=len(data),
        sha256=digest,
        uploaded_by=principal.user_id,
        uploaded_at=now,
    )
    db.add(doc)
    audit.record(
        db,
        action="participant.document_replaced" if previous else "participant.document_uploaded",
        entity_type="participant_document",
        entity_id=doc.id,
        project_id=project.id,
        actor_id=principal.user_id,
        ip=ip,
        before={"document_id": str(previous.id), "sha256": previous.sha256} if previous else None,
        after={
            "participant_id": str(participant.id),
            "kind": kind,
            "content_type": content_type,
            "size_bytes": len(data),
            "sha256": digest,
        },
    )
    db.commit()
    return doc


@dataclass(frozen=True)
class Listing:
    """One participant's documents in a project, as far as the caller may see them."""

    project: Project
    participant: Participant
    access: Access
    current: dict[str, ParticipantDocument]  # by kind
    earlier: list[ParticipantDocument]  # replaced ones, newest first
    names: dict[uuid.UUID, str]  # who uploaded and replaced them

    def may_upload(self, kind: str) -> bool:
        """Whether the window offers Upload: allowed to, the participant is not removed, and a
        consent form only where the project takes uploads."""
        return (
            self.access.may_upload(kind)
            and self.participant.deleted_at is None
            and (kind != CONSENT_FORM or consent.takes_uploads(self.project))
        )


def _visible(
    project_id: uuid.UUID, participant_id: uuid.UUID, kinds: Collection[str]
) -> list[ColumnElement[bool]]:
    """This participant's documents of these kinds that count in the project, files not removed."""
    return [
        ParticipantDocument.participant_id == participant_id,
        ParticipantDocument.removed_at.is_(None),
        of_project(project_id, kinds),
    ]


def listing(
    db: Session, principal: Principal, project_id: uuid.UUID, participant_id: uuid.UUID
) -> Listing:
    project, participant = participants.get_in_project(db, principal, project_id, participant_id)
    rights = access(db, principal, project, participant.id)
    if not rights.any:
        raise forbidden()
    kinds = [k for k in DOCUMENT_KINDS if rights.may_view(k)]
    docs = list(
        db.scalars(
            select(ParticipantDocument)
            .where(*_visible(project.id, participant.id, kinds))
            .order_by(ParticipantDocument.uploaded_at.desc())
        )
    )
    return Listing(
        project=project,
        participant=participant,
        access=rights,
        current={d.kind: d for d in docs if d.is_current},
        earlier=[d for d in docs if not d.is_current],
        names=display_names(db, [u for d in docs for u in (d.uploaded_by, d.replaced_by)]),
    )


def view_link(
    db: Session,
    storage: ObjectStorage | None,
    settings: Settings,
    principal: Principal,
    project_id: uuid.UUID,
    participant_id: uuid.UUID,
    document_id: uuid.UUID,
    ip: str | None,
) -> tuple[str, int]:
    """A short-lived link that shows the file in the browser (no download name), and its
    lifetime in seconds. A document the caller may not see answers like a missing one."""
    project, participant = participants.get_in_project(db, principal, project_id, participant_id)
    rights = access(db, principal, project, participant.id)
    if not rights.any:
        raise forbidden()
    kinds = [k for k in DOCUMENT_KINDS if rights.may_view(k)]
    doc = db.scalar(
        select(ParticipantDocument).where(
            ParticipantDocument.id == document_id, *_visible(project.id, participant.id, kinds)
        )
    )
    if doc is None:
        raise not_found("Document")
    seconds = settings.signed_url_seconds
    url = configured(storage).signed_get_url(doc.storage_key, seconds=seconds, download_name=None)
    audit.record(
        db,
        action="participant.document_view_link",
        entity_type="participant_document",
        entity_id=doc.id,
        project_id=project.id,
        actor_id=principal.user_id,
        ip=ip,
        after={"participant_id": str(participant.id), "kind": doc.kind},
    )
    db.commit()
    return url, seconds


def held(
    db: Session, project: Project, participant_ids: Collection[uuid.UUID]
) -> dict[uuid.UUID, set[str]]:
    """The kinds each participant has a current document of in the project, in one query (for
    the lists' "missing" badges)."""
    found: dict[uuid.UUID, set[str]] = {pid: set() for pid in participant_ids}
    if participant_ids:
        for d in db.scalars(current_documents(project.id, participant_ids)):
            found[d.participant_id].add(d.kind)
    return found

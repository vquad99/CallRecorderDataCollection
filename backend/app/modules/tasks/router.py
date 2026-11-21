"""/api/v1/tasks (TASK-*)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.core.permissions import Perm, Role
from app.db.paging import Page, PageNumber, PageSize
from app.modules.audio_qc import service as audio_qc
from app.modules.auth.deps import CurrentPrincipal, DbSession, Principal, client_ip, require
from app.modules.auth.models import User
from app.modules.participants import consent as consents
from app.modules.participants import documents
from app.modules.participants import service as participants
from app.modules.participants.models import CONSENT_FORM, Participant
from app.modules.participants.router import DocumentOut, document_out
from app.modules.projects import moderation
from app.modules.projects.models import Project
from app.modules.projects.service import get_manageable
from app.modules.tasks import bulk, devices, service, workflow
from app.modules.tasks.models import TASK_STATUSES, Task
from app.modules.users.service import display_names

router = APIRouter(
    prefix="/tasks", tags=["tasks"], dependencies=[Depends(require(Perm.TASKS_VIEW))]
)

Status = Literal[
    "DRAFT",
    "ASSIGNED",
    "IN_PROGRESS",
    "RECORDED",
    "AUDIO_QC",
    "ADMIN_REVIEW",
    "APPROVED",
    "REJECTED",
    "CANCELLED",
    "ON_HOLD",
    "CONSENT_FIX",
]
Mode = Literal["TELEPHONY", "FACE_TO_FACE"]
Priority = Literal["LOW", "NORMAL", "HIGH", "URGENT"]


class TaskSummary(BaseModel):
    id: uuid.UUID
    task_code: str
    project_id: uuid.UUID
    recording_mode: Mode
    status: Status
    priority: Priority
    due_at: datetime | None
    created_at: datetime


class PartyOut(BaseModel):
    id: uuid.UUID
    participant_code: str
    # The name, for people who may see the participant's profile (null otherwise, D-128).
    display_label: str | None = None
    has_email: bool = False
    # The participant's consent in the project as it counts now (D-127, D-129): their answer on
    # the consent form, or UPLOADED for a signed form uploaded where the project takes uploads
    # (D-144); and when it was given.
    consent_status: str | None
    consent_at: datetime | None
    may_record: bool = False
    # Projects that take uploads (D-144): the current signed form, for people who may look at it
    # (null otherwise or when there is none), and whether the caller may upload one now.
    consent_form: DocumentOut | None = None
    can_upload_consent_form: bool = False


class ConsentFixParty(BaseModel):
    side: Literal["A", "B"]
    participant_id: uuid.UUID
    participant_code: str
    # A new signed form is on file since QC sent the task back.
    replaced: bool


class ConsentFixOut(BaseModel):
    """A task at CONSENT_FIX (D-146): what QC found wrong with which consent form."""

    comment: str
    by: str | None
    at: datetime
    participants: list[ConsentFixParty]
    # Every form QC found not right was replaced: the task may go back to QC.
    forms_replaced: bool
    # The caller may send it back (the task's moderator, or someone who assigns tasks).
    can_send_back: bool


class RemindersOut(BaseModel):
    """What the moderator reads before recording or calling (D-147), for the task's mode: whether
    to ask each speaker to start with their first name and speaker ID, what to talk about, what to
    avoid, and the tips for this mode."""

    speaker_id: bool
    topics: list[str]
    avoid: list[str]
    tips: list[str]


class TaskDetail(TaskSummary):
    held_from: str | None
    reason_code: str | None
    participant_a: PartyOut
    participant_b: PartyOut
    moderator_id: uuid.UUID | None
    moderator_name: str | None
    allowed_transitions: list[str]
    reasons: dict[str, list[str]]
    can_assign: bool
    # The caller may change the moderator now (assigns tasks, and the status still allows it).
    can_reassign: bool
    is_moderator: bool
    # D-119: participants (A, B) without consent to record; recording is refused until empty.
    consent_missing: list[str]
    # How participants give consent in the project: ONLINE or UPLOAD (D-144).
    consent_mode: Literal["ONLINE", "UPLOAD"] = "ONLINE"
    # At CONSENT_FIX only (D-146): QC's comment, whose form, and who may send it back to QC.
    consent_fix: ConsentFixOut | None = None
    # D-147: the device details the project asks for each speaker (empty: none), and while the
    # task is In progress or Recorded the participants (codes) whose asked details are missing:
    # Send to QC waits for them.
    device_fields: list[str] = []
    device_details_missing: list[str] = []
    reminders: RemindersOut | None = None


def summary(t: Task) -> TaskSummary:
    return TaskSummary.model_validate(t, from_attributes=True)


def detail(db: DbSession, principal: Principal, t: Task) -> TaskDetail:
    sides = consents.for_task(db, t)
    project = db.get_one(Project, t.project_id)
    moderator = service.active_assignee(db, t.id, Role.MODERATOR.value)
    actor = service.actor_from(principal, t, moderator)
    uploads = consents.takes_uploads(project)
    names = display_names(db, [s.form.uploaded_by for s in sides if s.form is not None])

    def party(side: consents.SideConsent) -> PartyOut:
        p = db.get_one(Participant, side.participant_id)
        seen = participants.visibility(db, principal, project, p.id)
        out = PartyOut(
            id=p.id,
            participant_code=p.participant_code,
            display_label=p.display_label if seen.profile else None,
            has_email=p.email_enc is not None,
            consent_status=side.status,
            consent_at=side.standing.at,
            may_record=side.may_record,
        )
        if uploads:
            # The documents' own rule (D-144): who may look at and upload the signed form.
            rights = documents.access(db, principal, project, p.id)
            if side.form is not None and rights.may_view(CONSENT_FORM):
                out.consent_form = document_out(side.form, names)
            out.can_upload_consent_form = rights.may_upload(CONSENT_FORM) and p.deleted_at is None
        return out

    mod_name = (
        db.scalar(select(User.display_name).where(User.id == moderator.user_id))
        if moderator
        else None
    )
    return TaskDetail(
        **summary(t).model_dump(),
        held_from=t.held_from,
        reason_code=t.reason_code,
        participant_a=party(sides[0]),
        participant_b=party(sides[1]),
        moderator_id=moderator.user_id if moderator else None,
        moderator_name=mod_name,
        allowed_transitions=workflow.user_options(t.status, t.held_from, actor),
        reasons={k: sorted(v) for k, v in workflow.REASONS.items()},
        can_assign=actor.can_assign,
        can_reassign=service.can_reassign(actor, t),
        is_moderator=actor.is_moderator,
        consent_missing=consents.missing(sides),
        consent_mode=project.consent_mode,
        consent_fix=audio_qc.consent_fix_view(db, principal, t),
        device_fields=list(project.device_fields),
        device_details_missing=devices.missing_codes(db, project, t),
        reminders=RemindersOut(
            **moderation.reminders_for(project.recording_reminders, t.recording_mode)
        ),
    )


class TaskPage(Page[TaskSummary]):
    pass


@router.get("", response_model=TaskPage)
def list_tasks(
    principal: CurrentPrincipal,
    db: DbSession,
    project_id: uuid.UUID | None = None,
    status: Status | None = None,
    mode: Mode | None = None,
    mine: bool = False,
    search: Annotated[str | None, Query(max_length=40)] = None,
    page: PageNumber = 1,
    page_size: PageSize = 25,
) -> TaskPage:
    f = service.TaskFilter(
        project_id=project_id, status=status, mode=mode, mine=mine, search=search
    )
    items, total = service.list_tasks(db, principal, f, page, page_size)
    return TaskPage(items=[summary(t) for t in items], total=total, page=page, page_size=page_size)


class CreateTaskBody(BaseModel):
    project_id: uuid.UUID
    recording_mode: Mode
    participant_a_id: uuid.UUID
    participant_b_id: uuid.UUID
    priority: Priority = "NORMAL"
    due_at: datetime | None = None
    # Optional: assign the moderator at once, so the task starts as Assigned (D-085).
    moderator_id: uuid.UUID | None = None


@router.post("", response_model=TaskDetail, status_code=201)
def create_task(
    body: CreateTaskBody, request: Request, principal: CurrentPrincipal, db: DbSession
) -> TaskDetail:
    data = service.TaskInput(
        recording_mode=body.recording_mode,
        participant_a_id=body.participant_a_id,
        participant_b_id=body.participant_b_id,
        priority=body.priority,
        due_at=body.due_at,
    )
    ip = client_ip(request)
    if body.moderator_id is not None:
        # Checked before the task exists, so a wrong choice never leaves a half-made task;
        # only someone who may add tasks here learns who is a moderator of the project.
        project = get_manageable(db, principal, body.project_id, Perm.TASKS_ASSIGN)
        service.require_member_with_role(db, project.id, body.moderator_id, Role.MODERATOR)
    task = service.create_task(db, principal, body.project_id, data, ip)
    if body.moderator_id is not None:
        task = service.assign_moderator(db, principal, task.id, body.moderator_id, None, ip)
    return detail(db, principal, task)


class ImportTasksBody(BaseModel):
    project_id: uuid.UUID
    csv: str = Field(min_length=1, max_length=500_000)
    confirm: bool = False


class ImportTaskRow(BaseModel):
    line: int
    pair: str
    ok: bool
    message: str
    task_code: str | None


class ImportTasksOut(BaseModel):
    rows: list[ImportTaskRow]
    ready: int
    created: int


@router.post("/import", response_model=ImportTasksOut)
def import_tasks(
    body: ImportTasksBody, request: Request, principal: CurrentPrincipal, db: DbSession
) -> ImportTasksOut:
    """Add many tasks from a CSV file; check first, then add (D-083)."""
    rows = bulk.import_csv(
        db, principal, body.project_id, body.csv, body.confirm, client_ip(request)
    )
    return ImportTasksOut(
        rows=[ImportTaskRow.model_validate(r, from_attributes=True) for r in rows],
        ready=sum(1 for r in rows if r.ok),
        created=sum(1 for r in rows if r.task_code),
    )


@router.get("/{task_id}", response_model=TaskDetail)
def get_task(task_id: uuid.UUID, principal: CurrentPrincipal, db: DbSession) -> TaskDetail:
    return detail(db, principal, service.get_task(db, principal, task_id))


class AssignBody(BaseModel):
    user_id: uuid.UUID
    reason: str | None = Field(default=None, max_length=1000)


@router.post("/{task_id}/assign", response_model=TaskDetail)
def assign(
    task_id: uuid.UUID,
    body: AssignBody,
    request: Request,
    principal: CurrentPrincipal,
    db: DbSession,
) -> TaskDetail:
    return detail(
        db,
        principal,
        service.assign_moderator(
            db, principal, task_id, body.user_id, body.reason, client_ip(request)
        ),
    )


class DeleteBody(BaseModel):
    reason: str = Field(min_length=1, max_length=500)


@router.post("/{task_id}/delete", status_code=204)
def delete_task(
    task_id: uuid.UUID,
    body: DeleteBody,
    request: Request,
    principal: CurrentPrincipal,
    db: DbSession,
) -> None:
    """Delete a task made by mistake, while nothing has happened on it (D-115)."""
    service.delete_task(db, principal, task_id, body.reason, client_ip(request))


class TransitionBody(BaseModel):
    to: Status
    reason_code: str | None = Field(default=None, max_length=50)
    comment: str = Field(default="", max_length=2000)


@router.post("/{task_id}/transition", response_model=TaskDetail)
def transition(
    task_id: uuid.UUID,
    body: TransitionBody,
    request: Request,
    principal: CurrentPrincipal,
    db: DbSession,
) -> TaskDetail:
    task = service.get_task(db, principal, task_id)
    if task.status == "CONSENT_FIX" and body.to == "AUDIO_QC":
        # Back to QC only once the consent forms QC found wrong were replaced (D-146).
        task = audio_qc.send_back_to_qc(db, principal, task.id, body.comment, client_ip(request))
        return detail(db, principal, task)
    actor = service.actor_for(db, principal, task)
    if task.status == "RECORDED" and body.to == "AUDIO_QC":
        # Who may do it first, then whether the recording's automatic check is there: the
        # moderator sends it on only once QC has something to read (D-092).
        workflow.check(
            task.status,
            body.to,
            actor,
            held_from=task.held_from,
            reason_code=body.reason_code,
            comment=body.comment,
        )
        # Then the device details the project asks, for both people (D-147).
        devices.ensure_complete(db, task)
        audio_qc.ensure_checked(db, task)
    service.transition(
        db,
        task,
        body.to,
        actor,
        actor_id=principal.user_id,
        reason_code=body.reason_code,
        comment=body.comment,
        ip=client_ip(request),
    )
    return detail(db, principal, task)


class SendBackBody(BaseModel):
    comment: str = Field(default="", max_length=2000)


@router.post("/{task_id}/consent-fix/send-to-qc", response_model=TaskDetail)
def send_back_to_qc(
    task_id: uuid.UUID,
    body: SendBackBody,
    request: Request,
    principal: CurrentPrincipal,
    db: DbSession,
) -> TaskDetail:
    """The task's moderator (or someone who assigns tasks) sends the same recording back to QC
    once the consent forms QC found wrong were replaced (D-146)."""
    task = audio_qc.send_back_to_qc(db, principal, task_id, body.comment, client_ip(request))
    return detail(db, principal, task)


DeviceText = Annotated[str | None, Field(max_length=moderation.MAX_DEVICE_TEXT)]


class DeviceValuesIO(BaseModel):
    """One speaker's device details (D-147); null = not answered."""

    device_make: DeviceText = None
    device_model: DeviceText = None
    bluetooth_earphones: bool | None = None
    wired_earphones: bool | None = None
    loudspeaker_on: bool | None = None


class DeviceEntryIn(DeviceValuesIO):
    side: Literal["A", "B"]


class DeviceDetailsBody(BaseModel):
    """Both participants' device details at once, by side."""

    participants: list[DeviceEntryIn] = Field(min_length=1, max_length=2)


class DeviceLastTimeOut(DeviceValuesIO):
    task_code: str
    filled_at: datetime


class DevicePartyOut(BaseModel):
    side: Literal["A", "B"]
    participant_id: uuid.UUID
    participant_code: str
    details: DeviceValuesIO
    filled_by: str | None
    filled_at: datetime | None
    # The asked details not answered yet.
    missing: list[str]
    # Offered to whoever may fill them: the person's newest details on another task of the
    # project ("Same as last time"); never filled in by itself.
    last_time: DeviceLastTimeOut | None


class DeviceDetailsOut(BaseModel):
    # The details the project asks, in the form's order.
    fields: list[str]
    call_type: Literal["Telephonic", "Face-to-face"]
    # The caller may change them now (the task's moderator or an admin, before QC).
    editable: bool
    complete: bool
    participants: list[DevicePartyOut]


def device_details_out(v: devices.View) -> DeviceDetailsOut:
    return DeviceDetailsOut(
        fields=v.fields,
        call_type=v.call_type,
        editable=v.editable,
        complete=v.complete,
        participants=[
            DevicePartyOut(
                side=p.side,
                participant_id=p.participant_id,
                participant_code=p.participant_code,
                details=DeviceValuesIO(**p.values.as_dict()),
                filled_by=p.filled_by,
                filled_at=p.filled_at,
                missing=p.missing,
                last_time=DeviceLastTimeOut(
                    **p.last_time.values.as_dict(),
                    task_code=p.last_time.task_code,
                    filled_at=p.last_time.filled_at,
                )
                if p.last_time
                else None,
            )
            for p in v.participants
        ],
    )


@router.get("/{task_id}/device-details", response_model=DeviceDetailsOut)
def get_device_details(
    task_id: uuid.UUID, principal: CurrentPrincipal, db: DbSession
) -> DeviceDetailsOut:
    """The device each speaker used (D-147), for everyone who may see the task."""
    return device_details_out(devices.view(db, principal, task_id))


@router.put("/{task_id}/device-details", response_model=DeviceDetailsOut)
def put_device_details(
    task_id: uuid.UUID,
    body: DeviceDetailsBody,
    request: Request,
    principal: CurrentPrincipal,
    db: DbSession,
) -> DeviceDetailsOut:
    """The task's moderator (or a project admin) saves both people's device details before the
    task goes to QC (D-147)."""
    entries = {e.side: e.model_dump(exclude={"side"}) for e in body.participants}
    if len(entries) != len(body.participants):
        entries = {}  # a side given twice: the service says both are needed, once each
    return device_details_out(devices.save(db, principal, task_id, entries, client_ip(request)))


class CommentBody(BaseModel):
    body: str = Field(min_length=1, max_length=5000)


class TimelineOut(BaseModel):
    at: datetime
    kind: str
    actor: str | None
    text: str
    # Set for status changes only (kind "status"); null for assignments and comments.
    from_status: str | None = None
    to_status: str | None = None
    reason_code: str | None = None
    comment: str | None = None


@router.post("/{task_id}/comments", status_code=201, response_model=TimelineOut)
def add_comment(
    task_id: uuid.UUID,
    body: CommentBody,
    request: Request,
    principal: CurrentPrincipal,
    db: DbSession,
) -> TimelineOut:
    c = service.add_comment(db, principal, task_id, body.body, client_ip(request))
    return TimelineOut(at=c.created_at, kind="comment", actor=principal.display_name, text=c.body)


@router.get("/{task_id}/timeline", response_model=list[TimelineOut])
def timeline(task_id: uuid.UUID, principal: CurrentPrincipal, db: DbSession) -> list[TimelineOut]:
    return [
        TimelineOut.model_validate(e, from_attributes=True)
        for e in service.timeline(db, principal, task_id)
    ]


assert set(Status.__args__) == set(TASK_STATUSES)  # type: ignore[attr-defined]  # noqa: S101

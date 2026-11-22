"""Audio quality check (AQC-001..010, D-079).

Read-only (AQC-009): the automatic check reads the measurements taken when the delivery file was
made, and a re-check reads a downloaded copy; neither ever changes the audio. The checks
themselves are in rules.py. The automatic result never approves or rejects anything: the QC
Executive assigned to the task decides (PASS or FAIL, D-118). A pass goes to the project admin
for the final approval, or approves the task itself in a project where QC pass is the final
approval (D-138).

The QC Executive answers the project's QC checklist with every decision (D-146, checklist.py),
and in a project that takes signed consent forms checks each person's form. A pass needs every
required answer, none failing and both forms right. When only a form is wrong, SEND_BACK_CONSENT
moves the task to CONSENT_FIX: its moderator uploads a new scan and sends the same recording back
(send_back_to_qc), and QC starts again from the answers given, the consent check cleared.
"""

from __future__ import annotations

import logging
import tempfile
import uuid
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from botocore.exceptions import BotoCoreError, ClientError
from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import AppError, forbidden, not_found
from app.core.permissions import Perm, Role
from app.core.storage import ObjectStorage
from app.modules.audio_qc import checklist
from app.modules.audio_qc.models import AudioQcCheck, AudioQcDraft, AudioQcResult
from app.modules.audio_qc.rules import (
    Check,
    Duplicate,
    Limits,
    Measured,
    Pauses,
    analyze_file,
    comparable,
    evaluate,
    from_asset,
    limits_of,
    outcome_of,
    pauses_of,
    summary,
)
from app.modules.audit import service as audit
from app.modules.auth.deps import Principal
from app.modules.auth.models import User
from app.modules.participants import consent
from app.modules.participants.models import Participant
from app.modules.projects.models import Project, ProjectAudioRule
from app.modules.recordings import access
from app.modules.recordings.models import (
    DELIVERY_KINDS,
    AssetProcessingStep,
    AudioAsset,
    Recording,
    current_recording_of,
    current_recordings,
)
from app.modules.tasks import service as tasks
from app.modules.tasks import workflow
from app.modules.tasks.models import Task
from app.modules.telephony import service as telephony
from app.modules.telephony.models import Call, CallEvent
from app.modules.users.service import display_names

logger = logging.getLogger("app.audio_qc")

# Statuses in which a QC Executive may be (re)assigned: anything still open.
QC_ASSIGNABLE = frozenset(
    {"DRAFT", "ASSIGNED", "IN_PROGRESS", "RECORDED", "AUDIO_QC", "CONSENT_FIX", "ON_HOLD"}
)
# A pass goes to the project admin for the final approval (D-092), or approves the task where the
# project says QC pass is the final approval (D-138). D-118: pass or reject only; no return.
# D-146: or, when only a signed consent form is wrong, back to the moderator for a new one.
SEND_BACK = "SEND_BACK_CONSENT"
CONSENT_FIX = "CONSENT_FIX"
DECISIONS = {"PASS": "ADMIN_REVIEW", "FAIL": "REJECTED", SEND_BACK: CONSENT_FIX}
QC_FINAL_STATUS = "APPROVED"
QC_FINAL_NOTE = "Approved by the QC decision: QC pass is the final approval in this project."


def decision_target(outcome: str, project: Project) -> str | None:
    """The status a QC decision moves the task to; None for an unknown outcome."""
    if outcome == "PASS" and project.qc_final_approval:
        return QC_FINAL_STATUS
    return DECISIONS.get(outcome)


def find_duplicate(
    db: Session, project_id: uuid.UUID, recording_id: uuid.UUID, m: Measured
) -> Duplicate | None:
    """Another recording in the same project with the same file or the same sound (AQC-007)."""
    base = (
        select(AudioAsset.recording_id)
        .where(
            AudioAsset.project_id == project_id,
            AudioAsset.kind.in_(DELIVERY_KINDS),
            AudioAsset.recording_id != recording_id,
            AudioAsset.deleted_at.is_(None),
        )
        .order_by(AudioAsset.created_at)
        .limit(1)
    )
    same_file = db.scalar(base.where(AudioAsset.sha256 == m.sha256))
    if same_file is not None:
        return Duplicate(exact=True, recording_id=same_file)
    if comparable(m):
        same_sound = db.scalar(base.where(AudioAsset.content_fingerprint == m.content_fingerprint))
        if same_sound is not None:
            return Duplicate(exact=False, recording_id=same_sound)
    return None


def delivery_asset(db: Session, recording_id: uuid.UUID) -> AudioAsset | None:
    return db.scalar(
        select(AudioAsset)
        .where(
            AudioAsset.recording_id == recording_id,
            AudioAsset.kind.in_(DELIVERY_KINDS),
            AudioAsset.deleted_at.is_(None),
        )
        .order_by(AudioAsset.version.desc())
        .limit(1)
    )


def _limits_for(db: Session, task: Task) -> Limits | None:
    rule = db.scalar(
        select(ProjectAudioRule).where(
            ProjectAudioRule.project_id == task.project_id,
            ProjectAudioRule.mode == task.recording_mode,
        )
    )
    return limits_of(rule) if rule is not None else None


def _pauses_for(db: Session, task: Task) -> Pauses:
    """The project's pause rule (D-148), as it is now."""
    return pauses_of(db.get_one(Project, task.project_id))


def _store(
    db: Session,
    rec: Recording,
    task: Task,
    asset: AudioAsset | None,
    checks: list[Check],
    measured: Measured | None,
    duplicate: Duplicate | None,
    *,
    requested_by: uuid.UUID | None,
) -> AudioQcResult:
    outcome, reason = outcome_of(checks)
    result = AudioQcResult(
        id=uuid.uuid4(),
        recording_id=rec.id,
        task_id=task.id,
        project_id=task.project_id,
        asset_id=asset.id if asset else None,
        automated=True,
        outcome=outcome,
        reason_code=reason,
        comment=summary(checks),
        reviewer_id=requested_by,
        duration_ms=measured.duration_ms if measured else None,
        silence_pct=measured.silence_pct if measured else None,
        clip_pct=measured.clip_pct if measured else None,
        peak_dbfs=measured.peak_dbfs if measured else None,
        rms_dbfs=measured.rms_dbfs if measured else None,
        dynamic_range_db=measured.dynamic_range_db if measured else None,
        duplicate_of_recording_id=duplicate.recording_id if duplicate else None,
    )
    result.checks = [
        AudioQcCheck(
            position=i,
            code=c.code,
            state=c.state,
            measured=c.measured[:200],
            expected=c.expected[:200],
            message=c.message,
        )
        for i, c in enumerate(checks, start=1)
    ]
    db.add(result)
    audit.record(
        db,
        action="audio_qc.automatic",
        entity_type="recording",
        entity_id=rec.id,
        project_id=task.project_id,
        actor_id=requested_by,
        ip=None,
        after={"outcome": outcome, "reason_code": reason},
    )
    return result


def run_automatic(db: Session, recording_id: uuid.UUID) -> AudioQcResult:
    """Check the newest delivery file of a ready recording; the moderator then sends it on."""
    rec = db.get(Recording, recording_id)
    if rec is None:
        raise not_found("Recording")
    task = db.get_one(Task, rec.task_id)
    asset = delivery_asset(db, rec.id)
    measured = from_asset(asset) if asset is not None else None
    duplicate = find_duplicate(db, task.project_id, rec.id, measured) if measured else None
    checks = evaluate(
        measured, _limits_for(db, task), duplicate=duplicate, pauses=_pauses_for(db, task)
    )
    result = _store(db, rec, task, asset, checks, measured, duplicate, requested_by=None)
    # The task stays with the moderator after the check (D-092): they listen and send it on.
    db.commit()
    return result


def _latest_ready_recording(db: Session, task: Task) -> Recording | None:
    return db.scalar(current_recording_of(task.id))


def _can_manage(principal: Principal, task: Task) -> bool:
    return principal.can_in_project(Perm.TASKS_ASSIGN, task.project_id)


def may_decide(db: Session, principal: Principal, task: Task) -> bool:
    """The caller decides this task's audio QC: its assigned QC Executive (or a Super Admin).
    Also who may look at the task's signed consent forms (D-144, participants/documents.py)."""
    if not principal.can(Perm.AUDIO_QC_REVIEW):
        return False
    if principal.is_super_admin:
        return True
    current = tasks.active_assignee(db, task.id, Role.QC_EXECUTIVE.value)
    return current is not None and current.user_id == principal.user_id


def recheck(
    db: Session,
    storage: ObjectStorage,
    settings: Settings,
    principal: Principal,
    task_id: uuid.UUID,
) -> AudioQcResult:
    """Download the delivery file again and check it from its bytes (also recovers a task whose
    automatic check did not run)."""
    task = tasks.get_task(db, principal, task_id)
    if not (_can_manage(principal, task) or may_decide(db, principal, task)):
        raise forbidden()
    if task.status not in ("RECORDED", "AUDIO_QC"):
        raise AppError(
            "There is no recording waiting for a check", code="TASK_NOT_IN_QC", status_code=409
        )
    rec = _latest_ready_recording(db, task)
    if rec is None:
        raise AppError("There is no finished recording yet", code="NO_RECORDING", status_code=409)
    asset = delivery_asset(db, rec.id)
    measured = decode_error = None
    if asset is not None:
        work = Path(settings.media_work_dir)
        work.mkdir(parents=True, exist_ok=True)
        try:
            with tempfile.TemporaryDirectory(dir=work) as tmp:
                copy = Path(tmp) / "delivery.wav"
                if storage.head(asset.storage_key) is not None:
                    storage.get_to_file(asset.storage_key, copy)
                measured, decode_error = analyze_file(copy)
        except (BotoCoreError, ClientError):
            logger.exception("audio_qc_storage_unavailable", extra={"task_id": str(task.id)})
            raise AppError(
                "File storage is not reachable right now; try again shortly",
                code="STORAGE_UNAVAILABLE",
                status_code=503,
                headers={"Retry-After": "5"},
            ) from None
    duplicate = find_duplicate(db, task.project_id, rec.id, measured) if measured else None
    checks = evaluate(
        measured,
        _limits_for(db, task),
        decode_error=decode_error,
        duplicate=duplicate,
        expected_sha256=asset.sha256 if asset else None,
        pauses=_pauses_for(db, task),
    )
    result = _store(
        db, rec, task, asset, checks, measured, duplicate, requested_by=principal.user_id
    )
    # The task stays with the moderator after the check (D-092): they listen and send it on.
    db.commit()
    return result


def assign_qc(
    db: Session,
    principal: Principal,
    task_id: uuid.UUID,
    user_id: uuid.UUID,
    reason: str | None,
    ip: str | None,
) -> Task:
    task = tasks.get_task(db, principal, task_id)
    if not _can_manage(principal, task):
        raise forbidden()
    if task.status not in QC_ASSIGNABLE:
        raise AppError(
            f"A {task.status} task cannot get a QC Executive", code="TASK_LOCKED", status_code=409
        )
    user = tasks.require_member_with_role(db, task.project_id, user_id, Role.QC_EXECUTIVE)
    if user.id in tasks.recording_people(db, task):
        raise _same_person()
    try:
        tasks.replace_assignee(db, principal, task, user, Role.QC_EXECUTIVE, reason, ip)
        db.commit()
    except Exception:
        db.rollback()
        raise
    return task


def _same_person() -> AppError:
    return AppError(
        "The person who records a session cannot check it", code="SAME_PERSON", status_code=422
    )


def _automatic_of(db: Session, recording_id: uuid.UUID) -> AudioQcResult | None:
    """The newest automatic check of one recording."""
    return db.scalar(
        select(AudioQcResult)
        .where(AudioQcResult.recording_id == recording_id, AudioQcResult.automated.is_(True))
        .order_by(AudioQcResult.created_at.desc())
        .limit(1)
    )


def _sides(db: Session, task: Task, *, forms: bool) -> list[dict[str, Any]]:
    """The task's two participants as a decision keeps them: side, id, code, and (in a project
    that takes signed forms) the id of the consent form on file now."""
    current = (
        consent.signed_forms(db, task.project_id, [task.participant_a_id, task.participant_b_id])
        if forms
        else {}
    )
    out = []
    for side, pid in (("A", task.participant_a_id), ("B", task.participant_b_id)):
        code = db.scalar(select(Participant.participant_code).where(Participant.id == pid))
        form = current.get(pid)
        out.append(
            {
                "side": side,
                "participant_id": pid,
                "participant_code": code,
                "consent_form_id": str(form.id) if form is not None else None,
            }
        )
    return out


def _checklist_error(code: str, message: str, where: list[str]) -> AppError:
    return AppError(message, code=code, status_code=422, details=[{"questions": where}])


def _require_answers(
    items: list[checklist.Item], given: checklist.Answers, codes: Mapping[str, str]
) -> None:
    """Every required question answered (422 CHECKLIST_INCOMPLETE) and none answered so that the
    recording fails (422 CHECKLIST_FAILED), naming them."""
    missing = [checklist.label(i, side, codes) for i, side in checklist.unanswered(items, given)]
    if missing:
        more = f" and {len(missing) - 1} more" if len(missing) > 1 else ""
        raise _checklist_error(
            "CHECKLIST_INCOMPLETE",
            f"Answer every question of the checklist first: {missing[0]}{more}.",
            missing,
        )
    failed = [checklist.label(f.item, f.side, codes) for f in checklist.failing(items, given)]
    if failed:
        raise _checklist_error(
            "CHECKLIST_FAILED",
            f"The recording fails the checklist ({failed[0]}): reject it instead.",
            failed,
        )


def _consent_rules(
    outcome: str, uploads: bool, given: checklist.Answers, codes: Mapping[str, str], comment: str
) -> list[str]:
    """The consent check of a decision (D-146); returns the codes of the people whose form is not
    right. Pass: both forms checked and right. Send back: at least one form marked not right, and
    what is wrong with it in the comment."""
    wrong = [codes[s] for s in checklist.SIDES if given.consent.get(s) == "no"]
    if outcome == "PASS" and uploads:
        unchecked = [codes[s] for s in checklist.SIDES if given.consent.get(s) is None]
        if unchecked:
            raise AppError(
                f"Check the signed consent form of {' and '.join(unchecked)} first.",
                code="CONSENT_NOT_CHECKED",
                status_code=422,
            )
        if wrong:
            raise AppError(
                f"The signed consent form of {' and '.join(wrong)} is not right: send the task "
                "back for its consent form instead.",
                code="CONSENT_NOT_OK",
                status_code=422,
            )
    if outcome == SEND_BACK:
        if not wrong:
            raise AppError(
                "Mark No for the consent form that is not right first.",
                code="CONSENT_NOT_MARKED",
                status_code=422,
            )
        if not comment:
            raise AppError(
                "Say what is wrong with the consent form.",
                code="COMMENT_REQUIRED",
                status_code=422,
            )
    return wrong


def _draft_of(db: Session, task_id: uuid.UUID) -> AudioQcDraft | None:
    return db.scalar(select(AudioQcDraft).where(AudioQcDraft.task_id == task_id))


def _write_draft(
    db: Session, task_id: uuid.UUID, answers: checklist.Answers, saved_by: uuid.UUID | None
) -> AudioQcDraft:
    draft = _draft_of(db, task_id)
    if draft is None:
        draft = AudioQcDraft(task_id=task_id, answers={})
        db.add(draft)
    draft.answers = answers.as_dict()
    draft.saved_by = saved_by
    return draft


def decide(
    db: Session,
    principal: Principal,
    task_id: uuid.UUID,
    outcome: str,
    reason_code: str | None,
    comment: str,
    ip: str | None,
    answers: Mapping[str, Any] | None = None,
) -> AudioQcResult:
    """The QC Executive's decision (AQC-008) with the QC checklist's answers (D-146): PASS sends
    the task to the project admin, or approves it where QC pass is the final approval (D-138);
    FAIL rejects it (D-118: no return); SEND_BACK_CONSENT sends it to its moderator for a new
    signed consent form. Stored with the answers, reason, comment, time and reviewer; the task
    moves in the same commit."""
    task = tasks.get_task(db, principal, task_id)
    if not may_decide(db, principal, task):
        raise forbidden()
    # Locked and read again (TASK-05, FOR NO KEY UPDATE as tasks.transition takes): of two
    # decisions sent at once, the second waits for the first and is told the task has moved on,
    # before anything of it is written.
    tasks.lock_task(db, task)
    if task.status != "AUDIO_QC":
        raise AppError(
            "This task is not waiting for an audio check", code="TASK_NOT_IN_QC", status_code=409
        )
    # Checked at decision time too, for every caller including a Super Admin: assigning the QC
    # first and the moderator second used to let one person record and approve (D-088).
    if principal.user_id in tasks.recording_people(db, task):
        raise _same_person()
    project = db.get_one(Project, task.project_id)
    target = decision_target(outcome, project)
    if target is None:
        raise AppError(
            "Choose PASS, FAIL or SEND_BACK_CONSENT", code="VALIDATION_ERROR", status_code=422
        )
    uploads = consent.takes_uploads(project)
    if outcome == SEND_BACK and not uploads:
        raise AppError(
            "This project takes consent online: there is no signed consent form to send back.",
            code="CONSENT_ONLINE",
            status_code=409,
        )
    if outcome == "PASS":
        # Nothing passes QC (or is approved by the pass, D-138) without both people's consent as
        # it counts now: in a project switched to Online, a signed form no longer counts (SECB-03).
        tasks.require_consent(db, task)
    # The decision is about the task's current recording, the one QC listens to and an export
    # delivers (D-135), and uses that recording's own automatic check (TASK-06).
    rec = _latest_ready_recording(db, task)
    automatic = _automatic_of(db, rec.id) if rec is not None else None
    if rec is None or automatic is None:
        raise AppError("Run the automatic check first", code="NO_AUTOMATIC_CHECK", status_code=409)
    comment = comment.strip()
    items = checklist.items_of(project.qc_checklist)
    given = checklist.Answers.read(answers).only(items, consent_check=uploads)
    sides = _sides(db, task, forms=uploads)
    codes = {p["side"]: p["participant_code"] for p in sides}
    if outcome in ("PASS", SEND_BACK):
        reason_code = None
        _require_answers(items, given, codes)
    to_fix = _consent_rules(outcome, uploads, given, codes, comment)
    if outcome == "PASS" and automatic.outcome == "FAIL" and not comment:
        raise AppError(
            "The automatic check failed: say why it passes anyway",
            code="COMMENT_REQUIRED",
            status_code=422,
        )
    workflow.check(
        task.status,
        target,
        workflow.SYSTEM,
        held_from=task.held_from,
        reason_code=reason_code,
        comment=comment,
    )
    snapshot = checklist.snapshot(items, given, sides, consent_check=uploads)
    result = AudioQcResult(
        id=uuid.uuid4(),
        recording_id=rec.id,
        task_id=task.id,
        project_id=task.project_id,
        asset_id=automatic.asset_id,
        automated=False,
        outcome=outcome,
        reason_code=reason_code,
        comment=comment,
        reviewer_id=principal.user_id,
        duration_ms=automatic.duration_ms,
        silence_pct=automatic.silence_pct,
        clip_pct=automatic.clip_pct,
        peak_dbfs=automatic.peak_dbfs,
        rms_dbfs=automatic.rms_dbfs,
        dynamic_range_db=automatic.dynamic_range_db,
        duplicate_of_recording_id=automatic.duplicate_of_recording_id,
        checklist=snapshot,
    )
    db.add(result)
    after: dict[str, Any] = {
        "outcome": outcome,
        "reason_code": reason_code,
        "task_status": target,
        "failing": [
            f"{f['side']}:{f['key']}" if f["side"] else f["key"] for f in snapshot["failing"]
        ],
    }
    if outcome == SEND_BACK:
        after["consent_to_fix"] = to_fix
    audit.record(
        db,
        action="audio_qc.decision",
        entity_type="recording",
        entity_id=rec.id,
        project_id=task.project_id,
        actor_id=principal.user_id,
        ip=ip,
        after=after,
    )
    draft = _draft_of(db, task.id)
    if outcome == SEND_BACK:
        # QC starts the next check from these answers; only the consent check is asked again.
        _write_draft(db, task.id, given.without_consent(), None)
    elif draft is not None:
        db.delete(draft)
    db.flush()
    note = comment or f"Audio QC: {outcome}"
    if target == QC_FINAL_STATUS:
        note = f"{QC_FINAL_NOTE} {comment}".strip()
    elif outcome == SEND_BACK:
        note = f"Consent form to fix: {' and '.join(to_fix)}. {comment}"
    tasks.transition(
        db,
        task,
        target,
        workflow.SYSTEM,
        actor_id=principal.user_id,
        reason_code=reason_code,
        comment=note,
    )
    return result


def _latest_checked(db: Session, task_id: uuid.UUID) -> AudioQcResult | None:
    """The task's newest decision that has checklist answers (D-146)."""
    return db.scalar(
        select(AudioQcResult)
        .where(
            AudioQcResult.task_id == task_id,
            AudioQcResult.automated.is_(False),
            AudioQcResult.checklist.is_not(None),
        )
        .order_by(AudioQcResult.created_at.desc())
        .limit(1)
    )


def checklist_view(db: Session, principal: Principal, task_id: uuid.UUID) -> dict[str, Any]:
    """The project's QC checklist for this task, the answers not yet sent (for whoever decides
    its QC) and the newest decision's answers (for everyone who sees the task), D-146."""
    task = tasks.get_task(db, principal, task_id)
    project = db.get_one(Project, task.project_id)
    items = checklist.items_of(project.qc_checklist)
    uploads = consent.takes_uploads(project)
    deciding = may_decide(db, principal, task)
    draft = _draft_of(db, task.id) if deciding else None
    latest = _latest_checked(db, task.id)
    names = display_names(
        db, [draft.saved_by if draft else None, latest.reviewer_id if latest else None]
    )
    saved = (
        None
        if draft is None
        else {
            "answers": checklist.Answers.read(draft.answers)
            .only(items, consent_check=uploads)
            .as_dict(),
            "saved_at": draft.updated_at,
            "saved_by_name": names.get(draft.saved_by) if draft.saved_by else None,
        }
    )
    recorded = (
        None
        if latest is None or latest.checklist is None
        else {
            "outcome": latest.outcome,
            "reason_code": latest.reason_code,
            "comment": latest.comment,
            "reviewer_name": names.get(latest.reviewer_id) if latest.reviewer_id else None,
            "decided_at": latest.created_at,
            **latest.checklist,
        }
    )
    return {
        "items": [i.as_dict() for i in items],
        "consent_check": uploads,
        "consent_question": checklist.CONSENT_QUESTION,
        "can_answer": deciding and task.status == "AUDIO_QC",
        "draft": saved,
        "latest": recorded,
    }


def save_draft(
    db: Session, principal: Principal, task_id: uuid.UUID, answers: Mapping[str, Any]
) -> AudioQcDraft:
    """Keeps the QC Executive's answers while they tick (D-146): one per task, replaced on each
    save; only the person who decides the task's QC, while it waits for the decision."""
    task = tasks.get_task(db, principal, task_id)
    if not may_decide(db, principal, task):
        raise forbidden()
    if task.status != "AUDIO_QC":
        raise AppError(
            "This task is not waiting for an audio check", code="TASK_NOT_IN_QC", status_code=409
        )
    project = db.get_one(Project, task.project_id)
    items = checklist.items_of(project.qc_checklist)
    uploads = consent.takes_uploads(project)
    given = checklist.Answers.read(answers).only(items, consent_check=uploads)
    draft = _write_draft(db, task.id, given, principal.user_id)
    db.commit()
    return draft


def _consent_fix(
    db: Session, task: Task
) -> tuple[AudioQcResult | None, list[dict[str, Any]], bool]:
    """The newest send-back of the task, the people whose consent form it found not right, and
    whether the project takes signed forms now. Each person has `replaced`: where the project
    takes signed forms, a new form is on file since (D-146); in a project switched to Online
    since, they have agreed online, the only consent that counts there now (SECB-03)."""
    sent = db.scalar(
        select(AudioQcResult)
        .where(AudioQcResult.task_id == task.id, AudioQcResult.outcome == SEND_BACK)
        .order_by(AudioQcResult.created_at.desc())
        .limit(1)
    )
    project = db.get_one(Project, task.project_id)
    uploads = consent.takes_uploads(project)
    if sent is None:
        return None, [], uploads
    wrong = [p for p in (sent.checklist or {}).get("participants", []) if p.get("consent") == "no"]
    ids = [uuid.UUID(p["participant_id"]) for p in wrong]
    current = consent.signed_forms(db, task.project_id, ids) if uploads else {}
    online = {} if uploads else consent.standings(db, project, ids)
    people = []
    for p in wrong:
        pid = uuid.UUID(p["participant_id"])
        form = current.get(pid)
        if uploads:
            replaced = form is not None and str(form.id) != p.get("consent_form_id")
        else:
            replaced = online[pid].consented
        people.append(
            {
                "side": p["side"],
                "participant_id": p["participant_id"],
                "participant_code": p["participant_code"],
                "replaced": replaced,
                "form_id": str(form.id) if form is not None else None,
            }
        )
    return sent, people, uploads


def consent_fix_view(db: Session, principal: Principal, task: Task) -> dict[str, Any] | None:
    """What the task page shows while a consent form is being fixed (D-146): QC's comment, whose
    form, whether a new one is on file, and whether the caller may send the task back to QC.
    `by_upload` false: the project switched to Online since, and `replaced` means the person has
    agreed online (SECB-03)."""
    if task.status != CONSENT_FIX:
        return None
    sent, people, uploads = _consent_fix(db, task)
    if sent is None:
        return None
    actor = tasks.actor_for(db, principal, task)
    names = display_names(db, [sent.reviewer_id])
    return {
        "comment": sent.comment,
        "by": names.get(sent.reviewer_id) if sent.reviewer_id else None,
        "at": sent.created_at,
        "participants": [
            {k: p[k] for k in ("side", "participant_id", "participant_code", "replaced")}
            for p in people
        ],
        "forms_replaced": all(p["replaced"] for p in people),
        "by_upload": uploads,
        "can_send_back": actor.is_moderator or actor.can_assign,
    }


def send_back_to_qc(
    db: Session, principal: Principal, task_id: uuid.UUID, comment: str, ip: str | None
) -> Task:
    """The moderator (or a project admin) sends the task back to QC once every consent form QC
    found not right was replaced (D-146): the same recording, the same QC Executive; QC's earlier
    answers wait for them with the consent check cleared."""
    task = tasks.get_task(db, principal, task_id)
    tasks.lock_task(db, task)  # one send-back at a time (TASK-05)
    if task.status != CONSENT_FIX:
        raise AppError(
            "This task is not waiting for a consent form",
            code="TASK_NOT_IN_CONSENT_FIX",
            status_code=409,
        )
    actor = tasks.actor_for(db, principal, task)
    comment = comment.strip()
    workflow.check(
        task.status, "AUDIO_QC", actor, held_from=task.held_from, reason_code=None, comment=comment
    )
    sent, people, uploads = _consent_fix(db, task)
    if sent is None:
        raise AppError(
            "QC's request for a new consent form was not found: ask your admin.",
            code="CONSENT_FIX_UNKNOWN",
            status_code=409,
        )
    waiting = [p["participant_code"] for p in people if not p["replaced"]]
    if waiting:
        who = " and ".join(waiting)
        raise AppError(
            f"Upload a new signed consent form for {who} first: QC found a problem with the one "
            "on file."
            if uploads
            else f"Participant {who} has not agreed on the consent form online yet. This "
            "project now takes consent online, so a signed form no longer counts.",
            code="CONSENT_FORM_NOT_REPLACED",
            status_code=409,
            details=[{"participants": waiting}],
        )
    audit.record(
        db,
        action="audio_qc.consent_fixed",
        entity_type="task",
        entity_id=task.id,
        project_id=task.project_id,
        actor_id=principal.user_id,
        ip=ip,
        after={
            "participants": [p["participant_code"] for p in people],
            "forms": [p["form_id"] for p in people],
            "send_back": str(sent.id),
        },
    )
    return tasks.transition(
        db,
        task,
        "AUDIO_QC",
        actor,
        actor_id=principal.user_id,
        comment=comment or "New signed consent form uploaded: the same recording goes back to QC.",
        ip=ip,
    )


def results_for(db: Session, task_id: uuid.UUID) -> list[AudioQcResult]:
    return list(
        db.scalars(
            select(AudioQcResult)
            .where(AudioQcResult.task_id == task_id)
            .order_by(AudioQcResult.created_at.desc())
            .limit(50)
        ).all()
    )


def view(db: Session, principal: Principal, task_id: uuid.UUID) -> dict[str, Any]:
    task = tasks.get_task(db, principal, task_id)
    qc = tasks.active_assignee(db, task.id, Role.QC_EXECUTIVE.value)
    qc_user = db.get(User, qc.user_id) if qc else None
    # Automatic checks of the current recording only: the one QC listens to and decides on
    # (TASK-06, D-135). Decisions stay, whichever recording they were about.
    current = access.current_id(db, task.id)
    results = [r for r in results_for(db, task.id) if not r.automated or r.recording_id == current]
    reviewers = (
        {
            u.id: u.display_name
            for u in db.scalars(
                select(User).where(User.id.in_({r.reviewer_id for r in results if r.reviewer_id}))
            ).all()
        }
        if results
        else {}
    )
    is_qc = may_decide(db, principal, task)
    can_manage = _can_manage(principal, task)
    project = db.get_one(Project, task.project_id)
    return {
        "task_status": task.status,
        "pass_approves": project.qc_final_approval,
        "qc_user_id": qc_user.id if qc_user else None,
        "qc_name": qc_user.display_name if qc_user else None,
        "can_decide": is_qc and task.status == "AUDIO_QC",
        "can_assign": can_manage and task.status in QC_ASSIGNABLE,
        "can_recheck": (is_qc or can_manage) and task.status in ("RECORDED", "AUDIO_QC"),
        "reasons": {
            "FAIL": sorted(workflow.REASONS["REJECTED"]),
        },
        "results": [
            {
                "id": r.id,
                "recording_id": r.recording_id,
                "asset_id": r.asset_id,
                "automated": r.automated,
                "outcome": r.outcome,
                "reason_code": r.reason_code,
                "comment": r.comment,
                "reviewer_name": reviewers.get(r.reviewer_id) if r.reviewer_id else None,
                "created_at": r.created_at,
                "duration_ms": r.duration_ms,
                "silence_pct": r.silence_pct,
                "clip_pct": r.clip_pct,
                "peak_dbfs": r.peak_dbfs,
                "rms_dbfs": r.rms_dbfs,
                "dynamic_range_db": r.dynamic_range_db,
                "duplicate_of_recording_id": r.duplicate_of_recording_id,
                "checks": [
                    {
                        "code": c.code,
                        "state": c.state,
                        "measured": c.measured,
                        "expected": c.expected,
                        "message": c.message,
                    }
                    for c in r.checks
                ],
            }
            for r in results
        ],
    }


def _iso(value: datetime | None) -> str | None:
    return value.astimezone(UTC).isoformat() if value else None


def metadata(
    db: Session, principal: Principal, recording_id: uuid.UUID, ip: str | None
) -> tuple[str, dict[str, Any]]:
    """The details file that travels with a recording: session, device, every file with its
    measurements and processing, consent status and audio QC. Participants by code only."""
    rec, task = access.readable(db, principal, recording_id)
    if not principal.can_in_project(Perm.RECORDINGS_DOWNLOAD, task.project_id):
        raise forbidden()
    project = db.get_one(Project, task.project_id)
    body = metadata_body(db, rec, task, project)
    audit.record(
        db,
        action="recording.metadata_download",
        entity_type="recording",
        entity_id=rec.id,
        project_id=task.project_id,
        actor_id=principal.user_id,
        ip=ip,
    )
    db.commit()
    return f"metadata_{task.task_code}_{rec.id}.json", body


def metadata_body(db: Session, rec: Recording, task: Task, project: Project) -> dict[str, Any]:
    """The details file's content, for a caller that has already checked access (D-094)."""
    assets = db.scalars(
        select(AudioAsset)
        .where(AudioAsset.recording_id == rec.id, AudioAsset.deleted_at.is_(None))
        .order_by(AudioAsset.kind, AudioAsset.version)
    ).all()
    steps = (
        db.scalars(
            select(AssetProcessingStep)
            .where(AssetProcessingStep.asset_id.in_([a.id for a in assets]))
            .order_by(AssetProcessingStep.seq)
        ).all()
        if assets
        else []
    )
    by_asset: dict[uuid.UUID, list[AssetProcessingStep]] = {}
    for step in steps:
        by_asset.setdefault(step.asset_id, []).append(step)
    people = []
    for side in consent.for_task(db, task):
        participant = db.get_one(Participant, side.participant_id)
        # The consent that counts is the answer on the form (D-129), or UPLOADED for a signed
        # form uploaded where the project takes uploads (D-144); a session consent was noted by
        # the moderator only before D-129.
        session, own = side.latest_noted, side.latest_own
        by_answer = side.form is None and side.status is not None
        people.append(
            {
                "slot": side.side,
                "participant_code": participant.participant_code,
                "language": participant.language_code,
                "session_consent": session.status if session else None,
                "session_consent_at": _iso(session.created_at) if session else None,
                "session_consent_method": session.method if session else None,
                "consent_form_answer": side.status,
                "consent_form_version": own.policy_version if own and by_answer else None,
            }
        )
    results = [r for r in results_for(db, task.id) if r.recording_id == rec.id]
    automatic = next((r for r in results if r.automated), None)
    decision = next((r for r in results if not r.automated), None)
    body: dict[str, Any] = {
        "format": "ccp.recording-metadata/1",
        "generated_at": _iso(datetime.now(UTC)),
        "project": {"code": project.code, "name": project.name},
        "session": {
            "task_code": task.task_code,
            "recording_mode": task.recording_mode,
            "status": task.status,
        },
        "participants": people,
        "recording": {
            "id": str(rec.id),
            "state": rec.state,
            "started_at": _iso(rec.started_at),
            "ended_at": _iso(rec.ended_at),
            "native_sample_rate": rec.native_sample_rate,
            "channel_count": rec.channel_count,
            "device_channel_count": rec.device_channel_count,
            "channel_handling": rec.channel_handling,
            "echo_cancellation": rec.echo_cancellation,
            "noise_suppression": rec.noise_suppression,
            "auto_gain_control": rec.auto_gain_control,
            "device_label": rec.device_label,
            "user_agent": rec.user_agent,
            "parts_received": rec.chunks_received,
            "interrupted": rec.interrupted,
            "interruption_reason": rec.interruption_reason,
        },
        "files": [
            {
                "id": str(a.id),
                "kind": a.kind,
                "version": a.version,
                "derived_from": str(a.parent_asset_id) if a.parent_asset_id else None,
                "container": a.container,
                "codec": a.codec,
                "sample_format": a.sample_format,
                "sample_rate": a.sample_rate,
                "bit_depth": a.bit_depth,
                "channels": a.channels,
                "duration_ms": a.duration_ms,
                "size_bytes": a.size_bytes,
                "sha256": a.sha256,
                "peak_dbfs": a.peak_dbfs,
                "rms_dbfs": a.rms_dbfs,
                "clip_count": a.clip_count,
                "clip_pct": a.clip_pct,
                "silence_pct": a.silence_pct,
                "dynamic_range_db": a.dynamic_range_db,
                "content_fingerprint": a.content_fingerprint,
                # Effective speech and the longest pause inside it (D-148); null until measured.
                "effective_ms": a.effective_ms,
                "longest_pause_ms": a.longest_pause_ms,
                "created_at": _iso(a.created_at),
                "processing": [
                    {
                        "tool": s.tool,
                        "tool_version": s.tool_version,
                        "parameters": s.parameters,
                        "input_sha256": s.input_sha256,
                        "output_sha256": s.output_sha256,
                    }
                    for s in by_asset.get(a.id, [])
                ],
            }
            for a in assets
        ],
        "audio_qc": {
            "automatic": None
            if automatic is None
            else {
                "outcome": automatic.outcome,
                "reason_code": automatic.reason_code,
                "summary": automatic.comment,
                "checked_at": _iso(automatic.created_at),
                "checks": [
                    {
                        "code": c.code,
                        "state": c.state,
                        "measured": c.measured,
                        "expected": c.expected,
                        "message": c.message,
                    }
                    for c in automatic.checks
                ],
            },
            "decision": None
            if decision is None
            else {
                "outcome": decision.outcome,
                "reason_code": decision.reason_code,
                "comment": decision.comment,
                "reviewer_id": str(decision.reviewer_id) if decision.reviewer_id else None,
                "decided_at": _iso(decision.created_at),
            },
        },
    }
    if rec.mode == "TELEPHONY":
        body["call"] = _call_details(db, rec)
    return body


def _call_details(db: Session, rec: Recording) -> dict[str, Any] | None:
    """The phone call a recording came from, for its details file (D-103): who called from which
    seat and when, what the moderator confirmed on the call, and every step until the file was
    stored. No phone number: the last two digits only."""
    call = db.scalar(select(Call).where(Call.recording_id == rec.id))
    if call is None:
        return None
    moderator = db.get(User, call.moderator_id)
    events = db.scalars(
        select(CallEvent).where(CallEvent.call_id == call.id).order_by(CallEvent.created_at)
    ).all()
    actors = display_names(db, (e.actor_id for e in events))
    return {
        "id": str(call.id),
        "provider": call.provider,
        "provider_reference": call.provider_reference,
        "provider_call": telephony.mask(call.provider_session_id or "") or None,
        "agent_seat": call.agent_id,
        "moderator": moderator.display_name if moderator else None,
        "number_ends_in": call.phone_hint,
        "dialled_at": _iso(call.dialled_at),
        "closed_at": _iso(call.closed_at),
        # The conversation as the moderator marked it; the delivery file is cut to it (D-113).
        "recording_started_at": _iso(call.record_started_at),
        "recording_stopped_at": _iso(call.record_stopped_at),
        "note": call.note,
        "checklist": {
            item: telephony.checklist_of(call).get(item)
            for item in ("A_JOINED", "B_JOINED", "MODERATOR_MUTED", "QUALITY_OK")
        },
        "history": [
            {
                "at": _iso(e.created_at),
                "kind": e.kind,
                "by": actors.get(e.actor_id) if e.actor_id else None,
                "text": e.detail,
            }
            for e in events
        ],
    }


def ensure_checked(db: Session, task: Task) -> None:
    """The newest finished recording has its automatic check, so QC has something to read."""
    rec = _latest_ready_recording(db, task)
    checked = rec is not None and db.scalar(
        select(AudioQcResult.id).where(
            AudioQcResult.recording_id == rec.id, AudioQcResult.automated.is_(True)
        )
    )
    if not checked:
        raise AppError(
            "The automatic sound check is still running. Try again in a minute.",
            code="CHECK_PENDING",
            status_code=409,
        )


def pending_automatic(db: Session, limit: int = 50) -> list[uuid.UUID]:
    """The current recording of each task at RECORDED when it has no automatic check yet: the
    process stopped in between. The recovery sweep checks them. (A task now waits at RECORDED for
    its moderator, D-092, so a checked recording must not be checked again on every sweep.) A
    replaced recording is never checked: QC never sees it (TASK-06, D-135)."""
    current = current_recordings(select(Task.id).where(Task.status == "RECORDED"))
    checked = exists().where(
        AudioQcResult.recording_id == current.c.recording_id, AudioQcResult.automated.is_(True)
    )
    return list(
        db.scalars(
            select(current.c.recording_id)
            .where(~checked)
            .order_by(current.c.started_at)
            .limit(limit)
        ).all()
    )

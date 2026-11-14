"""Export bundles made in the background (EXP-009, EXP-010, D-105).

A person asks for a bundle; a row in `export_jobs` keeps what they chose and how far it is. A
worker (or, without one, this process after the answer is sent) claims the row, writes the bundle
straight into storage, and marks it READY with its size and checksum. A READY bundle is handed out
through a short-lived link, each one audited, until the bundle expires; then it is removed from
storage. A job that stopped half-way is found by the sweep and tried again, three times at most.
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import AppError
from app.core.storage import ObjectStorage
from app.modules.audit import service as audit
from app.modules.auth.deps import Principal
from app.modules.auth.models import User
from app.modules.auth.security import FieldCipher
from app.modules.exports import bundle
from app.modules.exports.models import OPEN_STATES, ExportJob
from app.modules.projects.models import Project
from app.modules.projects.service import get_visible as get_visible_project
from app.modules.projects.service import not_found

logger = logging.getLogger("app.exports")

MAX_OPEN_PER_PROJECT = 3
MAX_ATTEMPTS = 3
HEARTBEAT_SECONDS = 30  # how often a running export says it is still alive


@dataclass(frozen=True)
class Listed:
    job: ExportJob
    requested_by: str | None


def _conflict(message: str, code: str) -> AppError:
    return AppError(message, code=code, status_code=409)


def _project(db: Session, principal: Principal, project_id: uuid.UUID) -> Project:
    return get_visible_project(db, principal, project_id)


def create(
    db: Session,
    settings: Settings,
    principal: Principal,
    project_id: uuid.UUID,
    sel: bundle.Selection,
    ip: str | None,
) -> ExportJob:
    project = _project(db, principal, project_id)
    bundle.check(db, principal, project, sel)
    entries = bundle.select_entries(db, project, sel, settings.report_timezone)
    if not entries:
        raise AppError(
            "Nothing to export: no recording fits this choice",
            code="NOTHING_TO_EXPORT",
            status_code=422,
        )
    open_jobs = db.scalar(
        select(func.count())
        .select_from(ExportJob)
        .where(ExportJob.project_id == project.id, ExportJob.state.in_(OPEN_STATES))
    )
    if (open_jobs or 0) >= MAX_OPEN_PER_PROJECT:
        raise _conflict(
            "This project already has exports being prepared; wait for one to finish",
            "TOO_MANY_EXPORTS",
        )
    job = ExportJob(
        project_id=project.id,
        requested_by=principal.user_id,
        content=sel.content,
        scope=sel.scope,
        table_format=sel.table_format,
        filters=sel.as_filters(),
        state="QUEUED",
        file_name=bundle.file_name(project, sel),
        recordings=len(entries),
    )
    db.add(job)
    db.flush()
    audit.record(
        db,
        action="export.requested",
        entity_type="export_job",
        entity_id=job.id,
        project_id=project.id,
        actor_id=principal.user_id,
        ip=ip,
        after={**sel.as_filters(), "recordings": len(entries)},
    )
    db.commit()
    return job


def _names(db: Session, jobs: list[ExportJob]) -> dict[uuid.UUID, str]:
    ids = {j.requested_by for j in jobs}
    if not ids:
        return {}
    return {
        uid: name
        for uid, name in db.execute(select(User.id, User.display_name).where(User.id.in_(ids)))
    }


def list_jobs(
    db: Session, principal: Principal, project_id: uuid.UUID, page: int, page_size: int
) -> tuple[list[Listed], int]:
    project = _project(db, principal, project_id)
    bundle.check(db, principal, project, bundle.Selection())  # may this person export at all
    total = int(
        db.scalar(
            select(func.count()).select_from(ExportJob).where(ExportJob.project_id == project.id)
        )
        or 0
    )
    jobs = list(
        db.scalars(
            select(ExportJob)
            .where(ExportJob.project_id == project.id)
            .order_by(ExportJob.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    )
    names = _names(db, jobs)
    return [Listed(j, names.get(j.requested_by)) for j in jobs], total


def get(db: Session, principal: Principal, project_id: uuid.UUID, job_id: uuid.UUID) -> Listed:
    project = _project(db, principal, project_id)
    bundle.check(db, principal, project, bundle.Selection())
    job = db.get(ExportJob, job_id)
    if job is None or job.project_id != project.id:
        raise not_found()
    return Listed(job, _names(db, [job]).get(job.requested_by))


def download_link(
    db: Session,
    settings: Settings,
    storage: ObjectStorage,
    principal: Principal,
    project_id: uuid.UUID,
    job_id: uuid.UUID,
    ip: str | None,
) -> tuple[str, int, ExportJob]:
    """A link to the bundle that works for a few minutes (EXP-010). The person must be allowed
    to ask for this very selection: a bundle with original files or personal data is not handed
    to someone who could not have made it."""
    project = _project(db, principal, project_id)
    job = db.get(ExportJob, job_id)
    if job is None or job.project_id != project.id:
        raise not_found()
    bundle.check(db, principal, project, bundle.Selection.from_filters(job.filters))
    now = datetime.now(UTC)
    if job.state != "READY" or job.storage_key is None:
        raise _conflict("This export is not ready to download", "EXPORT_NOT_READY")
    if job.expires_at is not None and job.expires_at <= now:
        raise _conflict("This export has expired; make it again", "EXPORT_EXPIRED")
    seconds = settings.signed_url_seconds
    url = storage.signed_get_url(job.storage_key, seconds=seconds, download_name=job.file_name)
    job.downloads += 1
    job.last_downloaded_at = now
    audit.record(
        db,
        action="export.download_link",
        entity_type="export_job",
        entity_id=job.id,
        project_id=project.id,
        actor_id=principal.user_id,
        ip=ip,
        after={"file_name": job.file_name, "sha256": job.sha256, "valid_seconds": seconds},
    )
    db.commit()
    return url, seconds, job


def remove(
    db: Session,
    storage: ObjectStorage | None,
    principal: Principal,
    project_id: uuid.UUID,
    job_id: uuid.UUID,
    ip: str | None,
) -> ExportJob:
    """Takes a bundle out of storage before its time, or withdraws one not yet started."""
    project = _project(db, principal, project_id)
    bundle.check(db, principal, project, bundle.Selection())
    job = db.scalar(select(ExportJob).where(ExportJob.id == job_id).with_for_update())
    if job is None or job.project_id != project.id:
        raise not_found()
    if job.state == "RUNNING":
        raise _conflict("This export is being made; remove it when it is ready", "EXPORT_RUNNING")
    if job.state not in ("READY", "QUEUED"):
        raise _conflict("This export has no bundle to remove", "EXPORT_NOT_READY")
    _expire(db, storage, job)
    audit.record(
        db,
        action="export.removed",
        entity_type="export_job",
        entity_id=job.id,
        project_id=project.id,
        actor_id=principal.user_id,
        ip=ip,
        after={"file_name": job.file_name},
    )
    db.commit()
    return job


def _expire(db: Session, storage: ObjectStorage | None, job: ExportJob) -> None:
    if job.storage_key and storage is not None:
        storage.delete(job.storage_key)
    job.storage_key = None
    job.state = "EXPIRED"
    job.expires_at = job.expires_at or datetime.now(UTC)


# ---------------------------------------------------------------- making the bundle


def run(
    db: Session,
    settings: Settings,
    storage: ObjectStorage | None,
    cipher: FieldCipher | None,
    job_id: uuid.UUID,
) -> str | None:
    """Makes one bundle; returns the job's state afterwards, or None when another worker has it
    (or it is not waiting any more)."""
    now = datetime.now(UTC)
    claimed = db.execute(
        update(ExportJob)
        .where(ExportJob.id == job_id, ExportJob.state == "QUEUED")
        .values(state="RUNNING", claimed_at=now, attempts=ExportJob.attempts + 1, error=None)
        .returning(ExportJob.id)
    ).first()
    db.commit()
    if claimed is None:
        return None
    job = db.get(ExportJob, job_id)
    assert job is not None  # noqa: S101
    # Each try writes its own object: a try that was given up cannot spoil the next one's file.
    attempt = job.attempts
    key = f"exports/{job.project_id}/{job.id}-{attempt}.zip"
    mine = (ExportJob.id == job_id, ExportJob.state == "RUNNING", ExportJob.attempts == attempt)
    last_beat = time.monotonic()

    def still_alive() -> None:
        """A long export keeps its claim fresh, so the sweep never takes it for a stopped one."""
        nonlocal last_beat
        if time.monotonic() - last_beat < HEARTBEAT_SECONDS:
            return
        last_beat = time.monotonic()
        db.execute(update(ExportJob).where(*mine).values(claimed_at=datetime.now(UTC)))
        db.commit()

    try:
        if storage is None:
            raise bundle.BundleError("File storage is not configured")
        project = db.get(Project, job.project_id)
        if project is None:
            raise bundle.BundleError("The project is no longer there")
        sel = bundle.Selection.from_filters(job.filters)
        entries = bundle.select_entries(db, project, sel, settings.report_timezone)
        if not entries:
            raise bundle.BundleError("No recording fits this choice any more")
        requester = db.get(User, job.requested_by)
        made = bundle.Bundle(
            db=db,
            storage=storage,
            cipher=cipher,
            project=project,
            selection=sel,
            entries=entries,
            export_id=str(job.id),
            requested_by=requester.display_name if requester else "",
            on_entry=still_alive,
        )
        size, digest = storage.put_stream(key, made.parts(), content_type="application/zip")
    except Exception as exc:
        db.rollback()
        # What a person may read: the reason when we know it, never a path or a provider answer.
        reason = str(exc) if isinstance(exc, bundle.BundleError | AppError) else None
        if reason is None:
            logger.exception("export_failed", extra={"export_id": str(job_id)})
        _cleanup(storage, key)
        failed = db.scalar(select(ExportJob).where(ExportJob.id == job_id).with_for_update())
        assert failed is not None  # noqa: S101
        if failed.state != "RUNNING" or failed.attempts != attempt:
            db.commit()  # another try has the job now: its outcome is not this one's to write
            return failed.state
        failed.state = "FAILED"
        failed.error = reason or "The export could not be made. Try again."
        failed.finished_at = datetime.now(UTC)
        db.commit()
        return "FAILED"
    done = db.scalar(select(ExportJob).where(ExportJob.id == job_id).with_for_update())
    assert done is not None  # noqa: S101
    if done.state != "RUNNING" or done.attempts != attempt:
        # Taken back while it was made (the sweep found it stale): leave nothing behind.
        _cleanup(storage, key)
        db.commit()
        return done.state
    finished = datetime.now(UTC)
    done.state = "READY"
    done.storage_key = key
    done.sha256 = digest
    done.size_bytes = size
    done.recordings = made.recordings
    done.files = len(made.written) + 1  # and SHA256SUMS
    done.finished_at = finished
    done.expires_at = finished + timedelta(hours=settings.export_bundle_hours)
    db.commit()
    logger.info(
        "export_ready",
        extra={"export_id": str(job_id), "recordings": made.recordings, "bytes": size},
    )
    return "READY"


def _cleanup(storage: ObjectStorage | None, key: str) -> None:
    if storage is None:
        return
    try:
        storage.delete(key)
    except Exception:
        logger.exception("export_cleanup_failed")


def sweep(db: Session, settings: Settings, storage: ObjectStorage | None) -> list[uuid.UUID]:
    """Housekeeping, run with the recovery sweep: bundles past their time leave storage, jobs
    that stopped half-way wait again (or fail after three tries). Returns the jobs to hand to a
    worker."""
    now = datetime.now(UTC)
    for job in db.scalars(
        select(ExportJob)
        .where(ExportJob.state == "READY", ExportJob.expires_at <= now)
        .with_for_update(skip_locked=True)
    ):
        try:
            _expire(db, storage, job)
        except Exception:
            logger.exception("export_expiry_failed", extra={"export_id": str(job.id)})
    stale = now - timedelta(minutes=settings.export_stale_minutes)
    for job in db.scalars(
        select(ExportJob)
        .where(ExportJob.state == "RUNNING", ExportJob.claimed_at < stale)
        .with_for_update(skip_locked=True)
    ):
        if job.attempts >= MAX_ATTEMPTS:
            job.state = "FAILED"
            job.error = "The export stopped before it was finished, three times. Try a smaller one."
            job.finished_at = now
        else:
            job.state = "QUEUED"
    db.commit()
    # A job just asked for is on its way to a worker already: only ones left waiting are sent.
    waiting = now - timedelta(seconds=settings.export_requeue_seconds)
    return list(
        db.scalars(
            select(ExportJob.id)
            .where(ExportJob.state == "QUEUED", ExportJob.updated_at < waiting)
            .order_by(ExportJob.created_at)
            .limit(20)
        )
    )

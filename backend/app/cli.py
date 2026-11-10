"""Command-line tasks.  python -m app.cli seed-dev

seed-dev (FND-027): one demo account per role plus a DEMO project, for local development only.
It refuses to run unless APP_ENV is development or test, and needs DEMO_PASSWORD (>= 12 characters).
"""

from __future__ import annotations

import argparse
import os
import sys
import uuid
from pathlib import Path
from typing import Any

from sqlalchemy import select

from app.core.config import ConfigError, Settings, load_settings
from app.core.permissions import Role
from app.db.session import create_db_engine, make_session_factory
from app.modules.auth.models import RoleRecord, User
from app.modules.auth.security import hash_password
from app.modules.projects.models import Project, ProjectAudioRule, ProjectMembership
from app.modules.projects.service import DEFAULT_AUDIO, DEFAULT_MAX_SILENCE_PCT

# Reserved for documentation (RFC 2606) and accepted by the email checker (.test is not).
DEMO_DOMAIN = "example.org"


class SeedRefused(RuntimeError):
    pass


def seed_dev(settings: Settings, password: str) -> list[str]:
    if settings.app_env not in ("development", "test"):
        raise SeedRefused(f"seed-dev refuses to run with APP_ENV={settings.app_env}")
    if len(password) < settings.password_min_length:
        raise SeedRefused(
            f"DEMO_PASSWORD must be at least {settings.password_min_length} characters"
        )
    engine = create_db_engine(settings)
    created: list[str] = []
    with make_session_factory(engine)() as db:
        roles = {r.code: r for r in db.scalars(select(RoleRecord)).all()}
        project = db.scalar(select(Project).where(Project.code == "DEMO"))
        if project is None:
            project = Project(
                id=uuid.uuid4(),
                code="DEMO",
                name="Demo project",
                description="Local development data",
                status="ACTIVE",
                allows_telephony=True,
                allows_face_to_face=True,
            )
            project.audio_rules = [
                ProjectAudioRule(
                    mode=mode,
                    **fmt,
                    max_silence_pct=DEFAULT_MAX_SILENCE_PCT,
                    min_duration_seconds=0,
                )
                for mode, fmt in DEFAULT_AUDIO.items()
            ]
            db.add(project)
        for role in Role:
            email = f"demo.{role.value.lower().replace('_', '-')}@{DEMO_DOMAIN}"
            user = db.scalar(select(User).where(User.email == email))
            if user is None:
                user = User(
                    id=uuid.uuid4(),
                    email=email,
                    display_name=f"Demo {role.value.title().replace('_', ' ')}",
                )
                user.roles = [roles[role.value]]
                db.add(user)
                created.append(email)
            user.password_hash = hash_password(password)
            user.status = "ACTIVE"
            db.flush()
            if role is not Role.SUPER_ADMIN and not db.scalar(
                select(ProjectMembership.id).where(
                    ProjectMembership.user_id == user.id, ProjectMembership.project_id == project.id
                )
            ):
                db.add(ProjectMembership(user_id=user.id, project_id=project.id))
        db.commit()
    engine.dispose()
    return created


def run_retention(settings: Settings) -> int:
    from app.core.storage import build_storage
    from app.modules.recordings.service import apply_retention

    storage = build_storage(settings)
    if storage is None:
        raise SeedRefused("storage is not configured")
    engine = create_db_engine(settings)
    with make_session_factory(engine)() as db:
        count = apply_retention(db, storage)
    engine.dispose()
    return count


def run_recovery(settings: Settings) -> int:
    from app.main import create_app
    from app.modules.recordings.worker_dispatch import recover

    app = create_app(settings)
    if app.state.storage is None:
        raise SeedRefused("storage is not configured")
    if settings.redis_url is not None:
        from celery import Celery

        app.state.celery = Celery("ccp", broker=settings.redis_url.get_secret_value())
    count = recover(app)
    app.state.engine.dispose()
    return count


def _storage_and_db(settings: Settings) -> tuple[Any, Any, Any]:
    from app.core.storage import build_storage

    storage = build_storage(settings)
    if storage is None:
        raise SeedRefused("storage is not configured")
    engine = create_db_engine(settings)
    return storage, engine, make_session_factory(engine)()


def run_verify_assets(settings: Settings, deep: int) -> int:
    from app.modules.recordings.service import verify_assets

    storage, engine, db = _storage_and_db(settings)
    with db:
        checked, problems = verify_assets(
            db, storage, deep=deep, work_dir=Path(settings.media_work_dir)
        )
    engine.dispose()
    print(
        f"verify-assets: {checked} file(s) checked, {deep} downloaded again, "
        f"{len(problems)} problem(s)"
    )
    for p in problems:
        print(f"  {p.storage_key}: {p.problem}")
    return 1 if problems else 0


def run_storage_orphans(settings: Settings, hours: int, delete: bool) -> int:
    from datetime import timedelta

    from app.modules.recordings.service import storage_orphans

    storage, engine, db = _storage_and_db(settings)
    with db:
        orphans = storage_orphans(db, storage, timedelta(hours=hours))
    engine.dispose()
    size = sum(o.size for o in orphans)
    for o in orphans:
        print(f"  {o.key} ({o.size} bytes, {o.modified:%Y-%m-%d %H:%M})")
        if delete:
            storage.delete(o.key)
    verb = "deleted" if delete else "found (run with --delete to remove)"
    print(f"storage-orphans: {len(orphans)} file(s), {size} bytes, {verb}")
    return 0


BACKUP_PREFIX = "backups/db/"


def _storage(settings: Settings) -> Any:
    from app.core.storage import build_storage

    storage = build_storage(settings)
    if storage is None:
        raise SeedRefused("storage is not configured")
    return storage


def run_backup_upload(settings: Settings, name: str | None, source: Any) -> str:
    """Store a database dump read from `source` (stdin) with its SHA-256 (O9)."""
    import hashlib
    import tempfile
    from datetime import UTC, datetime

    storage = _storage(settings)
    key = BACKUP_PREFIX + (name or f"ccp-{datetime.now(UTC):%Y%m%dT%H%M%SZ}.dump")
    digest = hashlib.sha256()
    work = Path(settings.media_work_dir)
    work.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=work) as tmp:
        for part in iter(lambda: source.read(1 << 20), b""):
            digest.update(part)
            tmp.write(part)
        tmp.flush()
        size = tmp.tell()
        if size == 0:
            raise SeedRefused("the backup is empty")
        storage.put_file(
            key, Path(tmp.name), content_type="application/octet-stream", sha256=digest.hexdigest()
        )
    stored = storage.head(key)
    if stored is None or (stored.size, stored.sha256) != (size, digest.hexdigest()):
        raise SeedRefused("the backup did not arrive intact in storage")
    return f"{key} {size} bytes sha256 {digest.hexdigest()}"


def run_backup_download(settings: Settings, key: str, sink: Any) -> None:
    """Write a stored backup to `sink` (stdout) after checking it against its SHA-256 (O9)."""
    import hashlib
    import tempfile

    storage = _storage(settings)
    info = storage.head(key)
    if info is None:
        raise SeedRefused(f"no backup at {key}")
    work = Path(settings.media_work_dir)
    work.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=work) as tmp:
        path = Path(tmp) / "backup.dump"
        storage.get_to_file(key, path)
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for part in iter(lambda: handle.read(1 << 20), b""):
                digest.update(part)
        if digest.hexdigest() != info.sha256:
            raise SeedRefused("the stored backup does not match its checksum")
        with path.open("rb") as handle:
            for part in iter(lambda: handle.read(1 << 20), b""):
                sink.write(part)
    sink.flush()


def run_backup_prune(settings: Settings, keep_days: int) -> list[str]:
    """Delete backups older than `keep_days`; the newest backup is always kept (O9)."""
    from datetime import UTC, datetime, timedelta

    storage = _storage(settings)
    backups = sorted(storage.list_objects(BACKUP_PREFIX), key=lambda o: o.modified)
    cutoff = datetime.now(UTC) - timedelta(days=keep_days)
    removed = [o.key for o in backups[:-1] if o.modified < cutoff]
    for key in removed:
        storage.delete(key)
    return removed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("seed-dev", help="create demo accounts and a DEMO project (development only)")
    sub.add_parser(
        "retention", help="delete stored files older than each project's retention rules"
    )
    sub.add_parser(
        "recover-recordings",
        help="process again every recording left half-done by a stopped process",
    )
    verify = sub.add_parser(
        "verify-assets", help="check every stored file's presence, size and checksum label"
    )
    verify.add_argument("--deep", type=int, default=0, help="also download and re-hash N files")
    orphans = sub.add_parser(
        "storage-orphans", help="list (or delete) stored files that no record points to"
    )
    orphans.add_argument("--older-than-hours", type=int, default=24)
    orphans.add_argument("--delete", action="store_true")
    up = sub.add_parser("backup-upload", help="store a database dump read from standard input")
    up.add_argument("--name", default=None)
    down = sub.add_parser("backup-download", help="write a stored backup to standard output")
    down.add_argument("key")
    sub.add_parser("backup-list", help="list stored database backups")
    prune = sub.add_parser("backup-prune", help="delete stored backups older than N days")
    prune.add_argument("--keep-days", type=int, required=True)
    args = parser.parse_args(argv)
    try:
        settings = load_settings()
        if args.command == "seed-dev":
            created = seed_dev(settings, os.environ.get("DEMO_PASSWORD", ""))
            print(f"seed-dev: {len(created)} account(s) created; passwords from DEMO_PASSWORD")
        elif args.command == "retention":
            print(f"retention: {run_retention(settings)} file(s) deleted")
        elif args.command == "recover-recordings":
            print(f"recover-recordings: {run_recovery(settings)} recording(s) handed to processing")
        elif args.command == "verify-assets":
            return run_verify_assets(settings, args.deep)
        elif args.command == "storage-orphans":
            return run_storage_orphans(settings, args.older_than_hours, args.delete)
        elif args.command == "backup-upload":
            print(f"backup-upload: {run_backup_upload(settings, args.name, sys.stdin.buffer)}")
        elif args.command == "backup-download":
            run_backup_download(settings, args.key, sys.stdout.buffer)
        elif args.command == "backup-list":
            for o in sorted(
                _storage(settings).list_objects(BACKUP_PREFIX), key=lambda o: o.modified
            ):
                print(f"{o.key} {o.size} {o.modified:%Y-%m-%dT%H:%M:%SZ}")
        elif args.command == "backup-prune":
            removed = run_backup_prune(settings, args.keep_days)
            print(f"backup-prune: {len(removed)} backup(s) deleted")
    except (ConfigError, SeedRefused) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())

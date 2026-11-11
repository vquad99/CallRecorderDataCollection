"""Command-line tasks.  python -m app.cli seed-dev

seed-dev (FND-027): one demo account per role plus a DEMO project, for local development only.
It refuses to run unless APP_ENV is development or test (or staging with ALLOW_DEMO_SEED=true, for a
hosted check copy), and needs DEMO_PASSWORD (>= 12 characters; >= 16 on staging).
create-admin: the first Super Admin of a new deployment, from ADMIN_EMAIL and ADMIN_PASSWORD.
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
    hosted_check = (
        settings.app_env == "staging" and os.environ.get("ALLOW_DEMO_SEED", "").lower() == "true"
    )
    if settings.app_env not in ("development", "test") and not hosted_check:
        raise SeedRefused(f"seed-dev refuses to run with APP_ENV={settings.app_env}")
    if hosted_check and len(password) < 16:
        raise SeedRefused("DEMO_PASSWORD must be at least 16 characters on a hosted copy")
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


def create_admin(
    settings: Settings, email: str, password: str, *, reset: bool, first_only: bool = False
) -> str:
    """Bootstrap the first Super Admin in any environment (a new deployment has no users and no
    way to invite one before someone can sign in). Creates the account if it is missing; changes
    an existing account's password only with reset. Audited."""
    from email_validator import EmailNotValidError, validate_email

    from app.modules.audit import service as audit

    try:
        email = validate_email(email.strip(), check_deliverability=False).normalized.lower()
    except EmailNotValidError:
        raise SeedRefused("ADMIN_EMAIL is not a valid email address") from None
    if len(password) < max(settings.password_min_length, 12):
        raise SeedRefused(
            f"ADMIN_PASSWORD must be at least {max(settings.password_min_length, 12)} characters"
        )
    engine = create_db_engine(settings)
    try:
        with make_session_factory(engine)() as db:
            user = db.scalar(select(User).where(User.email == email))
            if user is not None and not reset:
                return "exists"
            if user is None and first_only and _has_active_super_admin(db):
                # Every deploy runs this. Once a Super Admin exists, a changed or removed
                # ADMIN_EMAIL account must not come back with the stored password (D-088).
                return "skipped (a Super Admin already exists)"
            if user is None:
                role = db.scalar(
                    select(RoleRecord).where(RoleRecord.code == Role.SUPER_ADMIN.value)
                )
                user = User(id=uuid.uuid4(), email=email, display_name="Administrator")
                if role is None:
                    raise SeedRefused("the database has no Super Admin role: run migrations")
                user.roles = [role]
                db.add(user)
                outcome = "created"
            else:
                outcome = "password reset"
            user.password_hash = hash_password(password)
            user.status = "ACTIVE"
            db.flush()
            audit.record(
                db,
                action="user.bootstrap_admin",
                entity_type="user",
                entity_id=user.id,
                actor_id=None,
                after={"outcome": outcome},
            )
            db.commit()
            return outcome
    finally:
        engine.dispose()


def _has_active_super_admin(db: Any) -> bool:
    from app.modules.auth.models import UserRole

    return (
        db.scalar(
            select(User.id)
            .join(UserRole, UserRole.user_id == User.id)
            .join(RoleRecord, RoleRecord.id == UserRole.role_id)
            .where(RoleRecord.code == Role.SUPER_ADMIN.value, User.status == "ACTIVE")
            .limit(1)
        )
        is not None
    )


def rotate_keys(settings: Settings) -> dict[str, int]:
    """Encrypt every stored secret field again with the first DATA_ENCRYPTION_KEY (D-088).
    Run after putting a new key first in the list; then the old key can be removed."""
    from app.modules.auth.security import FieldCipher
    from app.modules.participants.models import Participant

    cipher = FieldCipher(settings.data_encryption_key.get_secret_value())
    counts = {"participant phone": 0, "participant email": 0, "authenticator secret": 0}
    engine = create_db_engine(settings)
    try:
        with make_session_factory(engine)() as db:
            for p in db.scalars(select(Participant)):
                if p.phone_e164_enc:
                    p.phone_e164_enc = cipher.rotate(p.phone_e164_enc)
                    counts["participant phone"] += 1
                if p.email_enc:
                    p.email_enc = cipher.rotate(p.email_enc)
                    counts["participant email"] += 1
            for u in db.scalars(select(User).where(User.mfa_secret_enc.is_not(None))):
                u.mfa_secret_enc = cipher.rotate(u.mfa_secret_enc or "")
                counts["authenticator secret"] += 1
            db.commit()
    finally:
        engine.dispose()
    return counts


def migrate(settings: Settings) -> None:
    from alembic import command
    from alembic.config import Config

    config = Config(str(Path(__file__).resolve().parent.parent / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", settings.database_url.get_secret_value())
    command.upgrade(config, "head")


def prepare_deploy(settings: Settings) -> int:
    """One command for a host's pre-deploy step (D-077): migrations, the first Super Admin when
    ADMIN_EMAIL is set, and demo accounts only where allowed. One command, so no shell is needed
    (Render ran a quoted `sh -c` command as a single word)."""
    migrate(settings)
    print("prepare-deploy: database migrated")
    email = os.environ.get("ADMIN_EMAIL", "")
    if email:
        outcome = create_admin(
            settings, email, os.environ.get("ADMIN_PASSWORD", ""), reset=False, first_only=True
        )
        print(f"prepare-deploy: admin {email} {outcome}")
    allowed = settings.app_env in ("development", "test") or (
        settings.app_env == "staging" and os.environ.get("ALLOW_DEMO_SEED", "").lower() == "true"
    )
    if allowed and settings.app_env == "staging":
        created = seed_dev(settings, os.environ.get("DEMO_PASSWORD", ""))
        print(f"prepare-deploy: {len(created)} demo account(s) created")
    return 0


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
    seed = sub.add_parser(
        "seed-dev", help="create demo accounts and a DEMO project (development only)"
    )
    seed.add_argument(
        "--if-allowed",
        action="store_true",
        help="do nothing (and succeed) where seeding is not allowed, e.g. in a deploy step",
    )
    sub.add_parser(
        "prepare-deploy",
        help="before a deploy: migrate, create the first admin, seed demo data if allowed",
    )
    admin = sub.add_parser(
        "create-admin",
        help="create the first Super Admin from ADMIN_EMAIL and ADMIN_PASSWORD (any environment)",
    )
    admin.add_argument(
        "--reset-password", action="store_true", help="also set the password of an existing account"
    )
    sub.add_parser(
        "retention", help="delete stored files older than each project's retention rules"
    )
    sub.add_parser(
        "rotate-keys",
        help="encrypt stored secrets again with the first key in DATA_ENCRYPTION_KEY",
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
            allowed = settings.app_env in ("development", "test") or (
                settings.app_env == "staging"
                and os.environ.get("ALLOW_DEMO_SEED", "").lower() == "true"
            )
            if args.if_allowed and not allowed:
                print("seed-dev: not allowed here, skipped")
                return 0
            created = seed_dev(settings, os.environ.get("DEMO_PASSWORD", ""))
            print(f"seed-dev: {len(created)} account(s) created; passwords from DEMO_PASSWORD")
        elif args.command == "prepare-deploy":
            return prepare_deploy(settings)
        elif args.command == "create-admin":
            email = os.environ.get("ADMIN_EMAIL", "")
            if not email:
                print("create-admin: ADMIN_EMAIL not set, nothing to do")
                return 0
            outcome = create_admin(
                settings, email, os.environ.get("ADMIN_PASSWORD", ""), reset=args.reset_password
            )
            print(f"create-admin: {email} {outcome}")
        elif args.command == "rotate-keys":
            for what, n in rotate_keys(settings).items():
                print(f"rotate-keys: {n} {what}(s) re-encrypted")
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

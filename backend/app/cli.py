"""Command-line tasks.  python -m app.cli seed-dev

seed-dev (FND-027): one demo account per role plus a DEMO project, for local development only.
It refuses to run unless APP_ENV is development or test, and needs DEMO_PASSWORD (>= 12 characters).
"""

from __future__ import annotations

import argparse
import os
import sys
import uuid

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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("seed-dev", help="create demo accounts and a DEMO project (development only)")
    args = parser.parse_args(argv)
    try:
        settings = load_settings()
        if args.command == "seed-dev":
            created = seed_dev(settings, os.environ.get("DEMO_PASSWORD", ""))
            print(f"seed-dev: {len(created)} account(s) created; passwords from DEMO_PASSWORD")
    except (ConfigError, SeedRefused) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())

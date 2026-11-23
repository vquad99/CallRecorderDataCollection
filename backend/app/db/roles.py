"""A database role for the running app that does not own the schema (security audit 2026-11-23,
D-160).

The role that owns the tables can change them and can drop the trigger that keeps audit_logs
append-only. So the app should sign in to PostgreSQL as a role that may only read and write rows,
with UPDATE, DELETE and TRUNCATE on audit_logs taken away, while migrations run as the owner
(MIGRATION_DATABASE_URL). `python -m app.cli grant-app-role <name>` makes or updates that role;
the deploy step runs it again after each migration when APP_DATABASE_ROLE is set, so new tables
are covered too (docs/DEPLOYMENT.md, "A separate database role for the app").
"""

from __future__ import annotations

import re

from psycopg import sql
from sqlalchemy import Engine

ROLE_NAME = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")
# Tables the app only adds to: their rows are never changed or removed by it.
APPEND_ONLY = ("audit_logs",)
# Written only by migrations.
MIGRATIONS_ONLY = ("alembic_version",)


def grant_app_role(engine: Engine, name: str, password: str | None) -> str:
    """Creates the role when it does not exist (a password is needed then) and (re)grants what the
    app needs on every table, now and later. Returns "created" or "updated". Run as the owner."""
    if not ROLE_NAME.fullmatch(name):
        raise ValueError("The role name takes lowercase letters, digits and _ only")
    role = sql.Identifier(name)
    with engine.begin() as connection:
        raw = connection.connection.driver_connection
        if raw is None:
            raise RuntimeError("No database connection")
        cur = raw.cursor()
        cur.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (name,))
        exists = cur.fetchone() is not None
        if exists and password:
            cur.execute(
                sql.SQL("ALTER ROLE {} LOGIN PASSWORD {}").format(role, sql.Literal(password))
            )
        elif not exists:
            if not password:
                raise ValueError("Set APP_ROLE_PASSWORD to create the role")
            cur.execute(
                sql.SQL(
                    "CREATE ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE PASSWORD {}"
                ).format(role, sql.Literal(password))
            )
        cur.execute("SELECT current_database()")
        (database,) = cur.fetchone() or ("",)
        statements = [
            sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(sql.Identifier(database), role),
            sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(role),
            sql.SQL(
                "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {}"
            ).format(role),
            sql.SQL("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {}").format(role),
            sql.SQL(
                "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
                "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {}"
            ).format(role),
            sql.SQL(
                "ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO {}"
            ).format(role),
        ]
        statements += [
            sql.SQL("REVOKE UPDATE, DELETE, TRUNCATE ON {} FROM {}").format(
                sql.Identifier(table), role
            )
            for table in APPEND_ONLY
        ]
        statements += [
            sql.SQL("REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON {} FROM {}").format(
                sql.Identifier(table), role
            )
            for table in MIGRATIONS_ONLY
        ]
        for statement in statements:
            cur.execute(statement)
    return "updated" if exists else "created"

#!/usr/bin/env bash
# Database restore (owner's list, O9): replaces the database with a stored backup. The backup is
# checked against its SHA-256 before anything is touched; the backend and worker are stopped while
# the database is replaced and started again afterwards.
#
#   infra/backup/restore.sh backups/db/ccp-20261110T020000Z.dump
#   list stored backups: docker compose ... exec backend python -m app.cli backup-list
set -euo pipefail
key="${1:?usage: restore.sh <backup key, e.g. backups/db/ccp-20261110T020000Z.dump>}"
C="docker compose --env-file ${ENV_FILE:-.env} -f infra/docker-compose.yml"
tmp="$(mktemp)"
trap 'rm -f "$tmp"' EXIT
$C exec -T backend python -m app.cli backup-download "$key" > "$tmp"
test -s "$tmp"
$C stop backend worker
$C exec -T db pg_restore --username=ccp --dbname=ccp --clean --if-exists --no-owner --exit-on-error < "$tmp"
$C start backend worker
echo "restore: $key restored"

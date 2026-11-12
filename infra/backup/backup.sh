#!/usr/bin/env bash
# Database backup (owner's list, O9): a pg_dump of the running database, stored in the private file
# storage under backups/db/ with its SHA-256, checked after upload. Old backups: backup-prune.
#
#   infra/backup/backup.sh            (run from the repository root, with .env in place)
#   KEEP_DAYS=30 infra/backup/backup.sh   also deletes backups older than 30 days (newest kept)
set -euo pipefail
C="docker compose --env-file ${ENV_FILE:-.env} -f ${COMPOSE_FILE_PATH:-infra/docker-compose.yml}"
name="ccp-$(date -u +%Y%m%dT%H%M%SZ).dump"
$C exec -T db pg_dump --username=ccp --dbname=ccp --format=custom --no-owner \
  | $C exec -T backend python -m app.cli backup-upload --name "$name"
if [ -n "${KEEP_DAYS:-}" ]; then
  $C exec -T backend python -m app.cli backup-prune --keep-days "$KEEP_DAYS"
fi

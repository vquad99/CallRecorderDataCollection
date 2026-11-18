#!/usr/bin/env bash
# The platform's own database backup on the AWS server (O9, D-058, D-132). As the ccp user:
#   deploy/aws/backup.sh                 dump RDS into the bucket, then delete dumps older than KEEP_DAYS
#   deploy/aws/backup.sh list            the stored dumps
#   deploy/aws/backup.sh restore <key>   replace the whole database with one of them
# A dump is stored by the app (python -m app.cli backup-upload) under backups/db/ in the S3 bucket
# (with the key prefix: staging/backups/db/), with its SHA-256, checked after upload; a restore
# checks it again first. This is a second copy next to RDS's automated backups (7 days, to the
# minute): kept KEEP_DAYS (30), in another service, and it outlives the RDS instance. The
# ccp-backup timer runs it daily; it does nothing before the first deploy.
set -euo pipefail

AWS_DIR="$(cd "$(dirname "$0")" && pwd)"
compose() { bash "$AWS_DIR/compose.sh" "$@"; }
KEEP_DAYS="${KEEP_DAYS:-30}"

say() {
  echo "backup: $*"
  if [ -n "${OPS_LOG:-}" ]; then echo "$(date -u +%FT%TZ) backup: $*" >> "$OPS_LOG" || true; fi
}

[ -f "$AWS_DIR/.state/live" ] || { echo "backup: nothing deployed yet"; exit 0; }

case "${1:-}" in
  "")
    name="ccp-$(date -u +%Y%m%dT%H%M%SZ).dump"
    if compose run --rm -T pgtools pg_dump --format=custom --no-owner \
      | compose exec -T api python -m app.cli backup-upload --name "$name"; then
      compose exec -T api python -m app.cli backup-prune --keep-days "$KEEP_DAYS" >/dev/null \
        || say "FAILED: pruning dumps older than $KEEP_DAYS days"
      say "$name stored"
    else
      say "FAILED: $name"
      exit 1
    fi
    ;;
  list)
    compose exec -T api python -m app.cli backup-list
    ;;
  restore)
    key="${2:?usage: backup.sh restore <key, e.g. backups/db/ccp-20261201T203000Z.dump>}"
    exec 9>"$AWS_DIR/.state/deploy.lock"
    flock -n 9 || { echo "backup: a deploy is running; try again in a minute"; exit 1; }
    read -r -p "This replaces the whole database with $key. Type RESTORE to go on: " answer
    [ "$answer" = RESTORE ] || exit 1
    tmp="$(mktemp)"
    trap 'rm -f "$tmp"' EXIT
    compose exec -T api python -m app.cli backup-download "$key" > "$tmp"
    test -s "$tmp"
    compose stop api worker web
    # Clear out what is there first (objects a newer migration made would clash with the dump).
    compose run --rm -T pgtools psql -X -q -v ON_ERROR_STOP=1 -c 'DROP OWNED BY CURRENT_USER'
    compose run --rm -T pgtools sh -c \
      'exec pg_restore --dbname="$PGDATABASE" --no-owner --no-privileges --exit-on-error' < "$tmp"
    compose run --rm -T migrate  # a dump from an older release gets the newer migrations
    compose up -d --wait --wait-timeout 300 --no-build
    say "restored $key"
    ;;
  *) sed -n '2,5p' "$0"; exit 2 ;;
esac

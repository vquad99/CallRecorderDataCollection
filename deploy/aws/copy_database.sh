#!/usr/bin/env bash
# The move from Render (D-132): copy the Render database into RDS, then compare every table on both
# sides: its row count and a checksum of all its rows. Run on the AWS server as the ccp user, while
# Render is stopped (docs/DEPLOYMENT_AWS.md 8.3):
#   read -rs RENDER_DB_URL; export RENDER_DB_URL    paste Render's External Database URL (not shown)
#   deploy/aws/copy_database.sh                      copy, then compare
#   deploy/aws/copy_database.sh compare              compare only
# Render refuses outside connections until this server's Elastic IP is on ccp-db's allow list
# (remove it again afterwards). Replaces everything in the RDS database. Stops the app containers
# and holds the deploy lock, so no automatic deploy starts them during the copy.
set -euo pipefail

AWS_DIR="$(cd "$(dirname "$0")" && pwd)"
compose() { bash "$AWS_DIR/compose.sh" "$@"; }
: "${RENDER_DB_URL:?set RENDER_DB_URL: Render > ccp-db > Connect > External Database URL}"
export RENDER_DB_URL
grep -q '^DB_HOST=.' "$AWS_DIR/.env" || { echo "copy: DB_HOST is empty in deploy/aws/.env"; exit 1; }
mkdir -p "$AWS_DIR/.state"
exec 9>"$AWS_DIR/.state/deploy.lock"
flock -n 9 || { echo "copy: a deploy is running; try again in a minute"; exit 1; }

# Every table: name, rows, and an md5 over the md5 of each row, in a fixed order. The same output
# settings on both sides, so equal rows print the same text.
export PGOPTIONS="-c TimeZone=UTC -c DateStyle=ISO,MDY -c IntervalStyle=postgres -c extra_float_digits=1 -c bytea_output=hex"
read -r -d '' COMPARE_SQL <<'SQL' || true
SELECT format(
  'SELECT %L, count(*), coalesce(md5(string_agg(md5(t::text), %L ORDER BY md5(t::text))), %L) FROM public.%I t',
  tablename, '', 'empty', tablename)
FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename
\gexec
SQL

compare() {
  local dir
  dir="$(mktemp -d)"
  compose run --rm -T -e RENDER_DB_URL -e PGOPTIONS pgtools \
    sh -c 'exec psql -X -At -F" " -v ON_ERROR_STOP=1 --dbname="$RENDER_DB_URL"' <<<"$COMPARE_SQL" > "$dir/render"
  compose run --rm -T -e PGOPTIONS pgtools \
    psql -X -At -F" " -v ON_ERROR_STOP=1 <<<"$COMPARE_SQL" > "$dir/rds"
  if [ -s "$dir/render" ] && cmp -s "$dir/render" "$dir/rds"; then
    echo "copy: all $(wc -l < "$dir/rds") tables match (rows and checksums):"
    cat "$dir/rds"
  else
    echo "copy: the databases DIFFER (left Render, right RDS):"
    diff "$dir/render" "$dir/rds" || true
    exit 1
  fi
}

if [ "${1:-}" = compare ]; then compare; exit 0; fi

read -r -p "This replaces everything in the RDS database with Render's data. Type COPY to go on: " answer
[ "$answer" = COPY ] || exit 1
compose stop api worker web 2>/dev/null || true
echo "copy: clearing the RDS database"
compose run --rm -T pgtools psql -X -q -v ON_ERROR_STOP=1 -c 'DROP OWNED BY CURRENT_USER'
echo "copy: Render -> RDS (pg_dump | pg_restore, both over TLS)"
compose run --rm -T -e RENDER_DB_URL pgtools sh -c 'set -eo pipefail
  pg_dump --dbname="$RENDER_DB_URL" --format=custom --no-owner --no-privileges \
    | pg_restore --dbname="$PGDATABASE" --no-owner --no-privileges --exit-on-error'
compare
echo "copy: done. Next: deploy/aws/deploy.sh (migrations, then the app starts on the copied data)."

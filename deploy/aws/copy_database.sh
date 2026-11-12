#!/usr/bin/env bash
# Copy the Render database into the AWS server's database (D-096), then compare row counts.
# Run on the AWS server, with only db and redis started (README step 5):
#   RENDER_DB_URL='postgresql://ccp:...@....singapore-postgres.render.com/ccp' deploy/aws/copy_database.sh
# The Render database refuses outside connections until this server's address is added to its
# allow list (Render dashboard -> ccp-db -> Networking). Replaces whatever the AWS database holds.
set -euo pipefail
cd "$(dirname "$0")/../.."
src="${RENDER_DB_URL:?set RENDER_DB_URL (Render dashboard -> ccp-db -> External Database URL)}"
C="docker compose -f deploy/aws/docker-compose.yml"
$C stop backend worker web caddy 2>/dev/null || true
$C up -d --wait db redis
$C exec -T db pg_dump "$src" --format=custom --no-owner --no-privileges \
  | $C exec -T db pg_restore --username=ccp --dbname=ccp --clean --if-exists --no-owner \
      --no-privileges --exit-on-error
count="SELECT string_agg(t || '=' || n, ' ' ORDER BY t) FROM (
  SELECT 'users' t, count(*) n FROM users UNION ALL
  SELECT 'projects', count(*) FROM projects UNION ALL
  SELECT 'participants', count(*) FROM participants UNION ALL
  SELECT 'tasks', count(*) FROM tasks UNION ALL
  SELECT 'recordings', count(*) FROM recordings UNION ALL
  SELECT 'audit_logs', count(*) FROM audit_logs) x"
render="$($C exec -T db psql "$src" -Atc "$count")"
aws="$($C exec -T db psql --username=ccp --dbname=ccp -Atc "$count")"
echo "render: $render"
echo "aws:    $aws"
[ "$render" = "$aws" ] && echo "copy: row counts match" || { echo "copy: row counts DIFFER"; exit 1; }

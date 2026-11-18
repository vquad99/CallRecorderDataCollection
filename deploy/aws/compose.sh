#!/usr/bin/env bash
# Docker Compose for the AWS server, with the right files (D-132). Always the base file, plus
#   docker-compose.localdb.yml  when DB_HOST is empty in .env (a stand-in database: CI and trials)
#   docker-compose.awslogs.yml  when AWS_LOG_GROUP is set in .env (container logs to CloudWatch)
# and IMAGE_TAG set to the images now live (deploy.sh passes its own). As the ccp user:
#   deploy/aws/compose.sh ps
#   deploy/aws/compose.sh logs -f --tail 100 api worker
#   deploy/aws/compose.sh exec api python -m app.cli verify-assets
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
setting() { sed -n "s/^$1=//p" "$here/.env" 2>/dev/null | tail -n 1; }

files=(-f "$here/docker-compose.yml")
[ -n "$(setting DB_HOST)" ] || files+=(-f "$here/docker-compose.localdb.yml")
[ -z "$(setting AWS_LOG_GROUP)" ] || files+=(-f "$here/docker-compose.awslogs.yml")
if [ -z "${IMAGE_TAG:-}" ]; then
  IMAGE_TAG="$(cat "$here/.state/live" 2>/dev/null || echo latest)"
fi
export IMAGE_TAG
exec docker compose --project-directory "$here" "${files[@]}" "$@"

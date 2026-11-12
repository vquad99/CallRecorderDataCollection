#!/usr/bin/env bash
# Build and start (or update) the platform on the AWS server (D-096). Run from anywhere:
#   deploy/aws/deploy.sh            latest main
#   NO_PULL=1 deploy/aws/deploy.sh  the code as it is on disk
# The migrate service runs first (migrations, first admin); the API starts only if it succeeds.
set -euo pipefail
cd "$(dirname "$0")/../.."
test -f deploy/aws/.env || { echo "deploy: deploy/aws/.env is missing (copy env.example)"; exit 1; }
[ -n "${NO_PULL:-}" ] || git pull --ff-only
C="docker compose -f deploy/aws/docker-compose.yml"
$C build
$C up -d --wait --remove-orphans
$C ps
echo "deploy: $(git rev-parse --short HEAD) is live"

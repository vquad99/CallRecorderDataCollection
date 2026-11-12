#!/usr/bin/env bash
# One-time set-up of a new Ubuntu 24.04 EC2 server for the platform (D-096). Run as root from the
# repository checkout (/opt/ccp):  sudo deploy/aws/bootstrap.sh
# Installs Docker + Compose, adds 2 GB swap (the web build needs it on small servers) and the daily
# database backup. Safe to run again.
set -euo pipefail
cd "$(dirname "$0")/../.."
apt-get update -q
DEBIAN_FRONTEND=noninteractive apt-get install -yq docker.io docker-compose-v2 git
systemctl enable --now docker
if ! swapon --show | grep -q /swapfile; then
  fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile
  grep -q '^/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi
mkdir -p deploy/aws/certs
cat > /etc/cron.d/ccp-backup <<CRON
# Daily database backup to the file storage, 30 days kept (O9).
30 20 * * * root cd $PWD && ENV_FILE=deploy/aws/.env COMPOSE_FILE_PATH=deploy/aws/docker-compose.yml KEEP_DAYS=30 infra/backup/backup.sh >> /var/log/ccp-backup.log 2>&1
CRON
echo "bootstrap: done. Next: deploy/aws/.env (from env.example), then deploy/aws/README.md step 4."

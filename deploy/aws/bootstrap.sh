#!/usr/bin/env bash
# One-time set-up of the AWS server for Conversation Collection (D-132). Ubuntu 24.04, as root.
# Terraform's user data saves this script as /usr/local/sbin/ccp-bootstrap and runs it at first
# boot. That run stops after making the server's deploy key: add the key to GitHub (read-only),
# then run it again by hand:   sudo ccp-bootstrap
# The second run clones the repository to /opt/ccp, installs the deploy and backup timers and starts
# the CloudWatch agent. Safe to run again at any time (docs/DEPLOYMENT_AWS.md steps 5-6).
set -euo pipefail

APP_USER=ccp
APP_HOME=/home/ccp
APP_DIR=/opt/ccp
KEY="$APP_HOME/.ssh/deploy_key"
REPO_URL="${CCP_REPO_URL:-$(cat /etc/ccp/repo_url 2>/dev/null || true)}"
BRANCH="${CCP_BRANCH:-$(cat /etc/ccp/repo_branch 2>/dev/null || echo main)}"
CWAGENT=/opt/aws/amazon-cloudwatch-agent
say() { echo "bootstrap: $*"; }
as_app() { runuser -u "$APP_USER" -- env HOME="$APP_HOME" "$@"; }

[ "$(id -u)" = 0 ] || { say "run as root (sudo ccp-bootstrap)"; exit 1; }
[ -n "$REPO_URL" ] || { say "set CCP_REPO_URL=git@github.com:<owner>/<repo>.git"; exit 1; }
install -d -m 755 /etc/ccp
echo "$REPO_URL" > /etc/ccp/repo_url
echo "$BRANCH" > /etc/ccp/repo_branch

# 1. Docker with Compose and Buildx, git, the CloudWatch agent. Ubuntu installs security updates by
#    itself (unattended-upgrades); it does not reboot by itself (docs/DEPLOYMENT_AWS.md 10.6).
say "installing packages"
export DEBIAN_FRONTEND=noninteractive
APT=(apt-get -o DPkg::Lock::Timeout=600)  # at first boot Ubuntu's own updates may hold the lock
"${APT[@]}" update -q
"${APT[@]}" install -yq docker.io docker-compose-v2 docker-buildx git curl unattended-upgrades
if [ ! -f /etc/docker/daemon.json ]; then
  # live-restore: containers keep running while Docker itself is updated.
  echo '{"live-restore": true, "log-driver": "json-file", "log-opts": {"max-size": "10m", "max-file": "3"}}' \
    > /etc/docker/daemon.json
  systemctl restart docker
fi
systemctl enable --now docker
if ! dpkg -s amazon-cloudwatch-agent >/dev/null 2>&1; then
  curl -fsSL -o /tmp/cwagent.deb \
    https://amazoncloudwatch-agent.s3.amazonaws.com/ubuntu/amd64/latest/amazon-cloudwatch-agent.deb
  dpkg -i /tmp/cwagent.deb
  rm -f /tmp/cwagent.deb
fi

# 2. 2 GB swap (the web build needs memory while the site keeps running); Redis's advice.
if ! swapon --show | grep -q /swapfile; then
  fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap -q /swapfile && swapon /swapfile
  grep -q '^/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi
echo 'vm.overcommit_memory = 1' > /etc/sysctl.d/90-ccp.conf
sysctl -q -p /etc/sysctl.d/90-ccp.conf

# 3. The app user: owns the checkout and .env, runs deploys and backups, may use Docker (which is
#    as good as root: so .env, readable by ccp only, is in effect a root-only file).
id "$APP_USER" >/dev/null 2>&1 \
  || useradd --system --create-home --home-dir "$APP_HOME" --shell /bin/bash "$APP_USER"
usermod -aG docker,systemd-journal "$APP_USER"  # Docker; read the journal
install -d -o "$APP_USER" -g "$APP_USER" -m 700 "$APP_HOME/.ssh"
install -d -o "$APP_USER" -g "$APP_USER" -m 755 /var/log/ccp
touch /var/log/ccp/operations.log && chown "$APP_USER:$APP_USER" /var/log/ccp/operations.log

# 4. Read-only deploy key for GitHub, and GitHub's published host key (docs.github.com, "GitHub's
#    SSH key fingerprints": SHA256:+DiY3wvvV6TuJJhbpZisF/zLDA0zPMSvHdkr4UvCOqU), so nothing else
#    can pose as GitHub.
[ -f "$KEY" ] || as_app ssh-keygen -q -t ed25519 -N '' -C ccp-server-deploy-key -f "$KEY"
printf 'Host github.com\n  IdentityFile %s\n  IdentitiesOnly yes\n  StrictHostKeyChecking yes\n' "$KEY" \
  > "$APP_HOME/.ssh/config"
echo 'github.com ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIOMqqnkVzrm0SdG6UOoqKLsabgH5C9okWi0dh2l9GKJl' \
  > "$APP_HOME/.ssh/known_hosts"
chown "$APP_USER:$APP_USER" "$APP_HOME/.ssh/config" "$APP_HOME/.ssh/known_hosts"
chmod 600 "$APP_HOME/.ssh/config"

# 5. The code. Stops here until GitHub accepts the deploy key.
if [ ! -d "$APP_DIR/.git" ]; then
  if ! as_app git ls-remote "$REPO_URL" >/dev/null 2>&1; then
    say "GitHub does not accept this server's key yet. Add it as a deploy key:"
    say "GitHub > the repository > Settings > Deploy keys > Add deploy key; 'Allow write access' OFF."
    cat "$KEY.pub"
    say "Then run: sudo ccp-bootstrap"
    exit 0
  fi
  install -d -o "$APP_USER" -g "$APP_USER" -m 750 "$APP_DIR"
  as_app git clone --quiet --branch "$BRANCH" "$REPO_URL" "$APP_DIR"
fi
install -d -o "$APP_USER" -g "$APP_USER" -m 700 "$APP_DIR/deploy/aws/certs" "$APP_DIR/deploy/aws/.state"

# 6. Timers (deploy on push, daily backup), log rotation, CloudWatch agent (disk and memory figures,
#    the deploy and backup log).
install -m 644 "$APP_DIR"/deploy/aws/systemd/ccp-*.service "$APP_DIR"/deploy/aws/systemd/ccp-*.timer \
  /etc/systemd/system/
printf '/var/log/ccp/*.log {\n  monthly\n  rotate 12\n  compress\n  missingok\n  notifempty\n  copytruncate\n}\n' \
  > /etc/logrotate.d/ccp
install -m 644 "$APP_DIR/deploy/aws/cloudwatch-agent.json" "$CWAGENT/etc/ccp.json"
"$CWAGENT/bin/amazon-cloudwatch-agent-ctl" -a fetch-config -m ec2 -s -c "file:$CWAGENT/etc/ccp.json"
systemctl daemon-reload
systemctl enable --now ccp-deploy.timer ccp-backup.timer

say "done. Next: $APP_DIR/deploy/aws/.env and the first deploy (docs/DEPLOYMENT_AWS.md steps 6-7)."

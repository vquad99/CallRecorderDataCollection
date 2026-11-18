# The AWS server (D-132)

One EC2 server in Mumbai runs web (nginx), API, worker, Redis and Caddy (HTTPS) with Docker
Compose. The database is RDS and the files are in S3. The AWS resources are made by Terraform in
`infra/aws/`. The whole procedure, including the move from Render: `docs/DEPLOYMENT_AWS.md`.

| File | What it is |
|---|---|
| `docker-compose.yml` | the services; only Caddy opens ports (80, 443) |
| `docker-compose.localdb.yml` | a stand-in database instead of RDS: CI and trials only |
| `docker-compose.awslogs.yml` | container logs to CloudWatch (when `AWS_LOG_GROUP` is set) |
| `compose.sh` | `docker compose` with the right files and image tag; use it for every compose command |
| `Caddyfile` | HTTPS with the Cloudflare Origin Certificate; the visitor's address from Cloudflare only |
| `env.example` | every setting, with where its value comes from; copy to `.env` on the server |
| `bootstrap.sh` | one-time server set-up (Terraform's user data runs it; then `sudo ccp-bootstrap`) |
| `deploy.sh` | build, migrate, start; `--if-changed` (timer), `rollback [TAG]`, `status` |
| `systemd/` | `ccp-deploy.timer` (every minute) and `ccp-backup.timer` (daily) |
| `cloudwatch-agent.json` | disk and memory figures, and the deploy and backup log, to CloudWatch |
| `backup.sh` | daily database dump into S3; `list`; `restore <key>` |
| `copy_database.sh` | the move: Render database into RDS, every table compared |
| `copy_files.sh` | the move: Wasabi files into S3, counts and sizes compared |

CI's `aws-stack` job starts this set-up from `env.example` with the stand-in database and checks
that the site answers over HTTPS (`.github/workflows/ci.yml`).

Everyday commands (as the `ccp` user: `sudo -iu ccp`, then `cd /opt/ccp`):

```sh
deploy/aws/deploy.sh status                 # what runs, which images are kept
deploy/aws/deploy.sh rollback               # back to the previous deploy
deploy/aws/compose.sh logs -f --tail 100 api worker
journalctl -u ccp-deploy -n 100             # what the deploy timer did
```

# Moving the platform from Render to AWS (D-096)

One EC2 server in Singapore runs everything with Docker Compose: PostgreSQL, Redis, API, worker,
web (nginx) and Caddy for HTTPS. Cloudflare stays in front of `dubdesk.live`. Audio files stay in
the Wasabi bucket unless step 8 is done. Downtime: about 15 minutes, during steps 5 to 7.

| File | What it is |
|---|---|
| `docker-compose.yml` | every service; only Caddy opens ports (80, 443) |
| `Caddyfile` | HTTPS; takes the visitor's address from Cloudflare only |
| `env.example` | every setting; copy to `.env` on the server |
| `bootstrap.sh` | one-time server set-up: Docker, swap, daily backup |
| `deploy.sh` | build, migrate, start; also every later update |
| `copy_database.sh` | copies the Render database and compares row counts |

## Cost (Singapore, on-demand, per month)

| Item | Size | About |
|---|---|---|
| EC2 | t3.medium (2 CPU, 4 GB) | $38 |
| Disk | 40 GB gp3 | $4 |
| Public address | 1 Elastic IP | $4 |
| Total | | **$46** |

S3 instead of Wasabi (step 8) adds about $0.025 per GB stored and $0.12 per GB downloaded.

## Steps

1. **Server.** EC2 console, region ap-southeast-1: Ubuntu 24.04, t3.medium, 40 GB gp3, an Elastic
   IP. Security group: 22 from your own address only; 80 and 443 from the Cloudflare ranges
   (https://www.cloudflare.com/ips/), nothing else.
2. **Code.** On the server:
   `sudo git clone git@github.com:vquad99/CallRecorderDataCollection.git /opt/ccp`
   (a read-only GitHub deploy key for the server), then `cd /opt/ccp && sudo deploy/aws/bootstrap.sh`.
3. **Settings.** `cp deploy/aws/env.example deploy/aws/.env && chmod 600 deploy/aws/.env`, fill it.
   `SECRET_KEY`, `DATA_ENCRYPTION_KEY`, storage, mail and admin values are copied from Render
   (ccp-api -> Environment). `DATA_ENCRYPTION_KEY` must be the same, or stored phone numbers are
   unreadable.
4. **Trial start.** `sudo deploy/aws/deploy.sh`. Check:
   `curl -k --resolve dubdesk.live:443:127.0.0.1 https://dubdesk.live/health/live`.
5. **Stop work on Render.** Render dashboard: suspend `ccp-web` (nobody can change data now).
   Render `ccp-db` -> Networking: add the server's Elastic IP.
6. **Copy the database.** `sudo RENDER_DB_URL='<External Database URL>' deploy/aws/copy_database.sh`
   must end with `copy: row counts match`. Then `sudo deploy/aws/deploy.sh`.
7. **Switch the address.** Cloudflare -> DNS: `dubdesk.live` A record -> the Elastic IP, proxied
   (orange). SSL/TLS mode **Full** (with `TLS=internal`). Open https://dubdesk.live, sign in, open a
   project, play a recording, make a 10-second test recording and see it processed.
8. **Optional: audio to S3.** Make a private bucket (versioning on, public access blocked, CORS for
   `https://dubdesk.live`), copy `callrec57/staging/` into it with the same keys
   (`aws s3 sync` with the Wasabi endpoint, or rclone), compare file counts, switch the storage
   lines in `.env` (see `env.example`), `sudo deploy/aws/deploy.sh`.
9. **Retire Render.** After a week without problems: remove the Elastic IP from the Render
   allow list, take a last Render database backup, delete the Render services.

**Going back** (any time before step 9): point the Cloudflare record back to Render and resume
`ccp-web`. Data written on AWS after step 6 is not on Render.

## Daily running

- Update: `sudo deploy/aws/deploy.sh` (Render deployed on every push; here it is by hand).
- Logs: `sudo docker compose -f deploy/aws/docker-compose.yml logs -f backend worker`.
- Backups: every day 20:30 UTC (02:00 IST) to the file storage, 30 days kept
  (`/var/log/ccp-backup.log`). Restore:
  `sudo ENV_FILE=deploy/aws/.env COMPOSE_FILE_PATH=deploy/aws/docker-compose.yml infra/backup/restore.sh <key>`.

# Deployment on AWS (D-132)

For the person who has access to the client's AWS account. It moves the live copy from Render to
one server in the client's AWS account in Mumbai, then covers daily running.

**Status: written, not tried.** Nothing has been created in AWS yet. The Terraform files pass
`terraform validate`; the scripts pass `bash -n`; CI starts the server set-up (with a stand-in
database) on every push. Every step that touches AWS, Render, Cloudflare or GoDaddy is NOT
VERIFIED. Correct this file when you walk through it.

## 1. What runs where

| Part | Where | Looked after by |
|---|---|---|
| Web (nginx: the app, `/api` to the API), API, worker, Redis, Caddy (HTTPS) | Docker containers on one EC2 server `ccp-server`: t3.medium (2 CPUs, 4 GB), Ubuntu 24.04 LTS, 40 GB encrypted disk, a fixed public address (Elastic IP) | us: `deploy/aws/` |
| Database | RDS PostgreSQL 16 `ccp-db`: db.t4g.small, 20 GB encrypted (grows to 100 GB), automated backups 7 days, not public, reachable only from the server | AWS: patches, backups, disk |
| Files (recordings, originals, exports, the app's own database dumps) | S3 bucket `ccp-recordings-<account id>`: private, encrypted, versioning; the server reaches it with its own role, no keys | AWS |
| Logs | CloudWatch Logs: `/ccp/app` (containers), `/ccp/operations` (deploys, backups); 30 days | AWS |
| Alarms | CloudWatch alarms emailed to one address | AWS |
| Shell on the server | Session Manager (browser or AWS CLI); no SSH port open | AWS |
| In front of the site | Cloudflare (proxy, hides the server, Origin Certificate) | Cloudflare (free plan) |
| Deploys | A timer on the server checks GitHub every minute and deploys new pushes to `main` | us: `deploy/aws/deploy.sh` |

Region ap-south-1 (Mumbai), the account's default VPC. The AWS resources are made by Terraform
(`infra/aws/`). The app also emails its own alerts (`ALERT_EMAIL`, D-109); the AWS alarms watch
the machine around it.

## 2. Cost per month (rough)

On-demand prices in Mumbai as remembered from AWS's price list, rounded. Check them in the AWS
Pricing Calculator (https://calculator.aws) before approval.

| Item | Size | About USD |
|---|---|---|
| Server | t3.medium, all month | 33 |
| Server disk | 40 GB gp3 | 4 |
| Public address | Elastic IP (every public IPv4 address is charged) | 4 |
| Database | db.t4g.small, one zone | 27 |
| Database disk | 20 GB gp3 | 3 |
| Database backups | up to the size of the database disk | 0 |
| Files | per 100 GB stored | 2.50 |
| Downloads (recordings played or exported) | first 100 GB a month free, then about 0.11 per GB | 0 at today's use |
| Logs, disk and memory figures, alarms, alarm emails, Session Manager | small | 1 to 2 |
| **Total** | | **about 70, plus 2.50 per 100 GB of files** |

The server runs in "unlimited" CPU mode: if its average CPU stays above 20% for a long time, AWS
adds about 0.05 per CPU-hour above that. Render today: about 37 a month plus Wasabi.

## 3. Before you start

### 3.1 What you need

- The client's AWS account, with MFA on the root user, and an IAM user for yourself (3.2).
- On your computer: Terraform 1.10 or newer, and the AWS CLI v2 signed in to that account
  (`aws sts get-caller-identity` answers). The Session Manager plugin is optional: the EC2 console
  opens a shell in the browser.
- GitHub: admin rights on the repository (to add the server's read-only deploy key).
- Render: access to the dashboard (`ccp-api` > Environment for the settings; `ccp-db` for the copy).
- Wasabi: an access key that can read bucket `callrec57` (for the file copy).
- Cloudflare: an account with `dubdesk.live` in it (3.3).

### 3.2 Permissions for the person who applies Terraform

Simplest: for the set-up day, your IAM user (with MFA) gets `AdministratorAccess`; take it away
afterwards. Narrower, and enough for this set-up and later changes, these AWS managed policies:

- `AmazonEC2FullAccess` (server, address, security groups)
- `AmazonRDSFullAccess` (database)
- `AmazonS3FullAccess` (bucket)
- `CloudWatchFullAccessV2` (log groups, alarms, the failure filter)
- `AmazonSNSFullAccess` (alarm emails)
- `IAMFullAccess` (the server's role, the admin group; also the RDS service role on first use)
- `AmazonSSMReadOnlyAccess` (the Ubuntu image number Terraform looks up)

For a shell on the server, put your IAM user name in `admin_iam_users` (Terraform adds you to the
group `ccp-admins`). For roles or IAM Identity Center, attach the output `admin_session_policy_arn`.

### 3.3 Cloudflare in front (two days before the move)

Today `dubdesk.live` is at **GoDaddy** and points straight at Render (HANDOVER.md section 4). The
Cloudflare that answers today is Render's own, not an account of ours. To keep Cloudflare in front
on AWS, the domain moves to a Cloudflare account of the client's first:

1. Make a free Cloudflare account; **Add a domain**: `dubdesk.live`, Free plan.
2. Compare the records Cloudflare found with HANDOVER.md section 4: `A @`, `CNAME www`, and the
   Resend records (`TXT resend._domainkey`, `MX send`, `TXT send`, `CNAME rsend`). Add any that are
   missing. Set **every** record to **DNS only** (grey cloud) for now: the site stays on Render.
3. GoDaddy > the domain > Nameservers > Change > enter the two names Cloudflare gives. Wait until
   Cloudflare says **Active** (minutes, at most 48 hours). Then send yourself a password link
   from the live site: email must still arrive.
4. Cloudflare > SSL/TLS > Origin Server > **Create Certificate**: hostnames `dubdesk.live` and
   `*.dubdesk.live`, 15 years. Keep the certificate and the private key (the key is shown only
   once) in the client's password manager. They go onto the server in step 6.

Why Cloudflare: the server is reachable only from Cloudflare (the security group lets nothing else
in), attacks are absorbed before they reach it, and the visitor's address comes from Cloudflare's
own header, which a visitor cannot fake. The price: Cloudflare's list of addresses is copied into
`infra/aws/variables.tf` and `deploy/aws/Caddyfile`; if Cloudflare adds ranges (rare), update both.

Without Cloudflare (simpler, no shield): leave the domain at GoDaddy; in `terraform.tfvars` set
`web_ingress_cidrs = ["0.0.0.0/0"]`; in `.env` set `TLS=` an email address (Caddy then gets a
Let's Encrypt certificate itself); at the move, point GoDaddy's `A @` at the Elastic IP (lower its
TTL to 600 seconds a day before).

## 4. Create the AWS resources

On your computer, from the repository:

```sh
cd infra/aws
cp terraform.tfvars.example terraform.tfvars   # alarm_email, admin_iam_users
terraform init
terraform plan -out ccp.tfplan                 # read it: about 65 to add (30 are Cloudflare rules)
terraform apply ccp.tfplan                     # about 10 minutes (the database is the slow part)
terraform output
```

Keep `infra/aws/terraform.tfstate` private and backed up: it holds the database password
(infra/aws/README.md, "State"). AWS emails `alarm_email` a confirmation link: click it, or no
alarm arrives.

## 5. First boot and the deploy key

The server sets itself up at first boot (Docker, git, the CloudWatch agent, the `ccp` user and its
deploy key), in about five minutes.

1. EC2 console > Instances > `ccp-server` > **Connect** > Session Manager > Connect (or
   `terraform output -raw shell_command`).
2. `sudo cat /home/ccp/.ssh/deploy_key.pub`
3. GitHub > the repository > Settings > Deploy keys > **Add deploy key**: title `aws-server`, paste
   the key, **Allow write access OFF**.
4. `sudo ccp-bootstrap`. It ends with `bootstrap: done`. The code is now in `/opt/ccp`, and the
   timers are installed (they do nothing until the first deploy in step 7).

`sudo cat /var/log/ccp-bootstrap.log` shows what the first boot did.

## 6. Settings and secrets

The secrets live in one file on the server, `/opt/ccp/deploy/aws/.env`, owner `ccp`, mode 600. Only
root and `ccp` can read it, and `ccp` can run Docker, which is as good as root: so in effect it is
a root-only file. Not AWS Parameter Store: with one server and one operator that adds an IAM rule
and a script to fetch them, and the values end up in the containers' settings anyway. Keep a copy
of `DATA_ENCRYPTION_KEY` and `SECRET_KEY` in the client's password manager: without them stored
phone numbers cannot be read, and the file goes if the server is ever replaced.

```sh
sudo -iu ccp
cd /opt/ccp/deploy/aws
cp env.example .env && chmod 600 .env
nano .env
```

Fill it in; every line says where its value comes from:

- From `terraform output -raw env_lines` (on your computer): `DB_HOST`, `STORAGE_BUCKET`,
  `STORAGE_ENDPOINT_URL`, `STORAGE_REGION`, `AWS_LOG_GROUP`, `AWS_REGION`.
  `POSTGRES_PASSWORD` = `terraform output -raw db_password`.
- From Render (`ccp-api` > Environment): `SECRET_KEY`, `DATA_ENCRYPTION_KEY` (both must be the
  same as on Render), `SMTP_HOST`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `EMAIL_FROM`, `ALERT_EMAIL`,
  the four `TXCONTACT_*` logins.
- `TLS=/certs/origin.pem /certs/origin.key`, then paste the Origin Certificate from 3.3:
  `nano certs/origin.pem` (the certificate), `nano certs/origin.key` (the private key),
  `chmod 600 certs/*`.
- Leave `ADMIN_EMAIL` and `ADMIN_PASSWORD` empty: the copied database already has the Super Admin.
- `STORAGE_ACCESS_KEY_ID` and `STORAGE_SECRET_ACCESS_KEY` stay empty (the server's role), unless
  you use the fallback in section 9.

## 7. First deploy (a trial on the empty database)

As `ccp`, in `/opt/ccp`:

```sh
deploy/aws/deploy.sh
```

The first build takes 5 to 10 minutes. It ends with `deploy: <commit> is live`. Then:

```sh
curl -sk --resolve dubdesk.live:443:127.0.0.1 https://dubdesk.live/api/v1/version
curl -sk --resolve dubdesk.live:443:127.0.0.1 https://dubdesk.live/health/ready
```

The second must say `"status":"ready"` (database, Redis and file storage all answer). Nobody can
sign in yet: the database is empty until the move. From now on the timer deploys every push to
`main` by itself (section 10.1).

## 8. The move from Render

Plan a window of one to two hours (the database copy is minutes; the last file copy depends on
how much came in since 8.1). Tell the users: no recording, calls or changes during the window.

### 8.1 The day before: the bulk of the files

As `ccp`, in `/opt/ccp`, with the Wasabi key (typed, not shown, not stored):

```sh
read -rs SRC_ACCESS_KEY_ID; read -rs SRC_SECRET_ACCESS_KEY
export SRC_ACCESS_KEY_ID SRC_SECRET_ACCESS_KEY
deploy/aws/copy_files.sh
```

It copies `callrec57/staging/` into the new bucket under the same keys (with each file's type and
the app's SHA-256 label) and ends with `copy: counts, sizes and checks match`. Running it again
copies only what is new.

### 8.2 Start of the window: stop Render

1. On the AWS server: `sudo systemctl stop ccp-deploy.timer` (no automatic deploy in the window).
2. Render dashboard: **Suspend** `ccp-web` (the site goes offline), then `ccp-worker` and
   `ccp-api` (nothing writes to the database any more). Work left half-done (a recording in
   processing, a call recording not fetched yet, an export) is picked up again on AWS by the
   app's own recovery sweep.
3. Render > `ccp-db` > its inbound IP rules (Access Control / Networking): **add** the Elastic IP
   as `<ip>/32`, nothing wider. This is the only way in: Render's database refuses all outside
   connections (`ipAllowList: []` in `render.yaml`), and Render's own services have no `pg_dump`.
   The copy runs over TLS. Do not sync the Render Blueprint in the window (it would empty the list
   again).
4. Copy `ccp-db` > Connect > **External Database URL**.

### 8.3 Copy the database

As `ccp`, in `/opt/ccp`:

```sh
read -rs RENDER_DB_URL; export RENDER_DB_URL     # paste the External Database URL
deploy/aws/copy_database.sh                      # type COPY when asked
```

It stops the app on AWS, empties the RDS database, copies Render's with `pg_dump | pg_restore`
(over TLS), then compares every table on both sides: the number of rows and a checksum of all its
rows. It must end with `copy: all N tables match (rows and checksums)`. If not: run it again; the
copy replaces everything each time.

### 8.4 Copy the last files

Same as 8.1 (the keys are still set in this shell): `deploy/aws/copy_files.sh`. Must end with
`copy: counts, sizes and checks match`. For a byte-by-byte comparison as well (downloads every
file from both sides; slow): `deploy/aws/copy_files.sh check --download`.

### 8.5 Start on AWS; check before the switch

```sh
deploy/aws/deploy.sh                                             # migrations, then the app starts
curl -sk --resolve dubdesk.live:443:127.0.0.1 https://dubdesk.live/health/ready   # "ready"
deploy/aws/compose.sh exec -T api python -m app.cli verify-assets --deep 20
unset RENDER_DB_URL SRC_ACCESS_KEY_ID SRC_SECRET_ACCESS_KEY
```

`verify-assets` checks that every file the database knows is in the bucket with the right size and
SHA-256 label, and downloads 20 to hash them again. Exit code 0 means all good.

### 8.6 Switch the address

Cloudflare > `dubdesk.live`:

1. DNS: `A dubdesk.live` -> the Elastic IP, **Proxied** (orange cloud). `www`: `CNAME www ->
   dubdesk.live`, Proxied (the server sends `www` to the bare address, as Render did).
2. SSL/TLS > Overview: **Full (strict)**. SSL/TLS > Edge Certificates: **Always Use HTTPS** on.

The change works within a minute or two.

### 8.7 Checks

1. `https://dubdesk.live/` opens; `https://dubdesk.live/api/v1/version` answers.
2. Sign in as Super Admin (password, then the authenticator code).
3. **System status**: Ready; database, Redis and file storage answer; **Needs attention**: nothing
   new.
4. Open a project and a task; **play an old recording** (copied from Wasabi). In the browser's
   developer tools the audio comes from `ccp-recordings-...s3.ap-south-1.amazonaws.com`.
5. Make a 10-second face-to-face test recording: it is processed and plays.
6. **Export**: a project's Export tab, audio of one task: the ZIP downloads and opens.
7. **Phone calls** page opens and shows phone calls as set up (TxContact logins work). One test
   call, if the client agrees (no real call has been made yet).
8. **Email arrives**: Forgot password (or Send password link) to your own account; it comes from
   `no-reply@dubdesk.live`.
9. **Audit log**: your sign-in shows your own public address (not a 172.x or Cloudflare address).
10. CloudWatch: log group `/ccp/app` has the streams `api`, `worker`, `web`, `caddy`; every alarm
    is OK (the disk alarm must not stay "Insufficient data" after 10 minutes).
11. `sudo systemctl start ccp-deploy.timer` (automatic deploys again). After the next push to
    `main`: `journalctl -u ccp-deploy -n 50` shows it deployed.

### 8.8 Close Render's door

Render > `ccp-db` > inbound IP rules: **remove** the Elastic IP (as soon as 8.3 has passed).

### 8.9 One week with Render as the fallback

Leave the Render services suspended and the Render database and the Wasabi files as they are.
Going back (only if AWS fails badly): Cloudflare `A dubdesk.live` back to Render's address (DNS
only, grey cloud), resume the three Render services. Anything written on AWS after the switch is
not on Render: copy it back (the same tools the other way; no script is written for that) or
accept losing it.

### 8.10 Shut Render down

After a week without problems:

1. Render > `ccp-db`: take a last backup (export) and keep it with the client.
2. Delete `ccp-web`, `ccp-api`, `ccp-worker`, `ccp-redis`, `ccp-db` (and the Blueprint).
3. Wasabi: keep `callrec57` a few weeks more as an extra copy (Wasabi charges every stored file
   for at least 90 days anyway), then delete it. Delete the Wasabi key used for the copy.
4. Update DEPLOYMENT.md, OPERATIONS_RUNBOOK.md and HANDOVER.md: AWS is the live copy.

## 9. S3 through the server's role (done)

The app reaches S3 with the server's own IAM role when `STORAGE_ACCESS_KEY_ID` and
`STORAGE_SECRET_ACCESS_KEY` are both empty (`Settings.storage_keys`, test
`test_storage_keys_are_both_or_neither`). Leave them empty on AWS. `storage_user_fallback` stays
`false`; it is only for a host without the role.

## 10. Daily running

As `ccp` (`sudo -iu ccp`, then `cd /opt/ccp`) unless it says `sudo`.

### 10.1 Deploys

Every push to `main` goes live by itself, as on Render: `ccp-deploy.timer` asks GitHub every
minute (read-only deploy key); when `main` moved, `deploy/aws/deploy.sh` pulls, builds new images
while the old containers keep serving (5 to 10 minutes), runs the migrations, then swaps the
containers. The API is away for a few seconds during the swap (Cloudflare shows its error page;
the recorder keeps retrying each audio part until it is stored). A push that changes no image (documents only) restarts
nothing. A failed deploy leaves (or puts back) the running version, writes `deploy: FAILED` and
emails the alarm. Like Render, it does not wait for CI.

- What happened: `journalctl -u ccp-deploy -n 100`; the short history: `/var/log/ccp/operations.log`.
- Now, by hand: `deploy/aws/deploy.sh` (also after changing `.env`).
- What runs: `deploy/aws/deploy.sh status`.
- Pause automatic deploys: `sudo systemctl stop ccp-deploy.timer` (`start` to resume).

### 10.2 Rollback

```sh
deploy/aws/deploy.sh rollback          # the previous deploy's images
deploy/aws/deploy.sh rollback <tag>    # any kept one: deploy/aws/deploy.sh status lists them
```

The last three builds are kept. Migrations are not undone (OPERATIONS_RUNBOOK.md 2.1). The timer
deploys again at the next push, so a revert pushed to `main` is the lasting fix.

### 10.3 Logs

- CloudWatch > Log groups > `/ccp/app` > stream `api`, `worker`, `web`, `caddy`, `redis`
  (30 days). Logs Insights searches them.
- On the server: `deploy/aws/compose.sh logs -f --tail 100 api worker`.

### 10.4 Alarms

Emailed to `alarm_email`: server status check failed; CPU above 85% for 15 minutes; disk above
80% (`docker system df`; old images and build cache go after each deploy); database free space
under 2 GB (it grows by itself to 100 GB); a deploy or the backup FAILED. The app's own alerts
(storage, Redis, stuck recordings, calls waiting) still go to `ALERT_EMAIL`.

### 10.5 Backups and restore

- **RDS automated backups**: every day, kept 7 days; restore to any minute in that time (RDS
  console > `ccp-db` > Actions > Restore to point in time). That makes a **new** database: put its
  address in `DB_HOST` in `.env`, then `deploy/aws/deploy.sh`.
- **The app's own dumps** (`ccp-backup.timer`, daily at 02:00 India time): `pg_dump` of RDS,
  stored by the app in the bucket under `staging/backups/db/` with its SHA-256, 30 days kept. A
  second copy that outlives the RDS instance. List: `deploy/aws/backup.sh list`. Restore:
  `deploy/aws/backup.sh restore backups/db/ccp-<time>.dump` (checks the checksum, stops the app,
  replaces the database, migrates, starts the app).
- **Files**: S3 keeps a deleted or overwritten file for 30 days (versioning); bring one back in
  the S3 console (Show versions). After a restore of the database, recordings stored after the
  backup have files but no rows: `python -m app.cli storage-orphans` lists them.

### 10.6 Updates and reboots

Ubuntu installs security updates by itself but does not reboot. Once a month, in a quiet hour,
if `/var/run/reboot-required` exists: `sudo reboot`. Everything starts again by itself (a minute
or two). RDS takes its minor updates in the Sunday window (02:30 India time). The app's images
are rebuilt with every deploy.

### 10.7 Secrets

All in `/opt/ccp/deploy/aws/.env` (section 6). To change one: edit `.env`, then
`deploy/aws/deploy.sh` (only the containers whose settings changed restart). The database
password: change it in RDS (Modify) and in `.env` together.

## 11. Making it cheaper later

- A one-year Savings Plan for the server and a reserved instance for the database: about 30 to 40%
  less on both, once the size has proved right.
- Graviton (`t4g.medium` server): about 20% less than t3.medium; the images then build for ARM
  (not tried).
- A smaller server (`t3.small`, 2 GB) if memory stays low (CloudWatch: `CCP` > `mem_used_percent`).
- The database in a container on the server instead of RDS (as in D-096): about 30 less, but the
  backups, patches and disk are then ours to watch.
- Old recordings to S3 Standard-IA by a lifecycle rule, once the client's retention rules are
  settled (cheaper to keep, costs more to read).

## 12. What is not tested

Everything in AWS: Terraform has never been applied; the first boot, the deploy timer, the
CloudWatch agent's figures (the disk alarm depends on them), container logs to CloudWatch, the
database copy from Render, the file copy from Wasabi, the Origin Certificate behind Cloudflare,
the restore. What is tested: the configuration's syntax (`terraform validate`), the scripts'
syntax, and on every push CI builds and starts this set-up with a stand-in database behind HTTPS.

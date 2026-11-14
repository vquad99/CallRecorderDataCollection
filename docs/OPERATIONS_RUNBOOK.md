# Operations runbook

For the person who runs the live copy. Three parts: taking a bad release back (rollback), getting
the service back after a loss (disaster recovery), and what to do when something is wrong
(incidents). Requirement OPS-008; alerts are OPS-006 (DECISIONS D-109).

**Not rehearsed.** Nobody has walked through these steps on the live copy yet (TM-OPS-04). Steps
marked NOT VERIFIED describe how the hosting provider says it works, or what the code does, without
having been tried there. Rehearse sections 2 and 3 once on a quiet day and correct this file.

## 1. What runs where

The live copy is on Render (Blueprint `ccp-staging`, Singapore), address `https://dubdesk.live`.
See DEPLOYMENT.md section 3 for the settings.

| Part | Render service | What it does |
|---|---|---|
| Web server | `ccp-web` (public) | Serves the application, passes `/api` to the API |
| API | `ccp-api` (private) | The application; also looks after stalled work every minute and checks itself |
| Worker | `ccp-worker` | Turns uploads into delivery files, fetches call recordings, makes export bundles |
| Queue | `ccp-redis` | Work queue and sign-in limits |
| Database | `ccp-db` (PostgreSQL 16) | Everything except the audio files |
| Files | Wasabi bucket (outside Render) | Recordings, originals, export bundles, backups |

Where to look first:

- **System status** page in the application (Super Admin): the parts, and **Needs attention**.
- Render dashboard: each service's **Logs** and **Events** (deploys).
- Commands run in the **Shell** of `ccp-api` (Render dashboard > `ccp-api` > Shell):
  `python -m app.cli <command>`. The list is in DEPLOYMENT.md section 5.

## 2. Rollback: taking a bad release back

Every push to `main` deploys by itself. Before a deploy goes live, `python -m app.cli
prepare-deploy` runs the database migrations.

**Preferred: go forward with a revert.** It keeps the history and automatic deploys as they are.

1. Find the bad commit: `git log --oneline -5`.
2. `git revert <commit>` (several: oldest last), push to `main`.
3. Watch CI and the three Render services deploy. Then do the checks in 2.3.

**Faster: Render's own rollback** (NOT VERIFIED on this account).

1. Render dashboard > `ccp-api` > Events > the last good deploy > **Rollback**. Do the same for
   `ccp-worker` and `ccp-web`, to the same commit.
2. Render may switch automatic deploys off after a rollback: check each service's settings and
   switch them on again once a fixed commit is on `main`.

### 2.1 The database after a rollback

Migrations are not undone by a rollback. Releases so far only **add** tables and columns, and
older code runs with a newer database. So normally: leave the database alone.

Only when older code cannot run with the newer database: take a backup first (section 3.1), then
in the `ccp-api` shell `python -m alembic downgrade <revision>` to the revision the older code
expects (each file in `backend/app/db/migrations/versions/` names its `down_revision`). A
downgrade that drops a table loses what was in it.

### 2.2 Settings changed in `render.yaml`

Those apply only after Render dashboard > Blueprints > `ccp-staging` > **Manual sync**. To take
one back, revert the file and sync again.

### 2.3 Checks after any rollback or release

1. `https://dubdesk.live/` opens; `https://dubdesk.live/api/v1/version` answers.
2. Sign in as Super Admin (password, then the authenticator code).
3. **System status**: Ready; **Needs attention**: nothing new.
4. Open a project, a task, and play one recording.
5. Dashboard and Phone calls pages open.

## 3. Disaster recovery

### 3.1 The database is lost or damaged

What exists today:

- **Render's own recovery for `ccp-db`**: NOT VERIFIED. Which backups the current plan keeps, and
  for how long, has not been checked. **Check it now, before it is needed**: Render dashboard >
  `ccp-db` > Recovery. Write the answer here.
- **The platform's own dumps** (`backups/db/` in the file storage): made by
  `infra/backup/backup.sh`, which is written for the Docker Compose set-up (the AWS copy runs it
  daily). **On Render no dump is scheduled** (OPS-004 open). Until one is, Render's recovery is
  the only backup of the live database.

To restore on Render (NOT VERIFIED): Render dashboard > `ccp-db` > Recovery > restore to a point
in time. Render makes a new database: point `ccp-api` and `ccp-worker` at it (the Blueprint's
`fromDatabase` does this when the name is kept), then run the checks in 2.3.

To restore on the Docker Compose set-up: `infra/backup/restore.sh <key>` (it checks the dump's
checksum, stops backend and worker, restores, starts them again). List dumps with
`python -m app.cli backup-list`.

After any restore: recordings stored after the backup was taken have files but no rows.
`python -m app.cli storage-orphans` lists them. Tell the project admins which tasks must be
checked.

### 3.2 Files are lost (the Wasabi bucket)

Recordings exist only in the bucket. **There is no second copy** (B-14 open: a second bucket with
its own keys is not set up). A deleted or lost file cannot be brought back.

- Find out what is missing: `python -m app.cli verify-assets` (every file's presence, size and
  checksum; `--deep N` downloads N and hashes them).
- A single file deleted by mistake: ask Wasabi support at once whether the bucket has versioning
  or a recovery window (NOT VERIFIED).
- The database keeps every recording's details, so the list of what was lost is exact.

### 3.3 The encryption key is lost (`DATA_ENCRYPTION_KEY`)

Phone numbers, email addresses of participants and two-step secrets are encrypted with it.
Without it they cannot be read; nothing else is affected. A copy is kept where DEPLOYMENT.md
section 3 says. If it is truly lost: set a new key, ask every admin to set up two-step sign-in
again (`reset-mfa`), and re-enter participants' contact details.

To change the key on purpose: put the new key **first** in `DATA_ENCRYPTION_KEY` (comma, then
the old one), deploy, run `python -m app.cli rotate-keys`, then remove the old one.

### 3.4 Render is down, or the account is lost

1. A new Render account (or the AWS set-up: `deploy/aws/README.md`).
2. New Blueprint from this repository's `render.yaml`; enter the values marked `sync: false`
   (DEPLOYMENT.md section 3): the **same** `DATA_ENCRYPTION_KEY` and the same Wasabi keys and
   bucket.
3. Restore the database (3.1) before the first sign-in.
4. Point the domain at the new `ccp-web` (GoDaddy: the `A` and `CNAME` records in DEPLOYMENT.md).
5. Checks in 2.3.

### 3.5 An admin cannot sign in

- Forgot the password: **Forgot password** on the sign-in page, or another Super Admin clicks
  **Send password link** on the user's page.
- Lost the authenticator: another Super Admin clicks **Reset two-step sign-in** on the user's
  page. The last Super Admin: `python -m app.cli reset-mfa <email>` in the `ccp-api` shell.
- No Super Admin left: set `ADMIN_EMAIL` and `ADMIN_PASSWORD` on `ccp-api`, then
  `python -m app.cli create-admin --reset-password`.
- Two-step sign-in itself is broken for everyone: set `REQUIRE_ADMIN_MFA=false` on `ccp-api`
  (it restarts), fix, and set it back to `true`.

## 4. Incidents: what to do when something is wrong

The platform looks at itself every minute. What it finds is on **System status > Needs
attention**, and it emails the addresses in `ALERT_EMAIL` (set on `ccp-api`; unset: no email):
once when something new is wrong, again every 24 hours while anything is still wrong, and once
when all is clear.

| What it says | Likely cause | What to do |
|---|---|---|
| File storage does not answer (`STORAGE_UNREACHABLE`) | Wasabi is down, or the keys were changed | Check Wasabi's status page and the keys on `ccp-api`. Nothing can be recorded, played or exported until it answers again |
| The work queue (Redis) does not answer (`REDIS_UNREACHABLE`) | `ccp-redis` is down or full | Render dashboard > `ccp-redis`. Uploads wait and are processed when it is back (the API sends them again every minute) |
| N recordings could not be processed (`RECORDINGS_FAILED`) | A damaged upload, or the worker ran out of memory or disk | The recorder page says **Processing failed**. The moderator records the conversation again (there is no button to process the same upload again). Many at once: look at the `ccp-worker` logs |
| N recordings have waited for processing (`RECORDINGS_STUCK`) | The worker is not running | Render dashboard > `ccp-worker`: is it live? Restart it. `python -m app.cli recover-recordings` sends everything waiting again |
| N phone calls wait for a person (`CALLS_NEED_PERSON`) | The provider listed several calls or none, or the file could not be fetched | **Phone calls** page > Show: Needs a person. Open the task: pick the right call, or **Look for the recording again** |
| N exports failed (`EXPORTS_FAILED`) | A stored file did not match its checksum, or storage was down | Project > Export: the reason is under the export's name. A checksum mismatch means a stored file is damaged: `python -m app.cli verify-assets` |

Other situations:

| What you see | What to do |
|---|---|
| The site does not open | Render dashboard: are `ccp-web` and `ccp-api` live? Read their logs. A deploy in progress takes a few minutes. If a deploy broke it: section 2 |
| Nobody can sign in | **System status** cannot be reached either: look at the `ccp-api` logs for the database. If the database is down: Render dashboard > `ccp-db` |
| "Too many failed sign-in attempts" for one person | Wait 15 minutes. For everyone at once from one office: the limit is per address too; it clears by itself |
| Emails do not arrive | Resend dashboard (the sending service): is the key valid, is the domain still verified? The API logs say `email` errors. Password links can be sent again from the user's page |
| Phone calls cannot be placed | The task page shows what TxContact answered. An empty answer means the dialer login is refused: check `TXCONTACT_DIALER_USERNAME` / `PASSWORD`. See docs/integrations/txcontact/API_NOTES.md |
| The site is slow | `ccp-api` logs: lines `slow_request` and `slow_query` name the request and its time. More web processes: `WEB_CONCURRENCY` |

### 4.1 A security incident (an account misused, data seen by the wrong person)

1. **Stop it:** the user's page > **Disable account**, and **Sign out everywhere**. For a
   suspected stolen admin session also **Reset two-step sign-in**.
2. **See what happened:** **Audit log**, filtered by that person and by day. Every sign-in,
   download link, export and change is there with the address it came from.
3. **Close the door:** if a secret may be known (a password in a chat, a key in an email), change
   it at its source (TxContact, Wasabi, Resend) and on `ccp-api`. The TxContact dialer password
   that arrived by email on 2026-11-13 should be changed in any case.
4. **Tell:** the project's owner and, where participants' personal data is concerned, whoever is
   responsible for them under the project's consent text. Write down what was seen, when, and
   what was done.

### 4.2 After any incident

Add a line to DECISIONS.md (what happened, what was changed) and correct this runbook where it
was wrong or missing.

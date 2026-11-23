# Security

Status: sections 1, 2, 6 and 9 implemented and tested (Phases 2-4, Option B); the rest planned. Requirement IDs: SEC-*, AUTH-*, ROLE-*, STOR-*,
TEL-012..013, TEL-035, PWA-004, PWA-007, OPS-003.

## 1. Authentication

- Server-side sessions; session token in an HttpOnly, Secure (outside development), SameSite=Strict cookie;
  only its SHA-256 is stored. CSRF double-submit: a readable `csrf_token` cookie must equal the
  `X-CSRF-Token` header on every POST/PUT/PATCH/DELETE under /api/v1 (SEC-007). No long-lived secrets in localStorage (AUTH-013).
- Passwords: Argon2id with per-password salt; never logged or returned (AUTH-006, AUTH-015).
- Idle and absolute session expiry, configurable; revocation per session and per user (AUTH-005, AUTH-010).
- Failed-login throttling per account and per IP, counted in PostgreSQL `login_attempts` (AUTH-009, D-027).
  The count for one address is read under a lock for that address, so a burst sent at once cannot
  pass it. Wrong authenticator codes given with the right password are counted per account from
  every address: 10 per window. Then sign-in and turning two-step sign-in off wait out the window.
  The owner is emailed at the first wrong code in a window (D-155).
- Password reset: random token, stored hashed, single use, short expiry; same response whether the email
  exists or not (AUTH-004).
- Optional TOTP MFA (AUTH-008); each code is accepted once only (D-050). Spaces in a typed code are
  ignored; turning it on ends the account's other sessions (D-155).
- Password checks through a signed-in session (password change, MFA off) are throttled like sign-in (D-050).
- Audit events: login success/failure, logout, password change/reset, disable/enable, role and
  membership changes (AUTH-014, USER-007). A failed sign-in whose typed text is not an account
  keeps only a keyed fingerprint of it in the audit log, never the text (a password pasted into
  the email box is never stored there, D-155).
- Signing out reaches every tab of the browser (BroadcastChannel `ccp-auth`): the other tabs show
  the sign-in page at once, and a moderator's phone line goes offline in each (D-133). Signing in
  in one tab opens the others (D-155).
- A sign-out whose request fails (network, 5xx, 429) keeps the person signed in on screen and says
  so: "You are still signed in: the server could not be reached. Try Sign out again." Only a
  confirmed sign-out or a 401 clears the page, so a shared computer is never left with a live
  session behind a sign-in page (D-155).
- Only a 401 signs a page out. A server that cannot be reached at start shows "Cannot reach the
  server" and retries every 5 s, so nobody signs in again and adds a session (D-155).
- The idle warning comes 2 minutes before the page's count (`last_seen_at` is written at most
  once a minute). Its check when the time is up is a background request (`X-Background-Request`),
  so it never extends a session; with the session kept alive by another tab it asks at most once
  a minute (D-155).
- Error references (request ids) show in form messages only for server faults (5xx). A page that
  fails to display never shows the error text or stack (D-155).

## 2. Authorization

- Permission matrix: ARCHITECTURE.md section 5.
- One central permission registry; every route declares its permission; a FastAPI dependency checks
  role permission, project membership and assignment before the handler runs (ROLE-009/010).
- Services filter every query by the caller's projects; object IDs are UUIDs; a foreign ID returns 404.
- Frontend filtering is for usability only (ROLE-011). TA-ROLE-01 calls every protected route as every role.

## 3. Personal data

- Collect only what the project needs (PART-010).
- Phone numbers encrypted at application level, keyed hash for duplicate detection, masked unless
  the caller may see contact details (PART-008, D-035, D-036).
- Consent records separate from profiles, readable only by permitted roles (PART-006, SEC-010).
- Exports exclude phone numbers by default; including personal data needs an explicit grant and is
  audited (EXP-004).
- Retention rules per project and asset kind, applied by the platform once an hour to files of
  closed tasks only (PROJ-01, D-155); deletion jobs and requests audited (STOR-009, PART-009).
- `participant.corrected` entries hold no participant names and no native districts. They say
  which fields changed (`name_changed`, `phone_changed`, `email_changed`, `speaker_details_changed`)
  and keep only the language and dialect. Email addresses appear only as keyed fingerprints
  (HMAC-SHA256 with the secret key, first 16 hex characters) in `participant.corrected` (when the
  email changes), `participant.portal_link_emailed` (`to`) and `consent.self_recorded`
  (`emailed_to`): the log proves where a consent link went without holding an address. Entries
  written before this change keep what they recorded: the audit log is append-only (trigger
  `audit_logs_no_update_delete`, migration 0002) and is not rewritten. Removing a participant also
  renames their removed address proofs to `address_proof` (D-155).
- Consent: a signed consent form cannot be replaced while a task with the person is at Audio QC,
  and a moderator replaces it only before QC or at a QC send-back (SECB-01). An online answer
  records the masked address its link was emailed to (SECB-02), so an answer given through an
  address staff put on file for a while shows in the consent history and the audit log. A QC
  pass, and an approval, needs both people's consent as it counts at that moment (SECB-03): a
  project switched from signed forms to online consent while a task was in QC cannot have it
  approved without consent (D-155).
- Evidence and test data never contain real personal data (GEN-006).
- AI transcription sends participant audio to Deepgram only for projects that switch it on (ASR-010);
  whether the client and consent text allow this is open (DECISIONS.md B-07).

## 4. Files and storage

- Private bucket, public access blocked, server-side encryption, versioning (STOR-001, STOR-013).
- Downloads only by short-lived signed URL issued after a permission check (STOR-005); verified on
  Wasabi: unsigned requests 403, expired links 403 (docs/evidence/phase4/wasabi_checks.txt).
- SHA-256 on upload and after storage; mismatch fails the upload (STOR-006).
- Service worker never caches audio or API responses with user data (PWA-004); logout clears caches
  holding user data (PWA-007).

## 5. Webhooks and provider calls

- Signature verified before any processing; unsigned or invalid events rejected and logged (TEL-012).
- Unique provider event ID; idempotent processing; dead-letter queue for permanent failures (TEL-013, TEL-033).
- Recording downloads only from the provider's allowed hosts through the authenticated provider API,
  never from an arbitrary URL in a webhook body (TEL-035).
- Provider credentials only in the secret manager; `provider_accounts` stores a reference (TEL-025).
- As built for TxContact (D-101): no webhooks exist, so the first three points do not apply; the
  recording is downloaded only from `TXCONTACT_BASE_URL` by a checked file name, redirects are
  refused, and the logins are environment secrets (`TXCONTACT_*_PASSWORD`), never in the database.
  TxContact's dialer takes its password in the address: the platform never logs that address.
  A moderator's own seat password (their Chirp sign-in, D-130) is the one TxContact password in the
  database: encrypted like phone numbers, in no answer, log or audit entry, and shown only on
  request to a Super Admin or that moderator, each time audited.

## 6. Web application hardening

- Input validation on every endpoint (pydantic schemas) (SEC-006).
- Output encoding by React; no raw HTML from user content (SEC-013).
- Secure headers: HSTS, Content-Security-Policy, X-Content-Type-Options, frame-ancestors none,
  Referrer-Policy, Permissions-Policy allowing microphone only for the app origin (SEC-013).
- Rate limits on every /api/v1 request: per session, or per IP when signed out (SEC-005, D-039).
- Request limits: 413 above 2.5 MB (audio chunks 8 MB; a participant's scanned document 10 MB, only
  PDF, JPEG or PNG by its first bytes, D-144); NUL characters refused with 422; every API
  answer is `no-store` and carries `default-src 'none'` (D-052).
- Web server content policy allows media only from the site and the storage service named by
  `MEDIA_ORIGINS` (D-061); security headers stay on cached files (caching uses `expires`).
- CORS allowlist from configuration (FND-011).
- Spreadsheet downloads: CSV/TSV cells that start with `=`, `+`, `-`, `@`, a tab or a carriage
  return get a `'` in front (`core/csvio.safe_cell`); numbers the server computed are written as
  numbers. The Progress tab's Excel download (`core/xlsx.py`) writes all text as inline strings,
  never formulas, and drops characters XML refuses. It is limited to the people who manage the
  project, and every download is audited (`project.exported`). Project names are one line, and
  email subjects are made one line, so no header can carry a line break (D-155).
- Downloads (project reports, the Progress download, payments, calls and participant CSVs, task
  ZIPs) are fetched by the page with the session cookie (`apiDownload`), never as plain links. A
  refusal is shown on the page, and a 401 signs the page out like any other request (AUTH-016,
  D-155).
- Task status changes lock the task row, so a Cancel and a Start sent at once can never both
  succeed, and a cancelled task cannot come back (TASK-05, D-155).

## 7. Secrets and supply chain

- Secrets only in environment / cloud secret manager; `.env.example` holds names and safe values (FND-025).
- Secret scanner and dependency vulnerability scan in CI (SEC-004, SEC-015). Both run even when an
  earlier step of their job failed. Dependabot (`.github/dependabot.yml`) proposes updates of
  images, actions and packages every week; the uv version pins are moved by hand (D-155).
- Pinned dependencies with lockfiles (ARCH-003).

## 8. Infrastructure

- TLS everywhere; encryption at rest for database, storage and backups (SEC-002, SEC-003).
- Least-privilege cloud roles per component (SEC-014). On AWS the server's role (S3) is for the API
  and the workers. web (nginx) and caddy, which face the internet, are blocked from the instance
  metadata address (`deploy/aws/systemd/ccp-imds-guard.service`, D-155).
- Backups encrypted; restore tested (SEC-008).
- Audit log append-only; integrity reviewed (SEC-001).
- Monitoring, alerting and log retention (OPS-006).

## 9. Security test sweep (owner's test list, Option B, 2026-11-09)

Automated, in CI: `backend/tests/test_security_access.py`, `test_security_auth.py`,
`test_security_api.py` (evidence: docs/evidence/option_b/).

- Every API route has a written access rule; a new route without one fails the build.
- Every route called by all six roles plus an unassigned moderator, on the caller's project (result
  must match the rule) and on another project (must be refused exactly like an object that does not
  exist); no response to a project member contains the other project's identifiers; request bodies
  cannot pull in another project's participants, staff or tasks.
- CSRF refused on every state-changing route; malformed IDs give 422 on every route; no response
  carries a password, secret, token or encrypted field.
- Sessions: planted session IDs never used; tokens stored only as hashes; removed roles, project
  membership, administrator revocation and password reset take effect at the next request.
- Sign-in: identical answers for unknown, wrong and disabled accounts; unknown addresses cost a full
  password check; reset links ignore the request's Host header; authenticator codes single use; code
  and password guessing throttled.
- Input: 413 size limits (declared and streamed bodies), NUL characters, injection strings in every
  search and filter, server-owned fields (id, status, codes, roles) not settable by a client, errors
  never echo the submitted values, protective headers on 200/401/403/404/422/413 answers.

Found and fixed: consent history visible to any moderator in the project and storage totals to every
role (D-049); authenticator code replay and unthrottled password checks in a signed-in session
(D-050); server errors from NUL characters, no body size limit, cacheable API answers (D-052); a
server error when saving an unchanged language or retention list (fixed in the project service).
Each fix was checked by removing it and watching its test fail.

Not covered here: browser-side XSS and a web vulnerability scan (Phase 10, TM-SEC-02); TLS,
encryption at rest and cloud permissions (Phase 10).

## 9a. Independent review, 2026-11-10 (D-064)

A second, independent review of roles, sessions, the web server and operations found one high
issue (behind nginx every visitor shared nginx's address, so one person could block sign-in for
everyone), one medium (forgot-password timing showed which addresses have accounts) and eleven
low ones. All are fixed except two open owner decisions (B-14 backups in a separate, locked bucket
with an encryption key off the web servers; B-15 mandatory two-step sign-in for administrators).
Each fix has a test in `backend/tests/test_security_review.py` that fails without it. One item is
accepted as is: a duplicate phone number across projects is refused (one person keeps one
participant ID), which tells the caller the number exists; the refusal is audited.

## 9b. Participant personal page (D-067)

Public by design, so the limits are in the link: 256-bit secret, stored hashed, 30-day life,
replaceable and revocable, carried after `#` in the address and in a header to the API (so it is
in no access log), same answer for every link that does not work, rate limited per address, CSRF
checked on the consent answer. The page returns no names, phone numbers, staff, other speakers,
storage keys or audio. Creating and revoking links is audited.

## 9c. Third review, 2026-11-11 (D-088)

Three independent reviews (roles and business rules; sign-in, sessions and tokens; browser,
files, web server and dependencies) and a check of the live site from outside. No high
findings. Fixed, each with a test in `backend/tests/test_security_review_2.py` or next to the
code it changes:

- Password hashing used 64 MiB per sign-in: a burst of parallel sign-ins could exhaust the
  512 MB server. Now 19 MiB (OWASP minimum for Argon2id), at most two hashes at once per process,
  503 "busy" after 10 s.
- Parallel sign-ins could all pass the failure count, and one authenticator code could be used
  twice at the same moment: password and code checks for one account now run one at a time.
- Five wrong passwords from anywhere locked the real owner out: an account now locks for the
  address the failures came from, and for everyone only after ten times as many.
- Signing in to one's own account reset the address's failure count: it no longer does.
- An IPv6 visitor could use a new address per request: limits now count the whole /64.
- An authenticator code in another script's digits caused a server error: refused instead.
- One person could record a session and approve it by being assigned QC first and moderator
  second: refused both at assignment and at the decision, for every role.
- An admin could open a participant's personal link, answer "I agree" and approve the answer:
  links shown to staff are marked, the answer names the link, and the person who handed it out
  cannot review it; consent records say "link handed out by staff".
- An admin of one project could edit or remove a participant shared with another project:
  now only someone who manages every project the participant is in.
- Correcting a participant's email now ends the personal link mailed to the old address.
- Participant export: the dialect cell is protected against spreadsheet formulas; project
  languages are checked like a participant's own.
- A CSV line with more values than the header broke the whole upload: now a per-line error.
- The first-admin step of every deploy could bring back a renamed admin address with the stored
  password: it now runs only while no Super Admin exists.
- The encryption key can be rotated (`DATA_ENCRYPTION_KEY=new,old`, then `rotate-keys`).
- Web server: request bodies limited to 9 MB (was 50 MB); recordings may play only from this
  platform's own bucket (was any Wasabi bucket).

Checked on the live site: TLS 1.0 and 1.1 refused; HSTS, content policy and frame protection on
every answer; http and www redirect to https://dubdesk.live; session cookie HttpOnly, Secure,
SameSite=Strict; no API docs, dotfiles or server status pages exposed; other websites cannot
call the API (no CORS permission); a request carrying a forged visitor-address header is refused
by the hosting edge (Cloudflare error 1000). No known vulnerable package (npm audit, pip-audit).

Accepted, not changed: the web server's main process runs as root inside its container (its
workers do not; the unprivileged image lags one nginx patch release); the API trusts forwarded
addresses from the private network, where only this platform's own services run.

## 9d. Phone calls and site review, 2026-11-13 (D-103)

An independent read of the telephony code, a real-browser run of every flow against a stand-in
provider, and a check of the live site's answers. Fixed in this release:

| Finding | Fix | Test |
|---|---|---|
| A closed call could wait for ever (wrong recording login) and could not be cancelled, blocking the task | A search that keeps failing ends with a person after the fetch window; a call can be cancelled at every stage | test_telephony.py |
| An unexpected error while fetching left the call claimed and silent | Every error ends the step with the call waiting for its next try or shown to a person | test_telephony.py |
| A redial within two minutes could take the dropped call's recording | After a redial on the same seat the time window opens only 10 s before dialling | test_telephony.py |
| A download cut short was kept as the provider original | The length TxContact announced is checked; nothing of a failed try stays in storage | test_txcontact_adapter.py |
| A cancel during a download was overwritten by the finished recording | The call row is locked and looked at again before a recording is made final | test_telephony.py |
| A provider's call id or file name (may hold the caller's number) went into history, candidates and the details file | Shown and exported masked; choosing a candidate uses an opaque key | test_telephony.py |
| Nothing limited repeat dialling of one participant | 6 calls an hour for a task; a participant who refused consent is not called again | test_telephony.py |
| Redirects from the provider were followed with the sign-in token | Redirects are refused | test_txcontact_adapter.py |
| An audio error message could carry a path on the server | The reason only | test_telephony.py |
| `/.env`, `/.git/config` and any unknown file answered 200 with the app page | Hidden files and unknown files answer 404 (frontend/nginx.conf); pages still fall back to the app | tested with nginx 1.28 locally (docs/evidence/phase5) |
| No robots.txt; the private tool could be listed by search engines | `robots.txt` (Disallow all) and a `noindex` tag | - |

Checked and found in order on https://dubdesk.live (2026-11-13): Content-Security-Policy,
Strict-Transport-Security, X-Content-Type-Options, Referrer-Policy, Permissions-Policy and
frame-ancestors are sent on every answer; the API documentation is off; `/health/ready` is private;
API routes answer 401 without a session.

Authorization of the new routes is in the route table of tests/test_security_access.py (every
role against every route, own and foreign project). A Super Admin's "View as" session cannot
start, change or cancel a call (every change is refused while viewing).

## 9e. Who sees what, 2026-11-14 (D-104)

| Rule | Where it is kept | Test |
|---|---|---|
| Call figures and the calls CSV are for people who assign tasks (Super Admin, Project Admin); a moderator gets 403 and has only the list of their own calls | The routes need `tasks.assign`; the service checks it again | test_security_access.py, test_telephony.py |
| Everything about one participant (`/details`) is for people who manage participants in that project; other projects the person is in are named only when the caller may see them | The service checks `participants.manage` in the project | test_security_access.py, test_telephony.py |
| A project's tabs after Overview are for people who manage projects | The pages hide them; since D-112 the server also refuses the team list and the participant list to everyone else (403) | participants.test.tsx, journeys/boundaries.spec.ts, test_security_access.py, test_permissions.py |

## 9f. Exports, 2026-11-14 (D-105)

| Rule | Where it is kept | Test |
|---|---|---|
| Names, phone numbers and email addresses are not in an export unless asked for by someone with `participants.export` (Super Admin) | The selection is checked when the export is asked for, and again when a link is given | test_export_jobs.py |
| Original recordings only for people who manage the project | The same check | test_export_jobs.py |
| A bundle is handed only to someone who could have asked for it; a project that is not the caller's answers 404 | The link request re-checks the job's own choice | test_export_jobs.py, test_security_access.py |
| A download link works for 5 minutes; each one is audited; a bundle leaves storage after 24 hours | `SIGNED_URL_SECONDS`, `EXPORT_BUNDLE_HOURS`; the recovery sweep removes expired bundles | test_export_jobs.py |
| A stored file that no longer matches its checksum is never exported | Each file is hashed while it is copied; a mismatch stops the export and removes the half-made bundle | test_export_jobs.py |
| A table cell cannot run as a spreadsheet formula | Cells starting with `=`, `+`, `-`, `@` get an apostrophe | test_exports_zip.py |

## 9g. Two-step sign-in for admins, 2026-11-14 (D-106)

| Rule | Where it is kept | Test |
|---|---|---|
| A Super Admin or Project Admin without two-step sign-in can do nothing but set it up | Checked on every request, before anything else, in the same place that checks the session | test_admin_mfa.py, journeys/twostep.spec.ts |
| A role given later brings the rule at once; other roles are not asked | The same check reads the account's roles on each request | test_admin_mfa.py |
| Looking at the app as someone else needs the Super Admin's own two-step sign-in | The check is on the person who is really signed in | test_admin_mfa.py |
| A lost authenticator is reset only by people who manage users, never for one's own account, and ends every session of that person | `POST /users/{id}/mfa/reset`; audited as `user.mfa_reset` | test_admin_mfa.py, test_security_access.py |
| The last Super Admin has a way back that needs the server, not the application | `python -m app.cli reset-mfa <email>`; audited with no actor | test_admin_mfa.py |
| Turning two-step sign-in on ends every other session, so a session opened with the password alone never becomes a full admin session (D-155) | `service.mfa_confirm`; audit `auth.mfa_enabled` after `sessions_revoked` | test_admin_mfa.py |
| With the password, at most 10 codes per window from any number of addresses; the owner is emailed (D-155) | `MFA:<email>` rows in `login_attempts`, checked at sign-in and when turning it off | test_security_auth.py |
| A code typed as "123 456" works and is not counted as a failure (D-155) | `security.totp_step` | test_security_auth.py |
| A burst from one address checks no more passwords than its limit (D-155) | lock per address in `ensure_not_throttled` | test_security_review_2.py |
| A password typed into the email box never reaches the audit log (D-155) | `auth.login_failed` | test_auth.py |
| Signing out while viewing as someone is recorded as the Super Admin's own (D-155) | auth router | test_view_as.py |
| The emergency reset on the server signs the account out and voids unused links (D-155) | `cli.create_admin` | test_settings_seed_audit.py |

The set-up shows the authenticator link as a QR code made in the browser by the application's
own code (D-107): the secret is sent to no other service to draw it.

## 9h. The installable application, 2026-11-14 (D-110)

| Rule | Where it is kept | Test |
|---|---|---|
| The service worker keeps built files and the offline page only; nothing from `/api/`, no recording, no page | `frontend/pwa/sw.template.js`: it answers only GET requests for `/assets/` and the offline files, and pages only to pass them on | src/pwa/pwa.test.tsx; e2e/pwa.spec.ts (the browser's stores after loading) |
| Nothing private in the browser's own stores | The application keeps no token or personal data in local or session storage (the session is a cookie the page cannot read) | e2e/pwa.spec.ts |
| A new version never reloads a page by itself | The page reloads only after the person clicks Reload | src/pwa/pwa.test.tsx |
| The worker and the manifest come from the same address only | The site's rules (`default-src 'self'`) cover workers and manifests | checked with nginx 1.28 (docs/evidence/phase10/pwa_2026-11-14.txt) |

## 9i. Security audit in 14 categories, 2026-11-23 (D-160)

Access control, IDs in addresses, keys, payments, sign-in and codes, script injection, uploads,
environment and git exposure, and database queries, tested on a local copy with a few read-only
checks of the live site. No Critical, High or Medium finding; the 14 Low ones are fixed:

| Rule | Where it is kept | Test |
|---|---|---|
| An export is removed only by its maker or a project manager | `exports/jobs.py` `may_remove` | tests/test_security_review_4.py |
| A Super Admin is never added to a project by anyone else | `projects/service.py` `add_member` | same |
| A made-up session cookie buys no extra requests | `core/ratelimit.py`, `auth/deps.py` | same |
| Only the newest password link works; common and trivial passwords are refused | `auth/service.py`, `auth/passwords.py` | same |
| Strangers cannot lock an account out of an address it used | `auth/service.py` `_known_address` | same |
| Ids are encoded into API paths | `frontend/src/api/client.ts` `seg` | src/api/paths.test.ts |
| Names in emails stay on one line | `core/email.py` `one_line`, `users/service.py` | tests/test_security_review_4.py |
| Documents hold only their page; optional ClamAV scan | `core/filecheck.py`, `core/virus.py` | same |
| Days outside 2000-2100 are refused | `core/days.py` | same |
| The app's database role cannot change the audit log (when used) | `db/roles.py`, `cli.py grant-app-role` | same |
| Import previews do not reveal other projects' phone numbers; probing is limited and reported | `participants/service.py`, `operations/service.py` | same |

Still for the owner: the production bucket's privacy and key scope, the two test encryption keys
in git history against the live key, rotating the keys shared during setup, switching on the app
role and ClamAV (docs/DEPLOYMENT.md).

## 10. Open security questions

- Call-recording consent law and provider terms in India: NOT VERIFIED (DECISIONS.md B-10).
- Data-residency region: open (B-04).

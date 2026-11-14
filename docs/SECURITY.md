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
- Password reset: random token, stored hashed, single use, short expiry; same response whether the email
  exists or not (AUTH-004).
- Optional TOTP MFA (AUTH-008); each code is accepted once only (D-050).
- Password checks through a signed-in session (password change, MFA off) are throttled like sign-in (D-050).
- Audit events: login success/failure, logout, password change/reset, disable/enable, role and
  membership changes (AUTH-014, USER-007).

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
- Retention rules per project and asset kind; deletion jobs and requests audited (STOR-009, PART-009).
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

## 6. Web application hardening

- Input validation on every endpoint (pydantic schemas) (SEC-006).
- Output encoding by React; no raw HTML from user content (SEC-013).
- Secure headers: HSTS, Content-Security-Policy, X-Content-Type-Options, frame-ancestors none,
  Referrer-Policy, Permissions-Policy allowing microphone only for the app origin (SEC-013).
- Rate limits on every /api/v1 request: per session, or per IP when signed out (SEC-005, D-039).
- Request limits: 413 above 2.5 MB (audio chunks 8 MB); NUL characters refused with 422; every API
  answer is `no-store` and carries `default-src 'none'` (D-052).
- Web server content policy allows media only from the site and the storage service named by
  `MEDIA_ORIGINS` (D-061); security headers stay on cached files (caching uses `expires`).
- CORS allowlist from configuration (FND-011).

## 7. Secrets and supply chain

- Secrets only in environment / cloud secret manager; `.env.example` holds names and safe values (FND-025).
- Secret scanner and dependency vulnerability scan in CI (SEC-004, SEC-015).
- Pinned dependencies with lockfiles (ARCH-003).

## 8. Infrastructure

- TLS everywhere; encryption at rest for database, storage and backups (SEC-002, SEC-003).
- Least-privilege cloud roles per component (SEC-014).
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
| A project's tabs after Overview are for people who manage projects | A rule of the pages only: the API behind the tabs is as before and keeps hiding names and contact details from people who may not see them | participants.test.tsx, journeys/boundaries.spec.ts |

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

The set-up shows the authenticator link as a QR code made in the browser by the application's
own code (D-107): the secret is sent to no other service to draw it.

## 9h. The installable application, 2026-11-14 (D-110)

| Rule | Where it is kept | Test |
|---|---|---|
| The service worker keeps built files and the offline page only; nothing from `/api/`, no recording, no page | `frontend/pwa/sw.template.js`: it answers only GET requests for `/assets/` and the offline files, and pages only to pass them on | src/pwa/pwa.test.tsx; e2e/pwa.spec.ts (the browser's stores after loading) |
| Nothing private in the browser's own stores | The application keeps no token or personal data in local or session storage (the session is a cookie the page cannot read) | e2e/pwa.spec.ts |
| A new version never reloads a page by itself | The page reloads only after the person clicks Reload | src/pwa/pwa.test.tsx |
| The worker and the manifest come from the same address only | The site's rules (`default-src 'self'`) cover workers and manifests | checked with nginx 1.28 (docs/evidence/phase10/pwa_2026-11-14.txt) |

## 10. Open security questions

- Call-recording consent law and provider terms in India: NOT VERIFIED (DECISIONS.md B-10).
- Data-residency region: open (B-04).

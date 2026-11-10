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

## 10. Open security questions

- Call-recording consent law and provider terms in India: NOT VERIFIED (DECISIONS.md B-10).
- Data-residency region: open (B-04).

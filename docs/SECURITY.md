# Security

Status: planned (Phase 0). Nothing is implemented. Requirement IDs: SEC-*, AUTH-*, ROLE-*, STOR-*,
TEL-012..013, TEL-035, PWA-004, PWA-007, OPS-003.

## 1. Authentication

- Server-side sessions; session ID in an HttpOnly, Secure, SameSite=Strict cookie; CSRF token on every
  state-changing request (SEC-007). No long-lived secrets in localStorage (AUTH-013).
- Passwords: Argon2id with per-password salt; never logged or returned (AUTH-006, AUTH-015).
- Idle and absolute session expiry, configurable; revocation per session and per user (AUTH-005, AUTH-010).
- Failed-login throttling per account and per IP in Redis (AUTH-009).
- Password reset: random token, stored hashed, single use, short expiry; same response whether the email
  exists or not (AUTH-004).
- Optional TOTP MFA after the base flow is proven (AUTH-008).
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
  `participants.contact` (PART-008).
- Consent records separate from profiles, readable only by permitted roles (PART-006, SEC-010).
- Exports exclude phone numbers by default; including personal data needs an explicit grant and is
  audited (EXP-004).
- Retention rules per project and asset kind; deletion jobs and requests audited (STOR-009, PART-009).
- Evidence and test data never contain real personal data (GEN-006).

## 4. Files and storage

- Private bucket, public access blocked, server-side encryption, versioning (STOR-001, STOR-013).
- Downloads only by short-lived signed URL issued after a permission check (STOR-005).
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
- Rate limits on auth, uploads, exports and webhooks (SEC-005).
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

## 9. Open security questions

- Call-recording consent law and provider terms in India: NOT VERIFIED (DECISIONS.md B-10).
- Data-residency region: open (B-04).

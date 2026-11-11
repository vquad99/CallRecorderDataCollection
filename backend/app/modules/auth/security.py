"""Password hashing, opaque tokens, TOTP and field encryption (AUTH-006, AUTH-008)."""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import struct
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from urllib.parse import quote

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from cryptography.fernet import Fernet, InvalidToken, MultiFernet

from app.core.errors import AppError

# Argon2id at the OWASP minimum (19 MiB, 2 passes, 1 lane). The library default (64 MiB, 4 lanes)
# let a burst of parallel sign-ins exhaust a 512 MB server (security review 2026-11-11, D-088).
# Older hashes still verify and are upgraded at the next sign-in (needs_rehash).
_hasher = PasswordHasher(time_cost=2, memory_cost=19456, parallelism=1)
# At most this many hashes at once in one process; the rest wait their turn, then give up.
HASH_SLOTS = 2
HASH_WAIT_SECONDS = 10.0
_slots = threading.BoundedSemaphore(HASH_SLOTS)
# Verified when an account does not exist, so a miss costs the same time as a wrong password.
_DUMMY_HASH = _hasher.hash(secrets.token_urlsafe(16))


@contextmanager
def _hash_slot() -> Iterator[None]:
    if not _slots.acquire(timeout=HASH_WAIT_SECONDS):
        raise AppError("The service is busy. Try again in a moment.", code="BUSY", status_code=503)
    try:
        yield
    finally:
        _slots.release()


TOTP_ISSUER = "Conversation Collection"
TOTP_STEP_SECONDS = 30
TOTP_DIGITS = 6


def hash_password(password: str) -> str:
    with _hash_slot():
        return _hasher.hash(password)


def verify_password(password_hash: str | None, password: str) -> bool:
    with _hash_slot():
        try:
            return (
                _hasher.verify(password_hash or _DUMMY_HASH, password) and password_hash is not None
            )
        except (VerifyMismatchError, VerificationError, InvalidHashError):
            return False


def needs_rehash(password_hash: str) -> bool:
    return _hasher.check_needs_rehash(password_hash)


def new_token() -> str:
    """High-entropy opaque token for cookies and links; only its hash is stored."""
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def tokens_equal(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode(), b.encode())


def new_totp_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")


def totp_uri(secret: str, account: str) -> str:
    label = quote(f"{TOTP_ISSUER}:{account}")
    return (
        f"otpauth://totp/{label}?secret={secret}&issuer={quote(TOTP_ISSUER)}"
        f"&digits={TOTP_DIGITS}&period={TOTP_STEP_SECONDS}"
    )


def _totp_at(secret: str, step: int) -> str:
    padded = secret + "=" * (-len(secret) % 8)
    key = base64.b32decode(padded, casefold=True)
    digest = hmac.new(key, struct.pack(">Q", step), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    code = (struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF) % 10**TOTP_DIGITS
    return str(code).zfill(TOTP_DIGITS)


def totp_step(secret: str, code: str, at: float | None = None) -> int | None:
    """RFC 6238 with one step of clock drift either way. Returns the time step the code belongs to,
    so the caller can refuse a code whose step was already used (RFC 6238 section 5.2)."""
    code = code.strip()
    # isascii first: isdigit() also accepts other scripts' digits, which compare_digest rejects.
    if not (code.isascii() and code.isdigit() and len(code) == TOTP_DIGITS):
        return None
    now = int((at if at is not None else time.time()) // TOTP_STEP_SECONDS)
    matched = None
    for step in (now - 1, now, now + 1):  # every candidate is compared: no early exit
        if hmac.compare_digest(_totp_at(secret, step), code):
            matched = step
    return matched


def verify_totp(secret: str, code: str, at: float | None = None) -> bool:
    return totp_step(secret, code, at) is not None


def fernet_keys(value: str) -> list[str]:
    """DATA_ENCRYPTION_KEY holds one key, or several separated by commas: the first encrypts,
    every one decrypts. Rotation: put a new key first, run `rotate-keys`, then drop the old one."""
    return [k.strip() for k in value.split(",") if k.strip()]


class FieldCipher:
    """Application-level encryption for sensitive columns (keys from DATA_ENCRYPTION_KEY)."""

    def __init__(self, key: str) -> None:
        self._fernet = MultiFernet([Fernet(k.encode()) for k in fernet_keys(key)])

    def encrypt(self, plaintext: str) -> str:
        return self._fernet.encrypt(plaintext.encode()).decode()

    def rotate(self, ciphertext: str) -> str:
        """The same value encrypted again with the first key (D-088)."""
        try:
            return self._fernet.rotate(ciphertext.encode()).decode()
        except InvalidToken:
            raise ValueError("encrypted value cannot be read with the configured key") from None

    def decrypt(self, ciphertext: str) -> str:
        try:
            return self._fernet.decrypt(ciphertext.encode()).decode()
        except InvalidToken:
            raise ValueError("encrypted value cannot be read with the configured key") from None

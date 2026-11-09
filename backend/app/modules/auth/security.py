"""Password hashing, opaque tokens, TOTP and field encryption (AUTH-006, AUTH-008)."""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import struct
import time
from urllib.parse import quote

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from cryptography.fernet import Fernet, InvalidToken

_hasher = PasswordHasher()  # Argon2id with the library's current recommended parameters
# Verified when an account does not exist, so a miss costs the same time as a wrong password.
_DUMMY_HASH = _hasher.hash(secrets.token_urlsafe(16))

TOTP_ISSUER = "Conversation Collection"
TOTP_STEP_SECONDS = 30
TOTP_DIGITS = 6


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str | None, password: str) -> bool:
    try:
        return _hasher.verify(password_hash or _DUMMY_HASH, password) and password_hash is not None
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


def totp_now(secret: str, at: float | None = None) -> str:
    return _totp_at(secret, int((at if at is not None else time.time()) // TOTP_STEP_SECONDS))


def verify_totp(secret: str, code: str, at: float | None = None) -> bool:
    """RFC 6238 with one step of clock drift either way."""
    code = code.strip()
    if not (code.isdigit() and len(code) == TOTP_DIGITS):
        return False
    step = int((at if at is not None else time.time()) // TOTP_STEP_SECONDS)
    return any(hmac.compare_digest(_totp_at(secret, step + d), code) for d in (-1, 0, 1))


class FieldCipher:
    """Application-level encryption for sensitive columns (key from DATA_ENCRYPTION_KEY)."""

    def __init__(self, key: str) -> None:
        self._fernet = Fernet(key.encode())

    def encrypt(self, plaintext: str) -> str:
        return self._fernet.encrypt(plaintext.encode()).decode()

    def decrypt(self, ciphertext: str) -> str:
        try:
            return self._fernet.decrypt(ciphertext.encode()).decode()
        except InvalidToken:
            raise ValueError("encrypted value cannot be read with the configured key") from None

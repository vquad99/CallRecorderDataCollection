"""Passwords that are long enough but still easy to guess (security audit 2026-11-23, D-160).

NIST SP 800-63B 3.1.1.2 asks for new passwords to be checked against commonly used, expected or
compromised values. The platform does it here, offline (no outside lookup): one character or a
handful of characters repeated, keyboard and alphabet runs, a common password with digits or
symbols added at the end, and the account's own name or the platform's name.
"""

from __future__ import annotations

import re

MIN_DISTINCT = 5

# Words that common passwords are built from; checked after the trailing digits and symbols that
# people add to reach a length rule are taken off ("password1234!" is "password").
COMMON_BASES = frozenset(
    {
        "abc",
        "admin",
        "administrator",
        "baseball",
        "changeme",
        "charlie",
        "computer",
        "conversation",
        "conversationcollection",
        "dragon",
        "dubdesk",
        "football",
        "freedom",
        "hello",
        "iloveyou",
        "india",
        "letmein",
        "login",
        "master",
        "monkey",
        "passw0rd",
        "password",
        "p@ssw0rd",
        "p@ssword",
        "princess",
        "qwerty",
        "qwertyuiop",
        "secret",
        "shadow",
        "sunshine",
        "superman",
        "trustno",
        "welcome",
        "whatever",
    }
)
_RUNS = (
    "abcdefghijklmnopqrstuvwxyz",
    "0123456789",
    "qwertyuiopasdfghjklzxcvbnm",
    "1qaz2wsx3edc4rfv5tgb6yhn7ujm8ik9ol0p",
)
_TAIL = re.compile(r"[\d\W_]+$")


def _is_run(text: str) -> bool:
    """Part of the alphabet, digits or a keyboard row, forwards or backwards (abcdefghijkl,
    987654321098, qwertyuiopas)."""
    if len(text) < 4:
        return False
    return any(text in run * 3 or text in (run * 3)[::-1] for run in _RUNS)


def weakness(password: str, email: str) -> str | None:
    """Why this password is too easy to guess, or None."""
    lowered = password.lower()
    if len(set(lowered)) < MIN_DISTINCT:
        return f"Use at least {MIN_DISTINCT} different characters"
    if _is_run(lowered):
        return "Do not use a run of letters, numbers or keys"
    base = _TAIL.sub("", lowered)
    local = email.split("@", 1)[0].lower()
    if base in COMMON_BASES or _is_run(base) or (len(local) >= 4 and base == local):
        return "This password is too common or too easy to guess; choose another"
    return None

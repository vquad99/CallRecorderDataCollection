"""Email addresses and phone numbers, as the platform checks, stores and compares them.

An email address is checked for its form (no lookup of the domain) and kept as written, with
the domain in lower case; a staff account's address is kept all in lower case, because people
sign in with it typed in any case. A phone number is kept in international E.164 form (+ and up
to 15 digits).
"""

from __future__ import annotations

import re

from email_validator import EmailNotValidError, validate_email

from app.core.errors import AppError

_PHONE = re.compile(r"^\+[1-9][0-9]{7,14}$")
_PHONE_JUNK = re.compile(r"[\s\-().]")


def normalize_email(raw: str) -> str:
    """The form an address is looked up by (sign-in, password reset); no checking."""
    return raw.strip().lower()


def clean_email(raw: str) -> str:
    """A well-formed address in the form it is stored, or 422 INVALID_EMAIL."""
    try:
        return validate_email(raw.strip(), check_deliverability=False).normalized
    except EmailNotValidError:
        raise AppError(
            "Enter a valid email address", code="INVALID_EMAIL", status_code=422
        ) from None


def clean_account_email(raw: str) -> str:
    """A staff account's address: well-formed, and in the form sign-in looks it up by."""
    return normalize_email(clean_email(raw))


def normalize_phone(raw: str) -> str:
    """+<country><number> from what people type (spaces, dashes, brackets, a leading 00), or
    422 INVALID_PHONE."""
    phone = _PHONE_JUNK.sub("", raw.strip())
    if phone.startswith("00"):
        phone = "+" + phone[2:]
    if not _PHONE.match(phone):
        raise AppError(
            "Phone number must be in international format, e.g. +91 98765 43210",
            code="INVALID_PHONE",
            status_code=422,
        )
    return phone

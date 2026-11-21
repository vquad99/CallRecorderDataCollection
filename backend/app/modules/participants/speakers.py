"""Speaker details (D-143): who a participant is as a speaker, the metadata speech-data clients
need with each conversation (the NLTM Konkani project). They belong to the person, so they are the
same in every project the person is in.

The one place that knows the fields, checks a value and says whether a participant's details are
complete. The API, the file import and the task rules all use it, so every way in has the same
rules. Every field may be empty (people saved before D-143 have none); a value that is given must
be valid. A task is made only for two people whose details are complete (tasks/pairing.py).

The native district is the participant's `district` (D-121), kept under that name.
"""

from __future__ import annotations

import re
from collections.abc import Mapping

from app.core.errors import AppError
from app.modules.participants.models import (
    EDUCATION_CODES,
    EDUCATION_MEDIUM_CODES,
    GENDER_CODES,
    MAX_AGE,
    MIN_AGE,
    Participant,
)

# The 28 states and 8 union territories of India, as written in the form's list and in the
# file. frontend/src/lib/speakers.ts has the same list (a test checks they match).
INDIAN_STATES: tuple[str, ...] = (
    "Andaman and Nicobar Islands",
    "Andhra Pradesh",
    "Arunachal Pradesh",
    "Assam",
    "Bihar",
    "Chandigarh",
    "Chhattisgarh",
    "Dadra and Nagar Haveli and Daman and Diu",
    "Delhi",
    "Goa",
    "Gujarat",
    "Haryana",
    "Himachal Pradesh",
    "Jammu and Kashmir",
    "Jharkhand",
    "Karnataka",
    "Kerala",
    "Ladakh",
    "Lakshadweep",
    "Madhya Pradesh",
    "Maharashtra",
    "Manipur",
    "Meghalaya",
    "Mizoram",
    "Nagaland",
    "Odisha",
    "Puducherry",
    "Punjab",
    "Rajasthan",
    "Sikkim",
    "Tamil Nadu",
    "Telangana",
    "Tripura",
    "Uttar Pradesh",
    "Uttarakhand",
    "West Bengal",
)
_STATES = {s.lower(): s for s in INDIAN_STATES}

# Every speaker detail, in the order the form and the file list them, with its words for people.
FIELDS: dict[str, str] = {
    "age": "Age",
    "gender": "Gender",
    "current_state": "Current state",
    "current_district": "Current district",
    "current_pincode": "Current PIN code",
    "native_state": "Native state",
    "district": "Native district",
    "native_pincode": "Native PIN code",
    "native_language": "Native language",
    "education": "Education",
    "education_medium": "Medium of education",
    "recording_state": "Recording state",
    "recording_district": "Recording district",
    "recording_pincode": "Recording PIN code",
}
_KINDS = {
    "age": "age",
    "gender": "gender",
    "education": "education",
    "education_medium": "medium",
    "native_language": "language",
    **{f"{place}_state": "state" for place in ("current", "native", "recording")},
    **{f"{place}_pincode": "pincode" for place in ("current", "native", "recording")},
    **{name: "district" for name in ("current_district", "district", "recording_district")},
}
_PINCODE = re.compile(r"^[1-9][0-9]{5}$")
_MAX_TEXT = {"district": 100, "language": 50}


def _bad(field: str, message: str) -> AppError:
    return AppError(
        message, code="INVALID_SPEAKER_DETAILS", status_code=422, details=[{"field": field}]
    )


def _code(value: str) -> str:
    """A code as people type it ("non-english", "Higher secondary") in the stored form."""
    return re.sub(r"[\s-]+", "_", value.strip()).upper()


def clean(field: str, value: object) -> int | str | None:
    """The value as stored, None when it is empty, or 422 INVALID_SPEAKER_DETAILS naming the
    field. Text from a file and values from the API are both accepted."""
    kind, label = _KINDS[field], FIELDS[field]
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    if kind == "age":
        number: int | None = None
        if isinstance(value, int) and not isinstance(value, bool):
            number = value
        elif isinstance(value, str) and value.strip().isdigit():
            number = int(value.strip())
        if number is None or not MIN_AGE <= number <= MAX_AGE:
            raise _bad(field, f"Age must be a whole number from {MIN_AGE} to {MAX_AGE}")
        return number
    if not isinstance(value, str):
        raise _bad(field, f"{label} must be text")
    if kind == "state":
        state = _STATES.get(" ".join(value.split()).lower())
        if state is None:
            raise _bad(
                field,
                f"{label} must be a state or union territory of India, written in full "
                "(for example Goa)",
            )
        return state
    if kind == "pincode":
        pincode = value.replace(" ", "")
        if not _PINCODE.match(pincode):
            raise _bad(field, f"{label} must be 6 digits and cannot start with 0")
        return pincode
    choices = {
        "gender": GENDER_CODES,
        "education": EDUCATION_CODES,
        "medium": EDUCATION_MEDIUM_CODES,
    }
    if kind in choices:
        code = _code(value)
        if code not in choices[kind]:
            raise _bad(field, f"{label} must be one of: {', '.join(choices[kind])}")
        return code
    text = value.strip()
    if len(text) > _MAX_TEXT[kind]:
        raise _bad(field, f"{label} is too long (at most {_MAX_TEXT[kind]} characters)")
    return text


def clean_all(values: Mapping[str, object]) -> dict[str, int | str | None]:
    """The given fields (others are left out), each checked by `clean`."""
    return {name: clean(name, values[name]) for name in FIELDS if name in values}


def missing(p: Participant) -> list[str]:
    """The words for the speaker details this participant does not have yet, in form order."""
    return [label for name, label in FIELDS.items() if getattr(p, name) in (None, "")]


def complete(p: Participant) -> bool:
    return not missing(p)

"""Speaker details (D-143): who a participant is as a speaker, the metadata speech-data clients
need with each conversation (the NLTM Konkani project). They belong to the person, so they are the
same in every project the person is in.

The one place that knows the fields, checks a value and says whether a participant's details are
complete. The API, the file import and the task rules all use it, so every way in has the same
rules. Every field may be empty (people saved before D-143 have none); a value that is given must
be valid. A task is made only for two people whose details are complete (tasks/pairing.py).

What a project asks of its speakers is the project's own setting (D-145): the ages it takes
(`speaker_min_age`, `speaker_max_age`) and the details a person needs before a task
(`required_speaker_details`). A value is checked here against what fits any person (an age of 1 to
120); `check_age` and `check_ages` hold it to the project's range wherever a project is known, and
`complete` judges the details against the project's list.

The native district is the participant's `district` (D-121), kept under that name.
"""

from __future__ import annotations

import re
from collections.abc import Collection, Iterable, Mapping
from typing import TYPE_CHECKING

from app.core.errors import AppError
from app.modules.participants.models import (
    EDUCATION_CODES,
    EDUCATION_MEDIUM_CODES,
    GENDER_CODES,
    MAX_AGE,
    MIN_AGE,
    Participant,
)

if TYPE_CHECKING:
    from app.modules.projects.models import Project

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
        elif isinstance(value, str) and value.strip().isdecimal():
            # isdecimal, not isdigit: exactly what int() reads ("२५" too), never "²" (PART-06).
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


def clean_required(keys: Iterable[str]) -> list[str]:
    """A project's list of required speaker details (D-145): known field names only, each once,
    in the form's order; 422 UNKNOWN_SPEAKER_DETAIL naming the first unknown one."""
    given = set(keys)
    unknown = sorted(given - FIELDS.keys())
    if unknown:
        raise AppError(
            f"{unknown[0]} is not a speaker detail. Choose from: {', '.join(FIELDS)}",
            code="UNKNOWN_SPEAKER_DETAIL",
            status_code=422,
            details=[{"field": "required_speaker_details", "value": unknown[0]}],
        )
    return [name for name in FIELDS if name in given]


def missing(details: Participant | Mapping[str, object], project: Project) -> list[str]:
    """The words for the speaker details the project needs (D-145) that these do not have yet,
    in form order: a participant, or the values of a file row as `clean_all` gives them."""
    required = project.required_speaker_details
    values = (
        details
        if isinstance(details, Mapping)
        else {name: getattr(details, name) for name in FIELDS}
    )
    return [
        label
        for name, label in FIELDS.items()
        if name in required and values.get(name) in (None, "")
    ]


def complete(p: Participant, project: Project) -> bool:
    """Whether the participant has every speaker detail the project needs: what the lists show as
    `speaker_details_complete` and what a task needs (D-143, D-145)."""
    return not missing(p, project)


def _ages(project: Project) -> str:
    return f"{project.speaker_min_age} to {project.speaker_max_age}"


def _outside(project: Project, age: int | None) -> bool:
    return age is not None and not project.speaker_min_age <= age <= project.speaker_max_age


def check_age(project: Project, age: int | None) -> None:
    """An age typed for this project (the form, a file row): 422 SPEAKER_AGE_OUT_OF_RANGE when it
    is outside the ages the project takes (D-145). No age is not checked here."""
    if _outside(project, age):
        raise AppError(
            f"Age must be from {_ages(project)} in this project (its speaker ages)",
            code="SPEAKER_AGE_OUT_OF_RANGE",
            status_code=422,
            details=[
                {
                    "field": "age",
                    "min_age": project.speaker_min_age,
                    "max_age": project.speaker_max_age,
                }
            ],
        )


def check_ages(project: Project, people: Collection[Participant]) -> None:
    """People joining the project or put on a task: 422 SPEAKER_AGE_OUT_OF_RANGE naming those whose
    age is outside the project's range (D-145). Their ages are not told."""
    codes = [p.participant_code for p in people if _outside(project, p.age)]
    if codes:
        who = f"{'Participant' if len(codes) == 1 else 'Participants'} {' and '.join(codes)}"
        raise AppError(
            f"{who} {'is' if len(codes) == 1 else 'are'} outside this project's speaker ages "
            f"({_ages(project)}).",
            code="SPEAKER_AGE_OUT_OF_RANGE",
            status_code=422,
            details=[
                {
                    "participants": codes,
                    "min_age": project.speaker_min_age,
                    "max_age": project.speaker_max_age,
                }
            ],
        )

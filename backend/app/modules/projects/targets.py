"""A project's audio and progress settings and its collection targets (D-148). All of them are
project settings (the Rules tab); the first client's numbers (Konkani, NLTM) are only what a
project starts with. No database access here: the rules for the values are pure functions, used
by projects/service.py and the Progress tab (projects/progress.py).

Audio and progress:
- `pause_limit_seconds`: a silent stretch inside the speech longer than this is a long pause (the
  automatic check PAUSES, audio_qc/rules.py); 1 to 30, 3 at the start.
- `long_pauses_need_review`: long pauses make the automatic check ask for a listen (REVIEW)
  instead of only showing them (INFO).
- `progress_counts`: what counts as completed minutes on the Progress tab and the dashboard:
  EFFECTIVE, the effective speech of approved conversations (recordings/media.speech_of), or FULL,
  their whole length. Payments always count the full length (D-137).

Targets: hours (effective or full, as `progress_counts` says), speakers, conversations, and the
shares the client wants of speakers by age band and gender, of conversations by recording type,
and of speakers by native district (an equal share per listed district).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from decimal import Decimal
from itertools import pairwise
from typing import Any

from app.core.errors import AppError
from app.modules.participants import speakers
from app.modules.participants.models import GENDER_CODES, MAX_AGE, MIN_AGE

# ---------------------------------------------------------------------- audio and progress

PROGRESS_COUNTS = ("EFFECTIVE", "FULL")
DEFAULT_PROGRESS_COUNTS = "EFFECTIVE"
DEFAULT_PAUSE_LIMIT_SECONDS = 3
PAUSE_LIMIT_RANGE = (1, 30)

# ---------------------------------------------------------------------- targets

MODES = ("FACE_TO_FACE", "TELEPHONY")
MAX_BANDS = 12
MAX_DISTRICTS = 100
MAX_DISTRICT = 100  # as a participant's native district (participants/speakers.py)
DEFAULT_TARGET_SPEAKERS = 500
DEFAULT_TARGET_CONVERSATIONS = 600
# The first client's targets: what a new project starts with, and what every project got when the
# targets came (migration 0038). An age band takes the ages from its `from` up to, but not
# including, its `to`; the band that ends highest also takes its `to` (so 20-30, 30-40, 40-50 and
# 50-60 cover 20 to 60, and a speaker of 30 is in 30-40).
DEFAULT_TARGET_AGE_BANDS: tuple[dict[str, int], ...] = (
    {"from": 20, "to": 30, "percent": 40},
    {"from": 30, "to": 40, "percent": 30},
    {"from": 40, "to": 50, "percent": 20},
    {"from": 50, "to": 60, "percent": 10},
)
DEFAULT_TARGET_GENDER: dict[str, int] = {"MALE": 50, "FEMALE": 50}
DEFAULT_TARGET_MODES: dict[str, int] = {"FACE_TO_FACE": 50, "TELEPHONY": 50}
# Districts start empty; the Rules tab's "Use the client's Konkani districts" fills these (the
# same list is written once more in frontend/src/features/projects/targets.ts, a test checks
# they match).
CLIENT_DISTRICTS: tuple[dict[str, str], ...] = (
    {"state": "Goa", "district": "North Goa"},
    {"state": "Goa", "district": "South Goa"},
    {"state": "Karnataka", "district": "Uttara Kannada"},
    {"state": "Karnataka", "district": "Udupi"},
    {"state": "Karnataka", "district": "Dakshina Kannada"},
    {"state": "Maharashtra", "district": "Sindhudurg"},
    {"state": "Maharashtra", "district": "Ratnagiri"},
    {"state": "Maharashtra", "district": "Raigad"},
)


def default_age_bands() -> list[dict[str, int]]:
    return [dict(band) for band in DEFAULT_TARGET_AGE_BANDS]


def _invalid(message: str, field: str, **detail: Any) -> AppError:
    return AppError(
        message, code="INVALID_TARGETS", status_code=422, details=[{"field": field, **detail}]
    )


def _percent(value: object, field: str, **where: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 100:
        raise _invalid(
            f"{_WORDS[field]}: a percent is a whole number from 0 to 100", field, **where
        )
    return value


_WORDS = {
    "target_age_bands": "Age bands",
    "target_gender": "Gender",
    "target_modes": "Face-to-face and phone",
    "target_districts": "Districts",
}


def _total(values: Sequence[int], field: str) -> None:
    if values and sum(values) != 100:
        raise _invalid(
            f"{_WORDS[field]}: the percents add up to {sum(values)}, not 100", field, total=100
        )


def _age(value: object) -> int | None:
    """An age any person may have (1 to 120), or None."""
    if isinstance(value, int) and not isinstance(value, bool) and MIN_AGE <= value <= MAX_AGE:
        return value
    return None


def clean_age_bands(raw: Sequence[Mapping[str, Any]]) -> list[dict[str, int]]:
    """Age bands as a project saves them, in age order (422 INVALID_TARGETS naming the band): each
    `from` below its `to`, within the ages any person may have (1 to 120), no two overlapping, at
    most 12; the percents add up to 100. None at all = no age target."""
    field = "target_age_bands"
    if len(raw) > MAX_BANDS:
        raise _invalid(f"Age bands: at most {MAX_BANDS}", field)
    bands: list[dict[str, int]] = []
    for number, band in enumerate(raw, start=1):
        low, high = _age(band.get("from")), _age(band.get("to"))
        if low is None or high is None:
            raise _invalid(
                f"Age band {number}: ages are whole numbers from {MIN_AGE} to {MAX_AGE}",
                field,
                band=number,
            )
        if low >= high:
            raise _invalid(
                f"Age band {number}: the first age must be below the last", field, band=number
            )
        bands.append(
            {"from": low, "to": high, "percent": _percent(band.get("percent"), field, band=number)}
        )
    bands.sort(key=lambda b: b["from"])
    for before, after in pairwise(bands):
        if after["from"] < before["to"]:
            raise _invalid(
                f"Age bands {before['from']}-{before['to']} and {after['from']}-{after['to']} "
                "overlap",
                field,
            )
    _total([b["percent"] for b in bands], field)
    return bands


def _shares(raw: Mapping[str, Any], keys: Sequence[str], field: str) -> dict[str, int]:
    """Percents per key (all keys, adding up to 100), or {} for no target."""
    if not raw:
        return {}
    if set(raw) != set(keys):
        raise _invalid(f"{_WORDS[field]}: give a percent for each of {', '.join(keys)}", field)
    shares = {key: _percent(raw[key], field, key=key) for key in keys}
    _total(list(shares.values()), field)
    return shares


def clean_gender(raw: Mapping[str, Any]) -> dict[str, int]:
    """{MALE, FEMALE} percents adding up to 100, or {} for no gender target."""
    return _shares(raw, GENDER_CODES, "target_gender")


def clean_modes(raw: Mapping[str, Any]) -> dict[str, int]:
    """{FACE_TO_FACE, TELEPHONY} percents adding up to 100, or {} for no target."""
    return _shares(raw, MODES, "target_modes")


def _key(text: str) -> str:
    return " ".join(text.split()).lower()


def clean_districts(raw: Sequence[Mapping[str, Any]]) -> list[dict[str, str]]:
    """Districts as a project saves them (422 INVALID_TARGETS naming the row): a state of India as
    on the participant form, a district of at most 100 characters, each pair once, at most 100."""
    field = "target_districts"
    if len(raw) > MAX_DISTRICTS:
        raise _invalid(f"Districts: at most {MAX_DISTRICTS}", field)
    out: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for number, row in enumerate(raw, start=1):
        try:
            state = speakers.clean("native_state", row.get("state"))
        except AppError:
            raise _invalid(
                f"District {number}: the state must be a state or union territory of India, "
                "written in full (for example Goa)",
                field,
                row=number,
            ) from None
        district = " ".join(str(row.get("district") or "").split())
        if not state or not district or len(district) > MAX_DISTRICT:
            raise _invalid(
                f"District {number}: give the state and a district of at most {MAX_DISTRICT} "
                "characters",
                field,
                row=number,
            )
        pair = (_key(str(state)), _key(district))
        if pair in seen:
            raise _invalid(f"District {number}: {district} is listed twice", field, row=number)
        seen.add(pair)
        out.append({"state": str(state), "district": district})
    return out


# ---------------------------------------------------------------------- what the Progress tab uses


def band_of(age: int | None, bands: Sequence[Mapping[str, int]]) -> int | None:
    """The index of the band an age is in (see DEFAULT_TARGET_AGE_BANDS), None outside them."""
    if age is None or not bands:
        return None
    top = max(b["to"] for b in bands)
    for i, band in enumerate(bands):
        if band["from"] <= age < band["to"] or (age == band["to"] == top):
            return i
    return None


def district_of(
    state: str | None, district: str | None, targets: Sequence[Mapping[str, str]]
) -> int | None:
    """The index of the target district a speaker's native district is: the same name (spaces and
    capitals aside) and the same state, or no state given. None when it is none of them."""
    if not district:
        return None
    name = _key(district)
    for i, target in enumerate(targets):
        if _key(target["district"]) == name and (not state or _key(state) == _key(target["state"])):
            return i
    return None


def hours_target(value: Decimal | None) -> float | None:
    """The hours target as the Progress tab uses it; 0 (allowed before PROJ-12, still possible in
    a project saved then) is no target, like null."""
    return float(value) if value else None


def split(total: int, weights: Sequence[int]) -> list[int]:
    """`total` shared out by whole-number `weights` (percents, or products of percents) as whole
    numbers that add up to `total` exactly (D-153, the "Still needed" targets): the largest
    remainder method. Each part first gets the whole part of its exact share; the ones left over go
    to the parts with the largest fractions, the first in order on a tie. Integer arithmetic only,
    so the same targets always give the same parts. No weight at all: every part is 0."""
    whole = sum(weights)
    if whole <= 0:
        return [0 for _ in weights]
    parts = [divmod(total * w, whole) for w in weights]
    out = [quotient for quotient, _ in parts]
    left = total - sum(out)
    order = sorted(range(len(parts)), key=lambda i: (-parts[i][1], i))
    for i in order[:left]:
        out[i] += 1
    return out

"""What a project asks of its moderators (D-147): the device details of each speaker, and the
reminders shown before recording. Both are project settings (the Rules tab); the first client's
(Konkani, NLTM) are only what a project starts with. No database access here: the rules for the
values are pure functions, used by projects/service.py and tasks/devices.py.

Device details are filled by the moderator for each speaker of each conversation, before the task
goes to QC (tasks/devices.py). The call type is not asked: it is the task's recording mode.

Reminders: a short list of lines the moderator reads before recording (the recorder page) and
before calling (the call card): the speaker-ID line (built on the page from the task's people),
what to talk about, what to avoid, and tips for the task's mode.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any, Literal

from app.core.errors import AppError

# The device details a project may ask, in the form's order, with their words.
DEVICE_FIELDS: dict[str, str] = {
    "device_make": "Device make",
    "device_model": "Device model",
    "bluetooth_earphones": "Bluetooth earphones used",
    "wired_earphones": "Wired earphones used",
    "loudspeaker_on": "Loudspeaker on",
}
TEXT_FIELDS = ("device_make", "device_model")
YES_NO_FIELDS = ("bluetooth_earphones", "wired_earphones", "loudspeaker_on")
# The first client's names for them in the metadata file of each speaker (delivered in a later
# part), with call_type from the task's mode.
CLIENT_KEYS: dict[str, str] = {
    "device_make": "device_make",
    "device_model": "device_model",
    "bluetooth_earphones": "is_bluetooth_earphones_used",
    "wired_earphones": "if_wired_earphones_used",
    "loudspeaker_on": "is_loudspeaker_switched_on",
}
CallType = Literal["Telephonic", "Face-to-face"]
CALL_TYPES: dict[str, CallType] = {"TELEPHONY": "Telephonic", "FACE_TO_FACE": "Face-to-face"}
MAX_DEVICE_TEXT = 60
# Every project starts by asking all five (the first client's list).
DEFAULT_DEVICE_FIELDS: tuple[str, ...] = tuple(DEVICE_FIELDS)


def clean_device_fields(names: Iterable[str]) -> list[str]:
    """A project's list of device details to ask: known names only, each once, in the form's
    order; 422 UNKNOWN_DEVICE_FIELD naming the first unknown one."""
    given = set(names)
    unknown = sorted(given - DEVICE_FIELDS.keys())
    if unknown:
        raise AppError(
            f"{unknown[0]} is not a device detail. Choose from: {', '.join(DEVICE_FIELDS)}",
            code="UNKNOWN_DEVICE_FIELD",
            status_code=422,
            details=[{"field": "device_fields", "value": unknown[0]}],
        )
    return [name for name in DEVICE_FIELDS if name in given]


# ------------------------------------------------------------------------------------ reminders

# The lists of lines a project's reminders hold, with their words in messages.
REMINDER_LISTS: dict[str, str] = {
    "topics": "Talk about",
    "avoid": "Avoid",
    "face_to_face": "Face-to-face tips",
    "telephony": "Phone call tips",
}
MODE_TIPS = {"FACE_TO_FACE": "face_to_face", "TELEPHONY": "telephony"}
MAX_REMINDER_LINES = 20
MAX_REMINDER_LINE = 200

# The first client's guideline (Konkani, NLTM): what a new project starts with, and what every
# project got when the reminders came (migration 0037). The face-to-face tips hold what the
# recorder said on its own before ("Place the microphone between the two speakers ...").
DEFAULT_RECORDING_REMINDERS: dict[str, Any] = {
    # "Ask each speaker to start with: I am <first name> and speaker ID <code>".
    "speaker_id": True,
    "topics": [
        "daily activities",
        "education",
        "agriculture",
        "food and cooking",
        "travel",
        "shopping",
        "health and fitness in general",
        "weather",
        "work and hobbies",
    ],
    "avoid": [
        "politics",
        "religion",
        "obscene talk",
        "hate or killing",
        "other sensitive topics",
        "personal information",
    ],
    "face_to_face": [
        "Record in a quiet place; both speakers stay in one place (sitting or standing).",
        "Place the recording device between the two speakers, no more than 2.5 feet from each "
        "mouth, and do not move it.",
    ],
    "telephony": [
        "Each speaker is in a quiet place and stays in one place (sitting or standing).",
        "Hold the handset near the mouth and keep the loudspeaker off.",
        "No ringtones or notification sounds during the call.",
    ],
}


def default_reminders() -> dict[str, Any]:
    """A fresh copy of the first client's reminders, for a new project."""
    return {
        key: list(value) if isinstance(value, list) else value
        for key, value in DEFAULT_RECORDING_REMINDERS.items()
    }


def _invalid(message: str, name: str, line: int | None = None) -> AppError:
    detail: dict[str, Any] = {"field": "recording_reminders", "list": name}
    if line is not None:
        detail["line"] = line
    return AppError(message, code="INVALID_REMINDERS", status_code=422, details=[detail])


def clean_reminders(raw: Mapping[str, Any]) -> dict[str, Any]:
    """Reminders as a project saves them, checked (422 INVALID_REMINDERS naming the list and the
    line): each list at most 20 lines of at most 200 characters; spaces are tidied and empty lines
    dropped. A list left out is empty."""
    out: dict[str, Any] = {"speaker_id": bool(raw.get("speaker_id", True))}
    for name, words in REMINDER_LISTS.items():
        lines = [" ".join(str(line).split()) for line in raw.get(name) or []]
        lines = [line for line in lines if line]
        if len(lines) > MAX_REMINDER_LINES:
            raise _invalid(f"{words}: at most {MAX_REMINDER_LINES} lines", name)
        for number, line in enumerate(lines, start=1):
            if len(line) > MAX_REMINDER_LINE:
                raise _invalid(
                    f"{words}, line {number}: at most {MAX_REMINDER_LINE} characters", name, number
                )
        out[name] = lines
    return out


def reminders_for(stored: Mapping[str, Any], mode: str) -> dict[str, Any]:
    """What the moderator of a task in this mode reads: the speaker-ID line or not, the topics,
    what to avoid and the tips for the mode."""
    return {
        "speaker_id": bool(stored.get("speaker_id", True)),
        "topics": list(stored.get("topics") or []),
        "avoid": list(stored.get("avoid") or []),
        "tips": list(stored.get(MODE_TIPS.get(mode, "")) or []),
    }

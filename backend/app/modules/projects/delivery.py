"""How a project's exports are laid out and named (D-149): project settings, the Rules tab's
Export card. The first client's delivery format (Konkani, NLTM) is only what a project starts with.
No database access here: pure functions, used by projects/service.py and exports/client.py.

- `export_layout`: CLIENT, the client's delivery format (exports/client.py), or PLATFORM, the
  platform's own layout (exports/bundle.py, D-105).
- `speaker_id_style`: NUMBER, the number of the participant code padded to at least 3 digits
  (P000123 -> "123", P000007 -> "007"), or CODE, the code itself ("P000123").
- `conversation_id_style`: CON_NUMBER, "CON" and the number of the task code padded to at least 3
  digits (T000045 -> "CON045"), or CODE ("T000045").
- `audio_name_pattern`: how an audio file is named, from the tokens {a} and {b} (the two speaker
  IDs), {a_pin} and {b_pin} (their native PIN codes) and {conversation} (the conversation ID);
  letters, digits, _ and - between them. It must hold {conversation}, so every name is unique.
"""

from __future__ import annotations

import re
from collections.abc import Mapping

from app.core.errors import AppError

CLIENT, PLATFORM = "CLIENT", "PLATFORM"
EXPORT_LAYOUTS = (CLIENT, PLATFORM)
SPEAKER_ID_STYLES = ("NUMBER", "CODE")
CONVERSATION_ID_STYLES = ("CON_NUMBER", "CODE")
DEFAULT_EXPORT_LAYOUT = CLIENT
DEFAULT_SPEAKER_ID_STYLE = "NUMBER"
DEFAULT_CONVERSATION_ID_STYLE = "CON_NUMBER"
# The tokens an audio file name is made of, with what each stands for.
AUDIO_NAME_TOKENS: dict[str, str] = {
    "a": "the first speaker's ID",
    "b": "the second speaker's ID",
    "a_pin": "the first speaker's native PIN code",
    "b_pin": "the second speaker's native PIN code",
    "conversation": "the conversation ID",
}
DEFAULT_AUDIO_NAME_PATTERN = "{a}_{b}_{a_pin}_{b_pin}_{conversation}"
MAX_AUDIO_NAME_PATTERN = 100
# A native PIN code that is not on file, in file names (MISSING.csv lists it).
NO_PINCODE = "000000"
# The least number of digits of a speaker or conversation number (7 -> "007").
NUMBER_DIGITS = 3

_TOKEN = re.compile(r"\{([^{}]*)\}")
_SAFE = re.compile(r"^[A-Za-z0-9_-]*$")


def _number(code: str) -> int:
    """The number of a participant or task code: P000123 -> 123."""
    return int(code[1:])


def speaker_id(participant_code: str, style: str) -> str:
    """A speaker's ID in the delivery: "123" (NUMBER) or "P000123" (CODE)."""
    if style == "CODE":
        return participant_code
    return f"{_number(participant_code):0{NUMBER_DIGITS}d}"


def conversation_id(task_code: str, style: str) -> str:
    """A conversation's ID in the delivery: "CON045" (CON_NUMBER) or "T000045" (CODE)."""
    if style == "CODE":
        return task_code
    return f"CON{_number(task_code):0{NUMBER_DIGITS}d}"


def _invalid(message: str) -> AppError:
    return AppError(
        message,
        code="INVALID_AUDIO_NAME_PATTERN",
        status_code=422,
        details=[{"field": "audio_name_pattern"}],
    )


def clean_audio_name_pattern(pattern: str) -> str:
    """The audio name pattern as a project saves it (spaces around it dropped), checked: 422
    INVALID_AUDIO_NAME_PATTERN for an empty or too long one, an unknown token, a character other
    than letters, digits, _ and - outside the tokens, or no {conversation}."""
    text = pattern.strip()
    if not text:
        raise _invalid("Write the audio file name, for example " + DEFAULT_AUDIO_NAME_PATTERN)
    if len(text) > MAX_AUDIO_NAME_PATTERN:
        raise _invalid(f"The audio file name is at most {MAX_AUDIO_NAME_PATTERN} characters")
    for token in _TOKEN.findall(text):
        if token not in AUDIO_NAME_TOKENS:
            known = ", ".join("{" + t + "}" for t in AUDIO_NAME_TOKENS)
            raise _invalid(f"{{{token}}} is not a token of the audio file name. Use {known}")
    if not _SAFE.match(_TOKEN.sub("", text)):
        raise _invalid(
            "Between the tokens, the audio file name takes only letters, digits, _ and -"
        )
    if "{conversation}" not in text:
        raise _invalid("The audio file name needs {conversation}, so that every name is unique")
    return text


def audio_name(pattern: str, values: Mapping[str, str]) -> str:
    """An audio file's name without its extension: the pattern's tokens filled in."""
    return _TOKEN.sub(lambda m: values[m.group(1)], pattern)


def uses_pincodes(pattern: str) -> bool:
    return "{a_pin}" in pattern or "{b_pin}" in pattern

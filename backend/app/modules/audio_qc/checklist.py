"""The QC checklist (D-146): what the QC Executive answers Yes or No for every recording.

A project's checklist is its own setting (`projects.qc_checklist`, the Rules tab); the first
client's guideline (Konkani, NLTM) is only what a project starts with. Each item:

- `key`: lowercase snake_case, unique in the list, at most 50 characters (the client's own JSON
  keys; a later part exports the answers under them);
- `question`: at most 200 characters, as the QC Executive reads it;
- `scope`: "conversation" (answered once) or "speaker" (answered for each of the two people);
- `fails_on`: the answer that means the recording fails ("yes" or "no"), or None for an
  observation, recorded with the decision and never failing anything;
- `required`: it must be answered before Pass or Send back for consent.

Besides the list, in a project that takes signed consent forms (D-144) the QC Executive checks
each person's form: "Consent form checked: signed, the right person, this project". That check is
built in, not an item. This module holds no database access: the rules for answers are pure
functions, used by audio_qc/service.py, and their result is kept with the decision as a snapshot
(the questions as they read then), so a checklist changed later never changes answers given.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from app.core.errors import AppError

SCOPES = ("conversation", "speaker")
ANSWERS = ("yes", "no")
SIDES = ("A", "B")
MAX_ITEMS = 60
MAX_KEY = 50
MAX_QUESTION = 200
KEY_FORMAT = re.compile(r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$")
# The question of the built-in consent check, as people and the snapshot read it.
CONSENT_QUESTION = "Consent form checked: signed, the right person, this project"


def _item(
    key: str, question: str, scope: str, fails_on: str | None, required: bool = True
) -> dict[str, Any]:
    return {
        "key": key,
        "question": question,
        "scope": scope,
        "fails_on": fails_on,
        "required": required,
    }


def _conversation(key: str, question: str) -> dict[str, Any]:
    return _item(key, question, "conversation", "no")


def _speaker(key: str, question: str) -> dict[str, Any]:
    return _item(key, question, "speaker", None)


# The first client's guideline (Konkani, NLTM): what a new project starts with, and what every
# project had when the checklist came (migration 0036). A project changes it on its Rules tab.
DEFAULT_QC_CHECKLIST: tuple[dict[str, Any], ...] = (
    _conversation(
        "correct_speaker_ids",
        "Both speakers have unique IDs that match the registered participants",
    ),
    _conversation(
        "speaker_id_announced", "Each speaker clearly says their speaker ID at the start"
    ),
    _conversation("two_speakers", "The conversation is between exactly two speakers"),
    _conversation("no_third_person", "No third person speaks or interrupts"),
    _conversation(
        "within_max_duration", "The conversation is within the maximum length (15 minutes)"
    ),
    _conversation("natural_conversation", "Natural conversation, not read from a script"),
    _conversation(
        "suitable_topic",
        "A common topic: nothing political, religious, obscene, hateful or sensitive",
    ),
    _conversation("no_personal_information", "Speakers do not share personal information"),
    _conversation("quiet_environment", "Relatively quiet: no road, TV, crying babies or vehicles"),
    _conversation("speakers_stationary", "Both speakers stay in one place (sitting or standing)"),
    _conversation("short_fillers", "Fillers (uh, um) never last more than 3 seconds"),
    _conversation("no_ringtone_overlap", "No ringtone or notification sound overlaps the speech"),
    _conversation("correct_recording_mode", "Correctly recorded as face-to-face or phone call"),
    _speaker("speech_intelligible", "Is speech intelligible?"),
    _speaker("speech_slurring", "Is speech slurred?"),
    _speaker("speech_stammering", "Is stammering present?"),
    _speaker("is_non_native_speech_present", "Is non-native speech present?"),
    _speaker("noisy_background", "Is background noise present?"),
    _speaker("good_pace_of_speech", "Is the pace of speech good?"),
    _speaker("is_this_natural_human_voice", "Is this a natural human voice?"),
    _speaker("low_speaker_volume", "Is the speaker's volume low?"),
    _speaker("speaker_far_from_microphone", "Is the speaker far from the microphone?"),
    _speaker("microphone_saturation", "Is microphone saturation present?"),
    _speaker("echo_in_audio", "Is echo present?"),
    _speaker("read_speech", "Does the speech sound read?"),
    _speaker("impromptu_speech", "Is the speech impromptu?"),
    _speaker("notifications_telephonic_sounds", "Are notification or phone sounds present?"),
    _speaker("speaker_breath_sounds", "Are breath sounds present?"),
)


def default_checklist() -> list[dict[str, Any]]:
    """A fresh copy of the first client's list, for a new project."""
    return [dict(item) for item in DEFAULT_QC_CHECKLIST]


@dataclass(frozen=True)
class Item:
    key: str
    question: str
    scope: str
    fails_on: str | None
    required: bool

    @property
    def per_speaker(self) -> bool:
        return self.scope == "speaker"

    def fails(self, answer: str | None) -> bool:
        return self.fails_on is not None and answer == self.fails_on

    def as_dict(self) -> dict[str, Any]:
        return _item(self.key, self.question, self.scope, self.fails_on, self.required)


def items_of(stored: Iterable[Mapping[str, Any]]) -> list[Item]:
    """A saved checklist (checked when it was saved) as items."""
    return [
        Item(
            key=str(i["key"]),
            question=str(i["question"]),
            scope=str(i["scope"]),
            fails_on=i.get("fails_on"),
            required=bool(i.get("required", True)),
        )
        for i in stored
    ]


def _invalid(position: int, message: str) -> AppError:
    return AppError(
        f"QC checklist, item {position}: {message}",
        code="INVALID_QC_CHECKLIST",
        status_code=422,
        details=[{"field": "qc_checklist", "item": position}],
    )


def clean(items: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """A checklist as a project saves it, checked (422 INVALID_QC_CHECKLIST naming the item): at
    most 60 items; each key lowercase snake_case, at most 50 characters and used once; each question
    given, at most 200 characters; scope conversation or speaker; fails_on yes, no or none."""
    if len(items) > MAX_ITEMS:
        raise AppError(
            f"A QC checklist has at most {MAX_ITEMS} items",
            code="INVALID_QC_CHECKLIST",
            status_code=422,
            details=[{"field": "qc_checklist"}],
        )
    seen: set[str] = set()
    out = []
    for position, raw in enumerate(items, start=1):
        key = str(raw.get("key") or "").strip()
        question = " ".join(str(raw.get("question") or "").split())
        scope, fails_on = raw.get("scope"), raw.get("fails_on")
        if not key or len(key) > MAX_KEY or not KEY_FORMAT.match(key):
            raise _invalid(
                position,
                f"the key must be lowercase letters, digits and _ (like speech_intelligible), "
                f"at most {MAX_KEY} characters",
            )
        if key in seen:
            raise _invalid(position, f"the key {key} is used twice")
        if not question or len(question) > MAX_QUESTION:
            raise _invalid(position, f"write the question (at most {MAX_QUESTION} characters)")
        if scope not in SCOPES:
            raise _invalid(position, "it applies to the conversation or to each speaker")
        if fails_on is not None and fails_on not in ANSWERS:
            raise _invalid(position, "the recording fails on Yes, on No, or never")
        seen.add(key)
        out.append(_item(key, question, str(scope), fails_on, bool(raw.get("required", True))))
    return out


@dataclass
class Answers:
    """Yes / No answers: conversation items once, speaker items per side (A, B), and the consent
    check per side. A question not answered is left out."""

    conversation: dict[str, str] = field(default_factory=dict)
    speakers: dict[str, dict[str, str]] = field(default_factory=dict)
    consent: dict[str, str] = field(default_factory=dict)

    @classmethod
    def read(cls, raw: Mapping[str, Any] | None) -> Answers:
        """From the API or a saved draft; anything that is not a yes or a no is unanswered."""
        raw = raw or {}

        def answers(values: Any) -> dict[str, str]:
            if not isinstance(values, Mapping):
                return {}
            return {str(k): v for k, v in values.items() if v in ANSWERS}

        speakers = raw.get("speakers") or {}
        return cls(
            conversation=answers(raw.get("conversation")),
            speakers={
                side: answers(speakers.get(side)) for side in SIDES if isinstance(speakers, Mapping)
            },
            consent={s: v for s, v in answers(raw.get("consent")).items() if s in SIDES},
        )

    def only(self, items: Sequence[Item], *, consent_check: bool) -> Answers:
        """The answers to these items only (a question taken out of the checklist meanwhile is
        dropped), and the consent check only where the project asks it."""
        conversation = {i.key for i in items if not i.per_speaker}
        speaker = {i.key for i in items if i.per_speaker}
        return Answers(
            conversation={k: v for k, v in self.conversation.items() if k in conversation},
            speakers={
                side: {k: v for k, v in self.speakers.get(side, {}).items() if k in speaker}
                for side in SIDES
            },
            consent=dict(self.consent) if consent_check else {},
        )

    def without_consent(self) -> Answers:
        return Answers(dict(self.conversation), {s: dict(v) for s, v in self.speakers.items()})

    def as_dict(self) -> dict[str, Any]:
        return {
            "conversation": dict(self.conversation),
            "speakers": {side: dict(self.speakers.get(side, {})) for side in SIDES},
            "consent": dict(self.consent),
        }


@dataclass(frozen=True)
class Finding:
    """One question answered so that the recording fails (side None: the conversation)."""

    item: Item
    side: str | None
    answer: str


def _slots(items: Sequence[Item]) -> Iterable[tuple[Item, str | None]]:
    for item in items:
        if item.per_speaker:
            for side in SIDES:
                yield item, side
        else:
            yield item, None


def _answer(answers: Answers, item: Item, side: str | None) -> str | None:
    if side is None:
        return answers.conversation.get(item.key)
    return answers.speakers.get(side, {}).get(item.key)


def unanswered(items: Sequence[Item], answers: Answers) -> list[tuple[Item, str | None]]:
    """The required questions without an answer, in the checklist's order."""
    return [
        (item, side)
        for item, side in _slots(items)
        if item.required and _answer(answers, item, side) is None
    ]


def failing(items: Sequence[Item], answers: Answers) -> list[Finding]:
    """The questions answered so that the recording fails, in the checklist's order."""
    found = []
    for item, side in _slots(items):
        answer = _answer(answers, item, side)
        if answer is not None and item.fails(answer):
            found.append(Finding(item, side, answer))
    return found


def label(item: Item, side: str | None, codes: Mapping[str, str]) -> str:
    """A question as a message names it: "P000123: Is speech intelligible?" for a speaker."""
    return f"{codes.get(side, side)}: {item.question}" if side else item.question


def snapshot(
    items: Sequence[Item],
    answers: Answers,
    participants: Sequence[Mapping[str, Any]],
    *,
    consent_check: bool,
) -> dict[str, Any]:
    """What a decision keeps: the questions as they read now, every answer by participant, the
    consent check (in a project that takes signed forms) and the failing answers.

    `participants`: for sides A and B, {side, participant_id, participant_code, consent_form_id}.
    """
    return {
        "items": [i.as_dict() for i in items],
        "consent_check": consent_check,
        "conversation": dict(answers.conversation),
        "participants": [
            {
                "side": p["side"],
                "participant_id": str(p["participant_id"]),
                "participant_code": p["participant_code"],
                "answers": dict(answers.speakers.get(p["side"], {})),
                "consent": answers.consent.get(p["side"]) if consent_check else None,
                "consent_form_id": p.get("consent_form_id") if consent_check else None,
            }
            for p in participants
        ],
        "failing": [
            {"key": f.item.key, "side": f.side, "answer": f.answer} for f in failing(items, answers)
        ],
    }


def answers_of(snap: Mapping[str, Any]) -> Answers:
    """The answers kept in a decision's snapshot, to start the next check from (D-146)."""
    return Answers(
        conversation=dict(snap.get("conversation") or {}),
        speakers={p["side"]: dict(p.get("answers") or {}) for p in snap.get("participants", [])},
        consent={
            p["side"]: p["consent"]
            for p in snap.get("participants", [])
            if p.get("consent") in ANSWERS
        },
    )

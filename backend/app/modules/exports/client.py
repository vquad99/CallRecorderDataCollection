"""The client's delivery format of an export (D-149): what goes where, under which name, with which
values, and what is not on file. Read from the database in a few queries for the whole export (a
`Plan`); bundle.py writes the files from it, and the export summary counts its missing items.

    face_to_face/audio/      001_002_570001_576101_CON001.wav  (the project's audio_name_pattern)
    face_to_face/metadata/   001_CON001_570001_METADATA.json   per speaker of each conversation:
                             device, call type and the QC answers about the speaker
    telephonic/audio/, telephonic/metadata/   the same for phone calls
    speakers/                once per speaker in the export:
                             001_570001_METADATA.json   the speaker details
                             001_consent.pdf            the signed consent form as uploaded (.pdf,
                                                        .jpg or .png), or 001_consent.html, the
                                                        online consent record
                             001_speaker_proof.pdf      the address proof as uploaded
    SPEAKER_METADATA_README.json   what each key of the metadata files means
    MISSING.csv                    every value and file not on file

Values are text, as in the client's example ("age": "29", "gender": "female"); a value not on file
is "" and a native PIN code not on file is 000000 in file names; MISSING.csv lists each. Speakers
appear by speaker ID (and participant code in the tables): never a name, phone number or email.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Collection, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.orm import Session

from app.modules.audio_qc import checklist
from app.modules.audio_qc.models import AudioQcResult
from app.modules.participants import consent
from app.modules.participants.models import (
    ADDRESS_PROOF,
    CONSENT_FORM,
    ConsentRecord,
    Participant,
    current_documents,
)
from app.modules.projects import delivery, moderation
from app.modules.projects.models import Project
from app.modules.tasks.models import Task, TaskDeviceDetail

if TYPE_CHECKING:
    from app.modules.exports.bundle import Entry

FOLDERS = {"FACE_TO_FACE": "face_to_face", "TELEPHONY": "telephonic"}
SPEAKERS = "speakers"
README = "SPEAKER_METADATA_README.json"
MISSING = "MISSING.csv"
MISSING_COLUMNS = [
    "speaker_id",
    "participant_code",
    "conversation_id",
    "task_code",
    "item",
    "detail",
]

# The speaker metadata file's keys, in the client's order, with what each means.
SPEAKER_KEYS: dict[str, str] = {
    "speaker_id": "The speaker's ID in this delivery",
    "age": "Age in years",
    "gender": "male or female",
    "current_residing_district": "District where the speaker lives now",
    "current_residing_state": "State or union territory where the speaker lives now",
    "current_residing_pincode": "PIN code where the speaker lives now",
    "native_state": "State or union territory where the speaker comes from (native place)",
    "native_district": "District where the speaker comes from (native place)",
    "native_language": "The speaker's native language",
    "native_pincode": "PIN code of the speaker's native place",
    "educational_background": "Highest education",
    "medium_of_education": "Medium of education: English or Non-English",
    "speaker_state_during_recording": "State or union territory where the speaker was recorded",
    "speaker_district_during_recording": "District where the speaker was recorded",
    "speaker_pincode_during_recording": "PIN code where the speaker was recorded",
}
# Where each comes from on the participant (participants/speakers.py; `district` is the native
# district).
_SOURCES = {
    "age": "age",
    "gender": "gender",
    "current_residing_district": "current_district",
    "current_residing_state": "current_state",
    "current_residing_pincode": "current_pincode",
    "native_state": "native_state",
    "native_district": "district",
    "native_language": "native_language",
    "native_pincode": "native_pincode",
    "educational_background": "education",
    "medium_of_education": "education_medium",
    "speaker_state_during_recording": "recording_state",
    "speaker_district_during_recording": "recording_district",
    "speaker_pincode_during_recording": "recording_pincode",
}
# The file of one speaker in one conversation: the device details (D-147, filled by the moderator)
# and the call type, then the speaker's QC answers by checklist key (D-146).
CONVERSATION_KEYS: dict[str, str] = {
    "speaker_id": "The speaker's ID in this delivery",
    "device_make": "Make of the device the speaker used",
    "device_model": "Model of the device the speaker used",
    "call_type": "Telephonic or Face-to-face",
    "is_bluetooth_earphones_used": "Yes or No: Bluetooth earphones were used",
    "if_wired_earphones_used": "Yes or No: wired earphones were used",
    "is_loudspeaker_switched_on": "Yes or No: the loudspeaker was on",
}
GENDER_WORDS = {"MALE": "male", "FEMALE": "female"}
EDUCATION_WORDS = {
    "PRIMARY": "Primary School",
    "SECONDARY": "Secondary School",
    "HIGHER_SECONDARY": "Higher Secondary",
    "DIPLOMA": "Diploma",
    "BACHELORS": "Bachelor's Degree",
    "MASTERS": "Master's Degree",
    "PHD": "PhD",
    "OTHER": "Other",
}
MEDIUM_WORDS = {"ENGLISH": "English", "NON_ENGLISH": "Non-English"}
_WORDS = {"gender": GENDER_WORDS, "education": EDUCATION_WORDS, "education_medium": MEDIUM_WORDS}
ANSWER_WORDS = {"yes": "Yes", "no": "No"}
# An uploaded document's extension, from its type (D-144: PDF, JPEG or PNG, kept as uploaded).
EXTENSIONS = {"application/pdf": "pdf", "image/jpeg": "jpg", "image/png": "png"}


def as_json(value: object) -> bytes:
    """A JSON file of the delivery: UTF-8, indented, any script kept as it is."""
    return json.dumps(value, indent=2, ensure_ascii=False).encode("utf-8")


@dataclass(frozen=True)
class Document:
    """An uploaded file to copy into the delivery as it is."""

    key: str
    size: int
    sha256: str
    extension: str


@dataclass
class Speaker:
    """One person in the export, with the files of `speakers/`."""

    participant_id: uuid.UUID
    code: str
    speaker_id: str
    pin: str  # the native PIN code in file names; 000000 when not on file
    language: str
    dialect: str
    metadata: dict[str, str]
    form: Document | None = None  # the signed consent form as uploaded (Upload projects)
    online: bool = False  # no form: the online consent record is written instead
    proof: Document | None = None
    conversations: int = 0

    @property
    def metadata_path(self) -> str:
        return f"{SPEAKERS}/{self.speaker_id}_{self.pin}_METADATA.json"

    @property
    def consent_path(self) -> str | None:
        if self.form is not None:
            return f"{SPEAKERS}/{self.speaker_id}_consent.{self.form.extension}"
        return f"{SPEAKERS}/{self.speaker_id}_consent.html" if self.online else None

    @property
    def proof_path(self) -> str | None:
        if self.proof is None:
            return None
        return f"{SPEAKERS}/{self.speaker_id}_speaker_proof.{self.proof.extension}"


@dataclass(frozen=True)
class Conversation:
    """One recording of the export, named for the client."""

    entry: Entry
    conversation_id: str
    folder: str
    stem: str  # the audio file's name without .wav
    speakers: tuple[Speaker, Speaker]  # A, B
    metadata: tuple[dict[str, str], ...]  # per speaker, A then B; empty without metadata

    @property
    def audio_path(self) -> str:
        return f"{self.folder}/audio/{self.stem}.wav"

    def metadata_path(self, speaker: Speaker) -> str:
        return (
            f"{self.folder}/metadata/"
            f"{speaker.speaker_id}_{self.conversation_id}_{speaker.pin}_METADATA.json"
        )


@dataclass(frozen=True)
class Missing:
    """A value or file not on file: one row of MISSING.csv."""

    speaker_id: str
    participant_code: str
    conversation_id: str
    task_code: str
    item: str
    detail: str

    def row(self) -> list[object]:
        return [
            self.speaker_id,
            self.participant_code,
            self.conversation_id,
            self.task_code,
            self.item,
            self.detail,
        ]


@dataclass
class Plan:
    with_audio: bool
    with_meta: bool
    pattern: str
    speakers: list[Speaker]  # by participant code
    conversations: list[Conversation]  # as the entries
    qc_keys: dict[str, str] = field(default_factory=dict)  # key -> question, as the files carry
    missing: list[Missing] = field(default_factory=list)


class _Gaps:
    """MISSING.csv being gathered: each item once, in the order found."""

    def __init__(self) -> None:
        self.found: dict[tuple[str, str, str], Missing] = {}

    def add(
        self,
        item: str,
        detail: str,
        speaker: Speaker | None = None,
        conversation: tuple[str, str] | None = None,
    ) -> None:
        conv_id, task_code = conversation or ("", "")
        sid = speaker.speaker_id if speaker else ""
        self.found.setdefault(
            (sid, conv_id, item),
            Missing(sid, speaker.code if speaker else "", conv_id, task_code, item, detail),
        )


def _speaker(project: Project, p: Participant) -> Speaker:
    sid = delivery.speaker_id(p.participant_code, project.speaker_id_style)
    metadata = {"speaker_id": sid}
    for key, source in _SOURCES.items():
        value = getattr(p, source)
        if value is None or value == "":
            metadata[key] = ""
        elif source in _WORDS:
            metadata[key] = _WORDS[source].get(str(value), str(value))
        else:
            metadata[key] = str(value)
    return Speaker(
        participant_id=p.id,
        code=p.participant_code,
        speaker_id=sid,
        pin=metadata["native_pincode"] or delivery.NO_PINCODE,
        language=p.language_code,
        dialect=p.dialect,
        metadata=metadata,
    )


def _not_given(key: str) -> str:
    if key == "native_pincode":
        return f"Not given: {delivery.NO_PINCODE} in file names"
    return "Not given"


def _documents(db: Session, project: Project, by_id: dict[uuid.UUID, Speaker]) -> set[uuid.UUID]:
    """Puts each speaker's signed consent form (Upload projects) and address proof in place;
    returns the people with an online answer on the project's consent form."""
    ids = list(by_id)
    kinds = (CONSENT_FORM, ADDRESS_PROOF) if consent.takes_uploads(project) else (ADDRESS_PROOF,)
    for d in db.scalars(current_documents(project.id, ids, kinds)):
        doc = Document(d.storage_key, d.size_bytes, d.sha256, EXTENSIONS.get(d.content_type, "bin"))
        if d.kind == CONSENT_FORM:
            by_id[d.participant_id].form = doc
        else:
            by_id[d.participant_id].proof = doc
    return set(
        db.scalars(
            select(ConsentRecord.participant_id)
            .where(
                ConsentRecord.project_id == project.id,
                ConsentRecord.participant_id.in_(ids),
                ConsentRecord.is_own_answer,
            )
            .distinct()
        )
    )


def _speaker_gaps(project: Project, s: Speaker, gaps: _Gaps) -> None:
    for key, value in s.metadata.items():
        if value == "":
            gaps.add(key, _not_given(key), s)
    if s.form is None:
        if consent.takes_uploads(project):
            gaps.add(
                "consent",
                "No signed consent form uploaded"
                + (": the online consent record is given instead" if s.online else ""),
                s,
            )
        elif not s.online:
            gaps.add("consent", "No consent answer on record", s)
    if s.proof is None:
        gaps.add("speaker_proof", "No address proof uploaded", s)


def _device_values(row: TaskDeviceDetail | None) -> dict[str, str]:
    """The device details in the client's words: text, or Yes / No; "" when not answered."""

    def word(value: object) -> str:
        if value is None:
            return ""
        if isinstance(value, bool):
            return "Yes" if value else "No"
        return str(value)

    names = (*moderation.TEXT_FIELDS, *moderation.YES_NO_FIELDS)
    return {moderation.CLIENT_KEYS[n]: word(getattr(row, n) if row else None) for n in names}


def _conversation_metadata(
    s: Speaker,
    e: Entry,
    conv: tuple[str, str],
    device: TaskDeviceDetail | None,
    snapshot: dict[str, Any] | None,
    current: Sequence[checklist.Item],
    gaps: _Gaps,
) -> dict[str, str]:
    """One speaker's file of one conversation: device details and call type (D-147), then the QC
    answers about the speaker from the newest QC decision (D-146), by checklist key."""
    values = _device_values(device)
    out = {"speaker_id": s.speaker_id}
    for key in ("device_make", "device_model"):
        out[key] = values[key]
    out["call_type"] = moderation.CALL_TYPES.get(e.mode, "")
    for key in ("is_bluetooth_earphones_used", "if_wired_earphones_used"):
        out[key] = values[key]
    out["is_loudspeaker_switched_on"] = values["is_loudspeaker_switched_on"]
    if device is None:
        gaps.add("device_details", "Not filled", s, conv)
    else:
        for key, value in values.items():
            if value == "":
                gaps.add(key, "Not answered", s, conv)
    if snapshot is None:
        items: Sequence[checklist.Item] = current
        answers: dict[str, Any] = {}
        if items:
            gaps.add("qc_answers", "No QC decision with checklist answers yet", s, conv)
    else:
        items = [i for i in checklist.items_of(snapshot.get("items") or []) if i.per_speaker]
        answers = next(
            (
                dict(p.get("answers") or {})
                for p in snapshot.get("participants") or []
                if p.get("participant_id") == str(s.participant_id)
            ),
            {},
        )
    for item in items:
        if item.key in out:  # never over a fixed key
            continue
        out[item.key] = ANSWER_WORDS.get(str(answers.get(item.key)), "")
        if snapshot is not None and out[item.key] == "":
            gaps.add(item.key, "Not answered", s, conv)
    return out


def _snapshots(db: Session, recording_ids: Collection[uuid.UUID]) -> dict[uuid.UUID, Any]:
    """Each recording's newest QC decision with checklist answers (D-146), in one query."""
    if not recording_ids:
        return {}
    return dict(
        db.execute(
            select(AudioQcResult.recording_id, AudioQcResult.checklist)
            .where(
                AudioQcResult.recording_id.in_(list(recording_ids)),
                AudioQcResult.automated.is_(False),
                AudioQcResult.checklist.is_not(None),
            )
            .ext(distinct_on(AudioQcResult.recording_id))
            .order_by(AudioQcResult.recording_id, AudioQcResult.created_at.desc())
        ).all()
    )


def plan(db: Session, project: Project, entries: Sequence[Entry], content: str) -> Plan:
    """What an export in the client's format holds, read for every entry at once: the speakers
    with their details and documents, each conversation's names and speaker files, and what is
    missing. `content`: audio, metadata or both."""
    with_audio, with_meta = content in ("audio", "both"), content in ("metadata", "both")
    pattern = project.audio_name_pattern
    task_ids = [e.task_id for e in entries]
    pairs: dict[uuid.UUID, tuple[uuid.UUID, uuid.UUID]] = (
        {
            tid: (a, b)
            for tid, a, b in db.execute(
                select(Task.id, Task.participant_a_id, Task.participant_b_id).where(
                    Task.id.in_(task_ids)
                )
            )
        }
        if task_ids
        else {}
    )
    ids = {pid for pair in pairs.values() for pid in pair}
    people = (
        list(
            db.scalars(
                select(Participant)
                .where(Participant.id.in_(list(ids)))
                .order_by(Participant.participant_code)
            )
        )
        if ids
        else []
    )
    by_id = {p.id: _speaker(project, p) for p in people}
    gaps = _Gaps()
    devices: dict[tuple[uuid.UUID, uuid.UUID], TaskDeviceDetail] = {}
    snapshots: dict[uuid.UUID, Any] = {}
    current = [i for i in checklist.items_of(project.qc_checklist) if i.per_speaker]
    if with_meta and by_id:
        answered = _documents(db, project, by_id)
        for s in by_id.values():
            s.online = s.form is None and s.participant_id in answered
            _speaker_gaps(project, s, gaps)
        devices = {
            (r.task_id, r.participant_id): r
            for r in db.scalars(
                select(TaskDeviceDetail).where(TaskDeviceDetail.task_id.in_(task_ids))
            )
        }
        snapshots = _snapshots(db, [e.recording_id for e in entries])
    elif with_audio and delivery.uses_pincodes(pattern):
        for s in by_id.values():
            if not s.metadata["native_pincode"]:
                gaps.add("native_pincode", _not_given("native_pincode"), s)
    conversations = []
    for e in entries:
        conv_id = delivery.conversation_id(e.task_code, project.conversation_id_style)
        where = (conv_id, e.task_code)
        a_id, b_id = pairs[e.task_id]
        a, b = by_id[a_id], by_id[b_id]
        a.conversations += 1
        b.conversations += 1
        stem = delivery.audio_name(
            pattern,
            {
                "a": a.speaker_id,
                "b": b.speaker_id,
                "a_pin": a.pin,
                "b_pin": b.pin,
                "conversation": conv_id,
            },
        )
        if with_audio and e.audio is None:
            gaps.add("audio", "No delivery file for this recording", conversation=where)
        metadata: tuple[dict[str, str], ...] = ()
        if with_meta:
            snapshot = snapshots.get(e.recording_id)
            metadata = tuple(
                _conversation_metadata(
                    s, e, where, devices.get((e.task_id, s.participant_id)), snapshot, current, gaps
                )
                for s in (a, b)
            )
        conversations.append(Conversation(e, conv_id, FOLDERS[e.mode], stem, (a, b), metadata))
    qc_keys = {i.key: i.question for i in current}
    for snapshot in snapshots.values():
        for i in checklist.items_of(snapshot.get("items") or []):
            if i.per_speaker:
                qc_keys.setdefault(i.key, i.question)
    return Plan(
        with_audio=with_audio,
        with_meta=with_meta,
        pattern=pattern,
        speakers=list(by_id.values()),
        conversations=conversations,
        qc_keys={k: q for k, q in qc_keys.items() if k not in CONVERSATION_KEYS},
        missing=list(gaps.found.values()),
    )


def readme(p: Plan) -> dict[str, str]:
    """SPEAKER_METADATA_README.json: what each key of the speaker files means, the QC answers by
    their question."""
    meanings = dict(SPEAKER_KEYS)
    for key, meaning in CONVERSATION_KEYS.items():
        meanings.setdefault(key, meaning)
    for key, question in p.qc_keys.items():
        meanings.setdefault(key, f"QC answer, Yes or No: {question}")
    return meanings

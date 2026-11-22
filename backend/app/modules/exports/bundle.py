"""What an export bundle holds and how it is written (EXP-001..008, D-105, D-149).

A bundle is a ZIP, written while it is sent on, so a large project is never held in memory or on
the server's disk. It is laid out as the project says (`projects.export_layout`, D-149): in the
client's delivery format (CLIENT, every project's default; see client.py for its folders), or in
the platform's own layout (PLATFORM):

    face_to_face/audio/      the delivery WAV of each face-to-face recording
    face_to_face/originals/  what the browser recorded, when asked for and still kept
    face_to_face/metadata/   the details file (JSON) of each recording
    face_to_face/consent/    the consent record (HTML) of each recording
    telephony/...            the same four folders for phone recordings
    recordings.csv or .tsv   one row per recording
    recordings.json          the same rows as JSON
    participants.csv / .tsv  the people in these recordings (no names or numbers unless asked for)
    schema/                  the JSON Schemas of the JSON files
    README.txt
    manifest.json, manifest.csv   every file with its size and SHA-256
    SHA256SUMS               the same checksums, for `sha256sum -c SHA256SUMS`

Both layouts end with the same tables (recordings, participants), schema/, README.txt and the
manifests with every file's checksum; the client's format also has MISSING.csv.

Every audio file (and uploaded document) is checked against the checksum recorded when it was
stored; a file that does not match, or that is no longer in storage, stops the export and the
reason names its task or speaker (EXP-005). Phone numbers, names and email addresses are left out
unless the person asking may export personal data and asked for them. The client's format holds
speaker details (age, gender, PIN codes): only people who may see them ask for it or download it
(D-143, D-149). A bundle larger than MAX_BUNDLE_BYTES is refused when it is asked for: storage
takes a streamed object of at most core.storage.STREAM_MAX_BYTES.
"""

from __future__ import annotations

import hashlib
import json
import uuid
import zipfile
from collections.abc import Callable, Generator, Iterator
from dataclasses import asdict, dataclass, field, replace
from datetime import UTC, date, datetime
from typing import Any

from botocore.exceptions import ClientError
from sqlalchemy import Row, or_, select
from sqlalchemy.orm import Session

from app.core.csvio import write_table
from app.core.days import check_days, day_bounds
from app.core.errors import AppError, forbidden
from app.core.permissions import Perm, Role
from app.core.storage import ObjectStorage, is_missing
from app.modules.audio_qc import service as audio_qc
from app.modules.auth.deps import Principal
from app.modules.auth.models import User
from app.modules.auth.security import FieldCipher
from app.modules.exports import client, schemas
from app.modules.exports.models import BUNDLE_CONTENTS, SCOPES, TABLE_FORMATS
from app.modules.participants.models import Participant
from app.modules.projects import delivery
from app.modules.projects.models import Project, ProjectLanguage
from app.modules.recordings import consent_form
from app.modules.recordings.models import (
    DELIVERY_KINDS,
    ORIGINAL_KINDS,
    AudioAsset,
    Recording,
    current_recordings_query,
)
from app.modules.tasks.models import Task, TaskAssignment

MODES = ("FACE_TO_FACE", "TELEPHONY")
FOLDERS = {"FACE_TO_FACE": "face_to_face", "TELEPHONY": "telephony"}
MAX_RECORDINGS = 5000  # one bundle; more is split with the filters
GIB = 1024**3
# The largest bundle asked for, counting its audio: a bundle goes to storage in parts while it is
# written, and storage takes at most 312.5 GiB that way (core.storage.STREAM_MAX_BYTES); the rest
# is room for the details files, tables and uploaded documents.
MAX_BUNDLE_BYTES = 300 * GIB
NO_TRANSCRIPTS = "Not included: this version of the platform makes no transcripts."
# Why a person who may export but not see speaker details gets no bundle in the client's format.
CLIENT_NEEDS_DETAILS = (
    "This project's exports use the client's delivery format, which holds speaker details (age, "
    "gender, PIN codes). Only people who may see speaker details (the project's admins) can "
    "prepare or download them."
)


class BundleError(Exception):
    """The bundle cannot be made; the message is shown to the person who asked for it."""


@dataclass(frozen=True)
class Selection:
    content: str = "both"
    scope: str = "approved"
    table_format: str = "csv"
    mode: str | None = None
    language: str | None = None
    recorded_from: date | None = None
    recorded_to: date | None = None
    originals: bool = False
    contact: bool = False
    # The project's layout when asked for (D-149): not a choice, the project's setting
    # (for_project). PLATFORM for bundles asked for before D-149.
    layout: str = delivery.PLATFORM

    def as_filters(self) -> dict[str, Any]:
        return {
            **asdict(self),
            "recorded_from": self.recorded_from.isoformat() if self.recorded_from else None,
            "recorded_to": self.recorded_to.isoformat() if self.recorded_to else None,
        }

    @classmethod
    def from_filters(cls, filters: dict[str, Any]) -> Selection:
        def day(value: object) -> date | None:
            return date.fromisoformat(value) if isinstance(value, str) and value else None

        return cls(
            content=str(filters.get("content", "both")),
            scope=str(filters.get("scope", "approved")),
            table_format=str(filters.get("table_format", "csv")),
            mode=filters.get("mode") or None,
            language=filters.get("language") or None,
            recorded_from=day(filters.get("recorded_from")),
            recorded_to=day(filters.get("recorded_to")),
            originals=bool(filters.get("originals")),
            contact=bool(filters.get("contact")),
            layout=str(filters.get("layout") or delivery.PLATFORM),
        )


def for_project(sel: Selection, project: Project) -> Selection:
    """The selection laid out as the project's exports are (D-149)."""
    return replace(sel, layout=project.export_layout)


@dataclass(frozen=True)
class FileRef:
    kind: str
    key: str
    size: int
    sha256: str
    extension: str


@dataclass(frozen=True)
class Entry:
    task_id: uuid.UUID
    recording_id: uuid.UUID
    task_code: str
    mode: str
    audio: FileRef | None
    originals: tuple[FileRef, ...]
    duration_ms: int | None


@dataclass
class Written:
    """One file put into the bundle."""

    path: str
    bytes: int
    sha256: str
    kind: str
    mode: str | None = None
    task_code: str | None = None
    recording_id: str | None = None


def _invalid(message: str) -> AppError:
    return AppError(message, code="VALIDATION_ERROR", status_code=422)


def check(db: Session, principal: Principal, project: Project, sel: Selection) -> None:
    """Refuses a selection that makes no sense or that this person may not ask for (EXP-004,
    EXP-008). The same check runs again before a bundle is handed out."""
    if not principal.can_in_project(Perm.EXPORTS_CREATE, project.id):
        raise forbidden()
    if (
        sel.content not in BUNDLE_CONTENTS
        or sel.scope not in SCOPES
        or sel.table_format not in TABLE_FORMATS
        or sel.layout not in delivery.EXPORT_LAYOUTS
    ):
        raise _invalid("Choose what to export")
    # The client's format holds speaker details: for the people who may see them (D-143), not
    # every holder of exports.create (a Client Viewer sees no speaker details).
    if sel.layout == delivery.CLIENT and not principal.can_in_project(
        Perm.PARTICIPANTS_MANAGE, project.id
    ):
        raise forbidden(CLIENT_NEEDS_DETAILS)
    if sel.mode is not None and sel.mode not in MODES:
        raise _invalid("Choose face-to-face or telephony recordings")
    if sel.language is not None:
        known = set(
            db.scalars(
                select(ProjectLanguage.language_code).where(
                    ProjectLanguage.project_id == project.id
                )
            )
        ) | set(
            db.scalars(
                select(Participant.language_code)
                .join(
                    Task,
                    or_(
                        Task.participant_a_id == Participant.id,
                        Task.participant_b_id == Participant.id,
                    ),
                )
                .where(Task.project_id == project.id)
                .distinct()
            )
        )
        if sel.language not in known:
            raise _invalid("This project has no recordings in that language")
    check_days(sel.recorded_from, sel.recorded_to)
    if sel.originals:
        if sel.content == "metadata":
            raise _invalid("Original recordings go with the audio: choose audio or both")
        # What was recorded before any processing: for the people who run the project.
        if not principal.can_in_project(Perm.PROJECTS_MANAGE, project.id):
            raise forbidden()
    # Names, phone numbers and email addresses: only people who may export personal data.
    if sel.contact and not principal.can_in_project(Perm.PARTICIPANTS_EXPORT, project.id):
        raise forbidden()


# A stored file as select_entries reads it, not as a whole row (an audio file's pauses, say):
# recording_id, kind, version, storage_key, size_bytes, sha256, file_extension, duration_ms.
FileRow = Row[uuid.UUID, str, int, str, int, str, str, int]


def _ref(asset: FileRow) -> FileRef:
    return FileRef(
        kind=asset.kind,
        key=asset.storage_key,
        size=int(asset.size_bytes or 0),
        sha256=asset.sha256,
        extension=(asset.file_extension or "bin").lstrip(".").lower(),
    )


def select_entries(
    db: Session,
    project: Project,
    sel: Selection,
    tz_name: str,
    *,
    task_id: uuid.UUID | None = None,
) -> list[Entry]:
    """The current recording of each task that fits the selection (D-135), by task code; with
    `task_id`, of that one task only (D-136). Mode, language and days narrow the tasks in the
    database. Only the columns an entry needs are read: the export summary asks this for every
    change of choice, and whole rows (an audio file's pauses, say) cost more than the rest."""
    newest_q = (
        current_recordings_query()
        .join(Task, Task.id == Recording.task_id)
        .where(Task.project_id == project.id)
    )
    if sel.scope == "approved":
        newest_q = newest_q.where(Task.status == "APPROVED")
    if task_id is not None:
        newest_q = newest_q.where(Task.id == task_id)
    newest = newest_q.subquery()
    query = select(Task.id, Task.task_code, Task.recording_mode, newest.c.recording_id).join(
        newest, newest.c.task_id == Task.id
    )
    if sel.mode:
        query = query.where(Task.recording_mode == sel.mode)
    if sel.language:
        speakers = select(Participant.id).where(Participant.language_code == sel.language)
        query = query.where(
            or_(Task.participant_a_id.in_(speakers), Task.participant_b_id.in_(speakers))
        )
    first, after = day_bounds(sel.recorded_from, sel.recorded_to, tz_name)
    if first is not None:
        query = query.where(newest.c.started_at >= first)
    if after is not None:
        query = query.where(newest.c.started_at < after)
    found = db.execute(query.order_by(Task.task_code).limit(MAX_RECORDINGS + 1)).all()
    if len(found) > MAX_RECORDINGS:
        raise AppError(
            f"More than {MAX_RECORDINGS} recordings: narrow the export by mode, language or days",
            code="TOO_LARGE",
            status_code=422,
        )
    assets: dict[uuid.UUID, list[FileRow]] = {}
    if found:
        for asset in db.execute(
            select(
                AudioAsset.recording_id,
                AudioAsset.kind,
                AudioAsset.version,
                AudioAsset.storage_key,
                AudioAsset.size_bytes,
                AudioAsset.sha256,
                AudioAsset.file_extension,
                AudioAsset.duration_ms,
            )
            .where(
                AudioAsset.recording_id.in_([row.recording_id for row in found]),
                AudioAsset.deleted_at.is_(None),
            )
            .order_by(AudioAsset.kind, AudioAsset.version)
        ):
            assets.setdefault(asset.recording_id, []).append(asset)
    entries = []
    for tid, task_code, mode, recording_id in found:
        mine = assets.get(recording_id, [])
        delivery = [a for a in mine if a.kind in DELIVERY_KINDS]
        final = delivery[-1] if delivery else None  # the newest version
        originals = (
            tuple(_ref(a) for a in mine if a.kind in ORIGINAL_KINDS) if sel.originals else ()
        )
        entries.append(
            Entry(
                task_id=tid,
                recording_id=recording_id,
                task_code=task_code,
                mode=mode,
                audio=_ref(final) if final else None,
                originals=originals,
                duration_ms=final.duration_ms if final else None,
            )
        )
    return entries


def audio_bytes(sel: Selection, entries: list[Entry]) -> int:
    if sel.content == "metadata":
        return 0
    return sum((e.audio.size if e.audio else 0) + sum(o.size for o in e.originals) for e in entries)


def missing_count(db: Session, project: Project, sel: Selection, entries: list[Entry]) -> int:
    """How many values and files a bundle in the client's format would not have (the rows of its
    MISSING.csv, D-149); 0 in the platform's layout, which lists none."""
    if sel.layout != delivery.CLIENT or not entries:
        return 0
    return len(client.plan(db, project, entries, sel.content).missing)


def file_name(
    project: Project, sel: Selection, now: datetime | None = None, task_code: str | None = None
) -> str:
    """both_PRJ0001_20261118_1200.zip; with one task, both_PRJ0001_T000123_20261118_1200.zip."""
    stamp = (now or datetime.now(UTC)).strftime("%Y%m%d_%H%M")
    task = f"_{task_code}" if task_code else ""
    return f"{sel.content}_{project.code}{task}_{stamp}.zip"


def table(columns: list[str], rows: list[list[object]], table_format: str) -> str:
    """A CSV or TSV table as text, with the mark that makes spreadsheet software read it as
    UTF-8 (EXP-007)."""
    return write_table(columns, rows, delimiter="\t" if table_format == "tsv" else ",", bom=True)


class _Sink:
    """A write-only target for ZipFile; what was written is taken out piece by piece."""

    def __init__(self) -> None:
        self._parts: list[bytes] = []

    def write(self, data: bytes, /) -> int:
        self._parts.append(bytes(data))
        return len(data)

    def flush(self) -> None:
        return None

    def close(self) -> None:
        return None

    def take(self) -> bytes:
        data = b"".join(self._parts)
        self._parts.clear()
        return data


def _zip_entry(path: str, method: int) -> zipfile.ZipInfo:
    """A file of the bundle, dated now (UTC), written with `method`: an entry keeps its own
    method, whatever the ZipFile's."""
    now = datetime.now(UTC)
    entry = zipfile.ZipInfo(path, (now.year, now.month, now.day, now.hour, now.minute, now.second))
    entry.compress_type = method
    return entry


class _Zip:
    """The ZIP being written: files go in one by one, `take()` hands on what was written so far,
    and `written` lists every file with its size and checksum."""

    def __init__(self, storage: ObjectStorage | None, written: list[Written]) -> None:
        self.sink = _Sink()
        # Audio and uploaded documents go in stored: a WAV barely shrinks, a PDF or a photo is
        # compressed already, and deflating them costs time. JSON files and tables are deflated.
        self.zf = zipfile.ZipFile(self.sink, mode="w")
        self.storage = storage
        self.written = written

    def take(self) -> bytes:
        return self.sink.take()

    def note(self, path: str, size: int, digest: str, kind: str, e: Entry | None) -> None:
        self.written.append(
            Written(
                path=path,
                bytes=size,
                sha256=digest,
                kind=kind,
                mode=e.mode if e else None,
                task_code=e.task_code if e else None,
                recording_id=str(e.recording_id) if e else None,
            )
        )

    def put(self, path: str, body: bytes, kind: str, e: Entry | None = None) -> None:
        self.zf.writestr(_zip_entry(path, zipfile.ZIP_DEFLATED), body)
        self.note(path, len(body), hashlib.sha256(body).hexdigest(), kind, e)

    def copy(
        self, path: str, key: str, sha256: str, kind: str, e: Entry | None, owner: str
    ) -> Iterator[bytes]:
        """A stored file, read in parts and checked against the checksum recorded when it was
        stored; `owner` (a task or participant code) names it if it does not match, or if it is
        no longer in storage (the database and storage disagree: nothing is left out silently)."""
        assert self.storage is not None  # noqa: S101
        digest = hashlib.sha256()
        size = 0
        try:
            with self.zf.open(_zip_entry(path, zipfile.ZIP_STORED), "w", force_zip64=True) as dest:
                for part in self.storage.iter_bytes(key):
                    dest.write(part)
                    digest.update(part)
                    size += len(part)
                    chunk = self.sink.take()
                    if chunk:
                        yield chunk
        except ClientError as exc:
            if not is_missing(exc):
                raise
            raise BundleError(
                f"A stored file of {owner} is missing from storage: export stopped"
            ) from None
        if digest.hexdigest() != sha256:
            # What is in storage is not what was stored: never hand it on as if it were.
            raise BundleError(
                f"A stored file of {owner} does not match its checksum: export stopped"
            )
        self.note(path, size, sha256, kind, e)

    def finish(self) -> bytes:
        """SHA256SUMS over every file written, then the end of the ZIP."""
        sums = "".join(f"{w.sha256}  {w.path}\n" for w in self.written)
        self.zf.writestr(_zip_entry("SHA256SUMS", zipfile.ZIP_DEFLATED), sums.encode())
        self.zf.close()
        return self.sink.take()


Rows = list[dict[str, Any]]


@dataclass
class Bundle:
    """One export being written. `parts()` gives the ZIP piece by piece; when it has run to its
    end, `written` lists every file that went in, and in the client's format `missing` counts the
    rows of MISSING.csv."""

    db: Session
    storage: ObjectStorage | None
    cipher: FieldCipher | None
    project: Project
    selection: Selection
    entries: list[Entry]
    export_id: str
    requested_by: str
    # Called after each recording (and each speaker): the job says it is still alive (jobs.run).
    on_entry: Callable[[], None] | None = None
    written: list[Written] = field(default_factory=list)
    missing: int = 0

    @property
    def recordings(self) -> int:
        return len(self.entries)

    def parts(self) -> Iterator[bytes]:
        sel = self.selection
        with_audio = sel.content in ("audio", "both")
        with_meta = sel.content in ("metadata", "both")
        plan = (
            client.plan(self.db, self.project, self.entries, sel.content)
            if sel.layout == delivery.CLIENT
            else None
        )
        # The client's format copies uploaded documents with the details.
        if (with_audio or (plan is not None and with_meta)) and self.storage is None:
            raise BundleError("File storage is not configured")
        out = _Zip(self.storage, self.written)
        if plan is not None:
            rows, people = yield from self._client(out, plan)
        else:
            rows, people = yield from self._platform(out, with_audio, with_meta)

        fmt = sel.table_format
        columns = list(schemas.CLIENT_RECORDING_COLUMNS if plan else schemas.RECORDING_COLUMNS)
        out.put(
            f"recordings.{fmt}",
            table(
                columns,
                [
                    [";".join(r[c]) if c == "original_files" else r[c] for c in columns]
                    for r in rows
                ],
                fmt,
            ).encode(),
            "table",
        )
        out.put("recordings.json", json.dumps(rows, indent=2).encode(), "table")
        out.put(f"participants.{fmt}", people.encode(), "table")
        for path, schema in (schemas.CLIENT_FILES if plan else schemas.FILES).items():
            out.put(path, json.dumps(schema, indent=2).encode(), "schema")
        readme = self._client_readme(plan) if plan else self._readme()
        out.put("README.txt", readme.encode(), "readme")

        # The manifests list everything written so far; SHA256SUMS then covers them as well.
        listed = [asdict(w) for w in self.written]
        by_mode = {m: sum(1 for e in self.entries if e.mode == m) for m in MODES}
        counts = {
            "recordings": len(self.entries),
            "face_to_face": by_mode["FACE_TO_FACE"],
            "telephony": by_mode["TELEPHONY"],
            "files": len(listed),
            "bytes": sum(w["bytes"] for w in listed),
        }
        if plan is not None:
            counts["missing"] = self.missing
        manifest = {
            "format": "ccp.export-manifest/1",
            "export_id": self.export_id,
            "created_at": datetime.now(UTC).isoformat(),
            "requested_by": self.requested_by,
            "project": {"code": self.project.code, "name": self.project.name},
            "selection": sel.as_filters(),
            "counts": counts,
            "transcripts": NO_TRANSCRIPTS,
            "files": listed,
        }
        out.put("manifest.json", json.dumps(manifest, indent=2).encode(), "table")
        keys = ["path", "bytes", "sha256", "kind", "mode", "task_code", "recording_id"]
        out.put(
            "manifest.csv",
            table(keys, [[w[k] for k in keys] for w in listed], "csv").encode(),
            "table",
        )
        yield out.finish()

    def _after(self, out: _Zip) -> Iterator[bytes]:
        """Between recordings: forget the rows read, say the job is alive, hand on what is
        written."""
        self.db.expire_all()  # a long export must not keep every row it read
        if self.on_entry is not None:
            self.on_entry()
        chunk = out.take()
        if chunk:
            yield chunk

    def _recording(self, e: Entry) -> tuple[Recording, Task]:
        rec = self.db.get(Recording, e.recording_id)
        task = self.db.get(Task, e.task_id)
        if rec is None or task is None:
            raise BundleError(f"The recording of {e.task_code} is no longer there")
        return rec, task

    def _platform(
        self, out: _Zip, with_audio: bool, with_meta: bool
    ) -> Generator[bytes, None, tuple[Rows, str]]:
        """The platform's own layout (D-105): per mode audio/, originals/, metadata/, consent/."""
        rows: Rows = []
        people: dict[str, dict[str, Any]] = {}
        for e in self.entries:
            folder = FOLDERS[e.mode]
            stem = f"{e.task_code}_{str(e.recording_id)[:8]}"
            audio_path = meta_path = consent_path = None
            original_paths: list[str] = []
            if with_audio and e.audio:
                audio_path = f"{folder}/audio/{stem}.wav"
                yield from out.copy(
                    audio_path, e.audio.key, e.audio.sha256, "audio", e, e.task_code
                )
            if with_audio:
                for ref in e.originals:
                    path = f"{folder}/originals/{stem}_{ref.kind.lower()}.{ref.extension}"
                    yield from out.copy(path, ref.key, ref.sha256, "original", e, e.task_code)
                    original_paths.append(path)
            rec, task = self._recording(e)
            details = audio_qc.metadata_body(self.db, rec, task, self.project)
            if with_meta:
                meta_path = f"{folder}/metadata/{stem}.json"
                out.put(meta_path, json.dumps(details, indent=2).encode(), "metadata", e)
                consent_path = f"{folder}/consent/{stem}.html"
                html = consent_form.render(self.db, rec, task, self.project).encode()
                out.put(consent_path, html, "consent", e)
            rows.append(
                self._row(e, task, details, audio_path, original_paths, meta_path, consent_path)
            )
            for slot in details["participants"]:
                seen = people.setdefault(
                    slot["participant_code"], {"language": slot["language"], "recordings": 0}
                )
                seen["recordings"] += 1
            yield from self._after(out)
        return rows, self._participants(people)

    def _client(self, out: _Zip, plan: client.Plan) -> Generator[bytes, None, tuple[Rows, str]]:
        """The client's delivery format (D-149, client.py): per mode audio/ (and originals/ when
        asked for) and metadata/ (each speaker of each conversation), then speakers/, the
        speaker metadata README and MISSING.csv."""
        rows: Rows = []
        for conv in plan.conversations:
            e = conv.entry
            audio_path = None
            original_paths: list[str] = []
            if plan.with_audio and e.audio:
                audio_path = conv.audio_path
                yield from out.copy(
                    audio_path, e.audio.key, e.audio.sha256, "audio", e, e.task_code
                )
            if plan.with_audio:
                for ref in e.originals:
                    path = f"{conv.folder}/originals/{conv.stem}_{ref.kind.lower()}.{ref.extension}"
                    yield from out.copy(path, ref.key, ref.sha256, "original", e, e.task_code)
                    original_paths.append(path)
            for speaker, values in zip(conv.speakers, conv.metadata, strict=False):
                out.put(conv.metadata_path(speaker), client.as_json(values), "metadata", e)
            rec, task = self._recording(e)
            details = audio_qc.metadata_body(self.db, rec, task, self.project)
            a, b = conv.speakers
            row = self._row(e, task, details, audio_path, original_paths, None, None) | {
                "conversation_id": conv.conversation_id,
                "speaker_a_id": a.speaker_id,
                "speaker_b_id": b.speaker_id,
                "speaker_a_metadata_file": conv.metadata_path(a) if plan.with_meta else None,
                "speaker_b_metadata_file": conv.metadata_path(b) if plan.with_meta else None,
            }
            rows.append({c: row[c] for c in schemas.CLIENT_RECORDING_COLUMNS})
            yield from self._after(out)
        if plan.with_meta:
            for s in plan.speakers:
                out.put(s.metadata_path, client.as_json(s.metadata), "speaker")
                consent_path = s.consent_path
                if s.form is not None and consent_path:
                    yield from out.copy(
                        consent_path, s.form.key, s.form.sha256, "consent", None, s.code
                    )
                elif consent_path:
                    html = consent_form.render_speaker(
                        self.db, self.project, s.participant_id, s.speaker_id, s.code
                    )
                    if html is not None:
                        out.put(consent_path, html.encode(), "consent")
                proof_path = s.proof_path
                if s.proof is not None and proof_path:
                    yield from out.copy(
                        proof_path, s.proof.key, s.proof.sha256, "proof", None, s.code
                    )
                yield from self._after(out)
            out.put(client.README, client.as_json(client.readme(plan)), "readme")
        out.put(
            client.MISSING,
            table(client.MISSING_COLUMNS, [m.row() for m in plan.missing], "csv").encode(),
            "table",
        )
        self.missing = len(plan.missing)
        return rows, self._client_participants(plan)

    def _row(
        self,
        e: Entry,
        task: Task,
        details: dict[str, Any],
        audio_path: str | None,
        original_paths: list[str],
        meta_path: str | None,
        consent_path: str | None,
    ) -> dict[str, Any]:
        a, b = details["participants"]
        dialects = dict(
            self.db.execute(
                select(Participant.participant_code, Participant.dialect).where(
                    Participant.id.in_([task.participant_a_id, task.participant_b_id])
                )
            ).all()
        )
        moderator = self.db.scalar(
            select(User.display_name)
            .join(TaskAssignment, TaskAssignment.user_id == User.id)
            .where(
                TaskAssignment.task_id == task.id,
                TaskAssignment.role_code == Role.MODERATOR.value,
                TaskAssignment.active.is_(True),
            )
            .limit(1)
        )
        final = next(
            (f for f in details["files"] if e.audio and f["sha256"] == e.audio.sha256), None
        )
        checks = details["audio_qc"]
        return {
            "task_code": e.task_code,
            "recording_id": str(e.recording_id),
            "mode": e.mode,
            "task_status": task.status,
            "recorded_at": details["recording"]["started_at"],
            "duration_seconds": round(e.duration_ms / 1000, 1) if e.duration_ms else None,
            "sample_rate": final["sample_rate"] if final else None,
            "bit_depth": final["bit_depth"] if final else None,
            "channels": final["channels"] if final else None,
            "participant_a": a["participant_code"],
            "participant_a_language": a["language"],
            "participant_a_dialect": dialects.get(a["participant_code"], ""),
            "participant_a_consent": a["consent_form_answer"],
            "participant_b": b["participant_code"],
            "participant_b_language": b["language"],
            "participant_b_dialect": dialects.get(b["participant_code"], ""),
            "participant_b_consent": b["consent_form_answer"],
            "moderator": moderator,
            "automatic_check": checks["automatic"]["outcome"] if checks["automatic"] else None,
            "qc_decision": checks["decision"]["outcome"] if checks["decision"] else None,
            "audio_file": audio_path,
            "audio_sha256": e.audio.sha256 if audio_path and e.audio else None,
            "audio_bytes": e.audio.size if audio_path and e.audio else None,
            "original_files": original_paths,
            "metadata_file": meta_path,
            "consent_file": consent_path,
        }

    def _people(self, codes: list[str]) -> dict[str, Participant]:
        if not codes:
            return {}
        return {
            p.participant_code: p
            for p in self.db.scalars(
                select(Participant).where(Participant.participant_code.in_(codes))
            )
        }

    def _contact(self, person: Participant | None) -> list[object]:
        """Name, phone number and email address, for an export that asked for them."""

        def clear(value: str | None) -> str:
            if not value or self.cipher is None:
                return ""
            return self.cipher.decrypt(value)

        if person is None:
            return ["", "", ""]
        return [person.display_label, clear(person.phone_e164_enc), clear(person.email_enc)]

    def _participants(self, people: dict[str, dict[str, Any]]) -> str:
        """The people in these recordings. Names, phone numbers and email addresses only when
        asked for by someone who may export personal data (EXP-004)."""
        contact = self.selection.contact
        columns = ["participant_code", "language", "dialect", "recordings_in_export"]
        if contact:
            columns += ["name", "phone", "email"]
        found = self._people(list(people))
        rows: list[list[object]] = []
        for code in sorted(people):
            person = found.get(code)
            row: list[object] = [
                code,
                people[code]["language"],
                person.dialect if person else "",
                people[code]["recordings"],
            ]
            if contact:
                row += self._contact(person)
            rows.append(row)
        return table(columns, rows, self.selection.table_format)

    def _client_participants(self, plan: client.Plan) -> str:
        """The speakers of the export with their IDs and files in the client's format (D-149);
        names, phone numbers and email addresses as in the platform's layout."""
        contact = self.selection.contact
        columns = [
            "participant_code",
            "speaker_id",
            "language",
            "dialect",
            "recordings_in_export",
            "metadata_file",
            "consent_file",
            "proof_file",
        ]
        if contact:
            columns += ["name", "phone", "email"]
        found = self._people([s.code for s in plan.speakers]) if contact else {}
        rows: list[list[object]] = []
        for s in plan.speakers:
            files = (
                [s.metadata_path, s.consent_path or "", s.proof_path or ""]
                if plan.with_meta
                else ["", "", ""]
            )
            row: list[object] = [
                s.code,
                s.speaker_id,
                s.language,
                s.dialect,
                s.conversations,
                *files,
            ]
            if contact:
                row += self._contact(found.get(s.code))
            rows.append(row)
        return table(columns, rows, self.selection.table_format)

    def _head(self) -> list[str]:
        sel = self.selection
        return [
            f"Export of project {self.project.code} - {self.project.name}",
            f"Made {datetime.now(UTC).strftime('%Y-%m-%d %H:%M')} UTC for {self.requested_by}",
            f"Recordings: {len(self.entries)} "
            f"({'approved tasks only' if sel.scope == 'approved' else 'every finished recording'})",
        ]

    def _tail(self, people: str) -> list[str]:
        sel = self.selection
        fmt = sel.table_format
        return [
            "Tables",
            f"  recordings.{fmt}    one row per recording",
            "  recordings.json    the same rows as JSON",
            f"  participants.{fmt}  {people}",
            "  A value that starts with = + - or @ has an apostrophe put before it, so that",
            "  spreadsheet software shows it as text and never runs it as a formula.",
            "  schema/            the JSON Schemas of the JSON files",
            "",
            "Checking the files",
            "  manifest.json and manifest.csv list every file with its size and SHA-256.",
            "  On Linux or macOS: sha256sum -c SHA256SUMS",
            "",
        ]

    def _readme(self) -> str:
        sel = self.selection
        lines = [
            *self._head(),
            "",
            "Folders",
            "  face_to_face/  recordings made in the browser",
            "  telephony/     recordings of phone calls",
            "  In each: audio/ (16-bit PCM WAV delivery files), originals/ (when asked for),",
            "  metadata/ (details of each recording, JSON), consent/ (consent record, HTML).",
            "",
            *self._tail("the people in these recordings, by code"),
            "Personal data",
            "  Participants are named by code. "
            + (
                "This export also holds their names, phone numbers and email addresses: "
                "keep it accordingly."
                if sel.contact
                else "Names, phone numbers and email addresses are not included."
            ),
            "",
            f"Transcripts: {NO_TRANSCRIPTS}",
            "",
        ]
        return "\n".join(lines)

    def _client_readme(self, plan: client.Plan) -> str:
        """README.txt of the client's delivery format (D-149)."""
        sel = self.selection
        project = self.project
        example = delivery.audio_name(
            plan.pattern,
            {
                "a": delivery.speaker_id("P000001", project.speaker_id_style),
                "b": delivery.speaker_id("P000002", project.speaker_id_style),
                "a_pin": "570001",
                "b_pin": "576101",
                "conversation": delivery.conversation_id("T000001", project.conversation_id_style),
            },
        )
        speaker_ids = (
            "the participant code (P000123)"
            if project.speaker_id_style == "CODE"
            else "the number of the participant code, at least 3 digits (P000123 is 123)"
        )
        conversation_ids = (
            "the task code (T000045)"
            if project.conversation_id_style == "CODE"
            else "CON and the number of the task code, at least 3 digits (T000045 is CON045)"
        )
        lines = [
            *self._head(),
            "Layout: the client's delivery format (the project's Rules tab, card Export)",
            "",
            "Folders",
        ]
        if plan.with_audio:
            lines += [
                "  face_to_face/audio/  each face-to-face recording's delivery WAV (16-bit PCM)",
                "  telephonic/audio/    each phone call's delivery WAV (16-bit PCM)",
                f"  Audio files are named {plan.pattern}.wav, for example {example}.wav:",
                "  {a} and {b} are the two speakers' IDs, {a_pin} and {b_pin} their native PIN",
                "  codes, {conversation} the conversation ID.",
            ]
            if sel.originals:
                lines.append("  originals/ in each:  what was recorded, before any processing")
        if plan.with_meta:
            lines += [
                "  face_to_face/metadata/ and telephonic/metadata/",
                "    <speaker ID>_<conversation ID>_<native PIN code>_METADATA.json: one per",
                "    speaker of each conversation, with the device used, the call type and the",
                "    QC answers about the speaker (Yes or No).",
                "  speakers/  once per speaker:",
                "    <speaker ID>_<native PIN code>_METADATA.json  the speaker's details",
                "    <speaker ID>_consent.pdf (or .jpg, .png)  the signed consent form, uploaded;",
                "    <speaker ID>_consent.html  without one: the speaker's online consent record",
                "    <speaker ID>_speaker_proof.pdf (or .jpg, .png)  the address proof as uploaded",
                "  SPEAKER_METADATA_README.json  what each key of the metadata files means",
            ]
        lines += [
            f"  Speaker IDs: {speaker_ids}.",
            f"  Conversation IDs: {conversation_ids}.",
            "  Transcripts: none (this version of the platform makes no transcripts).",
            "",
            "Missing values and files",
            f"  MISSING.csv lists each one by speaker and conversation: {plan_missing(plan)}.",
            '  In the JSON files a value not on file is "". A native PIN code not on file is',
            f"  {delivery.NO_PINCODE} in file names.",
            "",
            *self._tail("the speakers of this export: code, speaker ID and their files"),
            "Personal data",
            "  Speakers are named by speaker ID and participant code: the metadata files hold no",
            "  names, phone numbers or email addresses. Their details (age, gender, PIN codes)",
            "  can identify a person: keep this export accordingly."
            + (
                " participants also holds their names, phone numbers and email addresses."
                if sel.contact
                else ""
            ),
            "",
        ]
        return "\n".join(lines)


def plan_missing(plan: client.Plan) -> str:
    """ "3 items missing" or "nothing missing", as the export's README says it."""
    n = len(plan.missing)
    if n == 0:
        return "nothing is missing"
    return f"{n} item{'s' if n != 1 else ''} missing"

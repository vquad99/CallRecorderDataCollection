"""What an export bundle holds and how it is written (EXP-001..008, D-105).

A bundle is a ZIP, written while it is sent on, so a large project is never held in memory or on
the server's disk:

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

Every audio file is checked against the checksum recorded when it was stored; a file that does
not match stops the export. Phone numbers, names and email addresses are left out unless the
person asking may export personal data and asked for them.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import uuid
import zipfile
from collections.abc import Callable, Iterator
from dataclasses import asdict, dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import or_, select
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.permissions import Perm
from app.core.storage import ObjectStorage
from app.modules.audio_qc import service as audio_qc
from app.modules.auth.deps import Principal, forbidden
from app.modules.auth.models import User
from app.modules.auth.security import FieldCipher
from app.modules.exports import schemas
from app.modules.exports.models import BUNDLE_CONTENTS, SCOPES, TABLE_FORMATS
from app.modules.participants.models import Participant
from app.modules.projects.models import Project, ProjectLanguage
from app.modules.recordings import consent_form
from app.modules.recordings.models import AudioAsset, Recording
from app.modules.tasks.models import Task, TaskAssignment

MODES = ("FACE_TO_FACE", "TELEPHONY")
FOLDERS = {"FACE_TO_FACE": "face_to_face", "TELEPHONY": "telephony"}
ORIGINAL_KINDS = ("BROWSER_ORIGINAL", "PROVIDER_ORIGINAL_MIXED", "PROVIDER_ORIGINAL_TRACK")
MAX_RECORDINGS = 5000  # one bundle; more is split with the filters
NO_TRANSCRIPTS = "Not included: this version of the platform makes no transcripts."
BOM = "﻿"  # spreadsheet software reads a UTF-8 table correctly only with it (EXP-007)


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
        )


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
    ):
        raise _invalid("Choose what to export")
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
    if sel.recorded_from and sel.recorded_to and sel.recorded_from > sel.recorded_to:
        raise _invalid("The first day must not be after the last day")
    if sel.originals:
        if sel.content == "metadata":
            raise _invalid("Original recordings go with the audio: choose audio or both")
        # What was recorded before any processing: for the people who run the project.
        if not principal.can_in_project(Perm.PROJECTS_MANAGE, project.id):
            raise forbidden()
    # Names, phone numbers and email addresses: only people who may export personal data.
    if sel.contact and not principal.can_in_project(Perm.PARTICIPANTS_EXPORT, project.id):
        raise forbidden()


def _ref(asset: AudioAsset) -> FileRef:
    return FileRef(
        kind=asset.kind,
        key=asset.storage_key,
        size=int(asset.size_bytes or 0),
        sha256=asset.sha256,
        extension=(asset.file_extension or "bin").lstrip(".").lower(),
    )


def select_entries(db: Session, project: Project, sel: Selection, tz_name: str) -> list[Entry]:
    """The newest finished recording of each task that fits the selection, by task code."""
    newest = (
        select(Recording)
        .join(Task, Task.id == Recording.task_id)
        .where(Task.project_id == project.id, Recording.state == "READY")
        .ext(distinct_on(Recording.task_id))
        .order_by(Recording.task_id, Recording.started_at.desc())
    )
    if sel.scope == "approved":
        newest = newest.where(Task.status == "APPROVED")
    recordings = {r.task_id: r for r in db.scalars(newest)}
    if not recordings:
        return []
    tasks = list(
        db.scalars(select(Task).where(Task.id.in_(list(recordings))).order_by(Task.task_code))
    )
    if sel.mode:
        tasks = [t for t in tasks if t.recording_mode == sel.mode]
    if sel.language:
        speakers = set(
            db.scalars(select(Participant.id).where(Participant.language_code == sel.language))
        )
        tasks = [
            t for t in tasks if t.participant_a_id in speakers or t.participant_b_id in speakers
        ]
    zone = ZoneInfo(tz_name)
    first = datetime.combine(sel.recorded_from, time.min, zone) if sel.recorded_from else None
    after = (
        datetime.combine(sel.recorded_to + timedelta(days=1), time.min, zone)
        if sel.recorded_to
        else None
    )

    def in_days(rec: Recording) -> bool:
        if first is None and after is None:
            return True
        at = rec.started_at
        if at is None:
            return False
        return (first is None or at >= first) and (after is None or at < after)

    tasks = [t for t in tasks if in_days(recordings[t.id])]
    if len(tasks) > MAX_RECORDINGS:
        raise AppError(
            f"More than {MAX_RECORDINGS} recordings: narrow the export by mode, language or days",
            code="TOO_LARGE",
            status_code=422,
        )
    wanted = [recordings[t.id].id for t in tasks]
    assets: dict[uuid.UUID, list[AudioAsset]] = {}
    if wanted:
        for asset in db.scalars(
            select(AudioAsset)
            .where(AudioAsset.recording_id.in_(wanted), AudioAsset.deleted_at.is_(None))
            .order_by(AudioAsset.kind, AudioAsset.version)
        ):
            assets.setdefault(asset.recording_id, []).append(asset)
    entries = []
    for task in tasks:
        rec = recordings[task.id]
        mine = assets.get(rec.id, [])
        delivery = [a for a in mine if a.kind in audio_qc.DELIVERY_KINDS]
        final = delivery[-1] if delivery else None  # the newest version
        originals = (
            tuple(_ref(a) for a in mine if a.kind in ORIGINAL_KINDS) if sel.originals else ()
        )
        entries.append(
            Entry(
                task_id=task.id,
                recording_id=rec.id,
                task_code=task.task_code,
                mode=task.recording_mode,
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


def file_name(project: Project, sel: Selection, now: datetime | None = None) -> str:
    stamp = (now or datetime.now(UTC)).strftime("%Y%m%d_%H%M")
    return f"{sel.content}_{project.code}_{stamp}.zip"


def safe_cell(value: object) -> str:
    """A cell that spreadsheet software will not run as a formula."""
    text = "" if value is None else str(value)
    return "'" + text if text[:1] in ("=", "+", "-", "@", "\t", "\r") else text


def table(columns: list[str], rows: list[list[object]], table_format: str) -> str:
    """A CSV or TSV table as text, with the mark that makes spreadsheet software read it as
    UTF-8 (EXP-007)."""
    out = io.StringIO()
    writer = csv.writer(out, delimiter="\t" if table_format == "tsv" else ",")
    writer.writerow(columns)
    for row in rows:
        writer.writerow([safe_cell(v) for v in row])
    return BOM + out.getvalue()


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


def _zip_time() -> tuple[int, int, int, int, int, int]:
    now = datetime.now(UTC)
    return (now.year, now.month, now.day, now.hour, now.minute, now.second)


@dataclass
class Bundle:
    """One export being written. `parts()` gives the ZIP piece by piece; when it has run to its
    end, `written` lists every file that went in."""

    db: Session
    storage: ObjectStorage | None
    cipher: FieldCipher | None
    project: Project
    selection: Selection
    entries: list[Entry]
    export_id: str
    requested_by: str
    # Called after each recording: the job says it is still alive (jobs.run).
    on_entry: Callable[[], None] | None = None
    written: list[Written] = field(default_factory=list)

    @property
    def recordings(self) -> int:
        return len(self.entries)

    def parts(self) -> Iterator[bytes]:
        sel = self.selection
        with_audio = sel.content in ("audio", "both")
        with_meta = sel.content in ("metadata", "both")
        if with_audio and self.storage is None:
            raise BundleError("File storage is not configured")
        sink = _Sink()
        zf = zipfile.ZipFile(sink, mode="w", compression=zipfile.ZIP_DEFLATED, compresslevel=1)

        def note(path: str, size: int, digest: str, kind: str, e: Entry | None) -> None:
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

        def put(path: str, body: bytes, kind: str, e: Entry | None = None) -> None:
            zf.writestr(zipfile.ZipInfo(path, _zip_time()), body)
            note(path, len(body), hashlib.sha256(body).hexdigest(), kind, e)

        def copy(path: str, ref: FileRef, kind: str, e: Entry) -> Iterator[bytes]:
            assert self.storage is not None  # noqa: S101
            digest = hashlib.sha256()
            size = 0
            with zf.open(zipfile.ZipInfo(path, _zip_time()), "w", force_zip64=True) as dest:
                for part in self.storage.iter_bytes(ref.key):
                    dest.write(part)
                    digest.update(part)
                    size += len(part)
                    chunk = sink.take()
                    if chunk:
                        yield chunk
            if digest.hexdigest() != ref.sha256:
                # What is in storage is not what was stored: never hand it on as if it were.
                raise BundleError(
                    f"A stored file of {e.task_code} does not match its checksum: export stopped"
                )
            note(path, size, ref.sha256, kind, e)

        rows: list[dict[str, Any]] = []
        people: dict[str, dict[str, Any]] = {}
        for e in self.entries:
            folder = FOLDERS[e.mode]
            stem = f"{e.task_code}_{str(e.recording_id)[:8]}"
            audio_path = meta_path = consent_path = None
            original_paths: list[str] = []
            if with_audio and e.audio:
                audio_path = f"{folder}/audio/{stem}.wav"
                yield from copy(audio_path, e.audio, "audio", e)
            if with_audio:
                for ref in e.originals:
                    path = f"{folder}/originals/{stem}_{ref.kind.lower()}.{ref.extension}"
                    yield from copy(path, ref, "original", e)
                    original_paths.append(path)
            rec = self.db.get(Recording, e.recording_id)
            task = self.db.get(Task, e.task_id)
            if rec is None or task is None:
                raise BundleError(f"The recording of {e.task_code} is no longer there")
            details = audio_qc.metadata_body(self.db, rec, task, self.project)
            if with_meta:
                meta_path = f"{folder}/metadata/{stem}.json"
                put(meta_path, json.dumps(details, indent=2).encode(), "metadata", e)
                consent_path = f"{folder}/consent/{stem}.html"
                html = consent_form.render(self.db, rec, task, self.project).encode()
                put(consent_path, html, "consent", e)
            rows.append(
                self._row(e, task, details, audio_path, original_paths, meta_path, consent_path)
            )
            for slot in details["participants"]:
                seen = people.setdefault(
                    slot["participant_code"], {"language": slot["language"], "recordings": 0}
                )
                seen["recordings"] += 1
            self.db.expire_all()  # a long export must not keep every row it read
            if self.on_entry is not None:
                self.on_entry()
            chunk = sink.take()
            if chunk:
                yield chunk

        fmt = sel.table_format
        columns = list(schemas.RECORDING_COLUMNS)
        put(
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
        put("recordings.json", json.dumps(rows, indent=2).encode(), "table")
        put(f"participants.{fmt}", self._participants(people).encode(), "table")
        for path, schema in schemas.FILES.items():
            put(path, json.dumps(schema, indent=2).encode(), "schema")
        put("README.txt", self._readme().encode(), "readme")

        # The manifests list everything written so far; SHA256SUMS then covers them as well.
        listed = [asdict(w) for w in self.written]
        by_mode = {m: sum(1 for e in self.entries if e.mode == m) for m in MODES}
        manifest = {
            "format": "ccp.export-manifest/1",
            "export_id": self.export_id,
            "created_at": datetime.now(UTC).isoformat(),
            "requested_by": self.requested_by,
            "project": {"code": self.project.code, "name": self.project.name},
            "selection": sel.as_filters(),
            "counts": {
                "recordings": len(self.entries),
                "face_to_face": by_mode["FACE_TO_FACE"],
                "telephony": by_mode["TELEPHONY"],
                "files": len(listed),
                "bytes": sum(w["bytes"] for w in listed),
            },
            "transcripts": NO_TRANSCRIPTS,
            "files": listed,
        }
        put("manifest.json", json.dumps(manifest, indent=2).encode(), "table")
        keys = ["path", "bytes", "sha256", "kind", "mode", "task_code", "recording_id"]
        put(
            "manifest.csv",
            table(keys, [[w[k] for k in keys] for w in listed], "csv").encode(),
            "table",
        )
        sums = "".join(f"{w.sha256}  {w.path}\n" for w in self.written)
        zf.writestr(zipfile.ZipInfo("SHA256SUMS", _zip_time()), sums.encode())
        zf.close()
        yield sink.take()

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
                TaskAssignment.role_code == "MODERATOR",
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
            "participant_a_consent": a["session_consent"],
            "participant_b": b["participant_code"],
            "participant_b_language": b["language"],
            "participant_b_dialect": dialects.get(b["participant_code"], ""),
            "participant_b_consent": b["session_consent"],
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

    def _participants(self, people: dict[str, dict[str, Any]]) -> str:
        """The people in these recordings. Names, phone numbers and email addresses only when
        asked for by someone who may export personal data (EXP-004)."""
        contact = self.selection.contact
        columns = ["participant_code", "language", "dialect", "recordings_in_export"]
        if contact:
            columns += ["name", "phone", "email"]
        found = (
            {
                p.participant_code: p
                for p in self.db.scalars(
                    select(Participant).where(Participant.participant_code.in_(list(people)))
                )
            }
            if people
            else {}
        )

        def clear(value: str | None) -> str:
            if not value or self.cipher is None:
                return ""
            return self.cipher.decrypt(value)

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
                row += [
                    person.display_label if person else "",
                    clear(person.phone_e164_enc) if person else "",
                    clear(person.email_enc) if person else "",
                ]
            rows.append(row)
        return table(columns, rows, self.selection.table_format)

    def _readme(self) -> str:
        sel = self.selection
        fmt = sel.table_format
        lines = [
            f"Export of project {self.project.code} - {self.project.name}",
            f"Made {datetime.now(UTC).strftime('%Y-%m-%d %H:%M')} UTC for {self.requested_by}",
            f"Recordings: {len(self.entries)} "
            f"({'approved tasks only' if sel.scope == 'approved' else 'every finished recording'})",
            "",
            "Folders",
            "  face_to_face/  recordings made in the browser",
            "  telephony/     recordings of phone calls",
            "  In each: audio/ (16-bit PCM WAV delivery files), originals/ (when asked for),",
            "  metadata/ (details of each recording, JSON), consent/ (consent record, HTML).",
            "",
            "Tables",
            f"  recordings.{fmt}    one row per recording",
            "  recordings.json    the same rows as JSON",
            f"  participants.{fmt}  the people in these recordings, by code",
            "  A value that starts with = + - or @ has an apostrophe put before it, so that",
            "  spreadsheet software shows it as text and never runs it as a formula.",
            "  schema/            the JSON Schemas of the JSON files",
            "",
            "Checking the files",
            "  manifest.json and manifest.csv list every file with its size and SHA-256.",
            "  On Linux or macOS: sha256sum -c SHA256SUMS",
            "",
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

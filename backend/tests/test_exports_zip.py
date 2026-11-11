"""The export ZIP is streamed in parts and carries its manifest (D-094). No database needed.

Requirements: EXP-002, EXP-005
"""

from __future__ import annotations

import contextlib
import csv
import io
import uuid
import zipfile
from collections.abc import Iterator

from app.modules.exports import service
from app.modules.projects.models import Project


class _Store:
    def __init__(self, files: dict[str, bytes]) -> None:
        self.files = files

    def iter_bytes(self, key: str, part_size: int = 4) -> Iterator[bytes]:
        data = self.files[key]
        for i in range(0, len(data), part_size):
            yield data[i : i + part_size]


def test_the_zip_streams_in_parts_and_opens_with_its_manifest() -> None:
    entries = [
        service.Entry(
            task_id=uuid.uuid4(),
            recording_id=uuid.uuid4(),
            task_code=code,
            audio_key=f"k/{code}",
            audio_size=12,
            audio_sha256="ab" * 32,
            duration_ms=4000,
        )
        for code in ("T000001", "T000002")
    ]
    plan = service.Plan(
        project=Project(code="VOICE", name="Voice"),
        content="audio",
        scope="approved",
        entries=entries,
        total_bytes=24,
    )
    store = _Store({"k/T000001": b"RIFF-one-wav", "k/T000002": b"RIFF-two-wav"})
    parts = list(service.stream_zip(plan, store, lambda: contextlib.nullcontext(None)))  # type: ignore[arg-type,return-value]
    assert len(parts) > 2, "sent in parts, not built whole"
    archive = zipfile.ZipFile(io.BytesIO(b"".join(parts)))
    names = sorted(archive.namelist())
    assert names[-1] == "manifest.csv"
    audio = [n for n in names if n.startswith("audio/")]
    assert len(audio) == 2
    assert archive.read(audio[0]) in (b"RIFF-one-wav", b"RIFF-two-wav")
    rows = list(csv.DictReader(io.StringIO(archive.read("manifest.csv").decode())))
    assert [r["task_code"] for r in rows] == ["T000001", "T000002"]
    assert rows[0]["metadata_file"] == "", "audio only"

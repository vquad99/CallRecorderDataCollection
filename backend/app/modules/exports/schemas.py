"""The JSON Schemas of an export bundle's JSON files (EXP-003).

Each bundle carries these under `schema/`, so whoever receives it can check the files against
them. The tests check every JSON file of a real bundle against its schema.
"""

from __future__ import annotations

from typing import Any

DRAFT = "https://json-schema.org/draft/2020-12/schema"
_STR = {"type": "string"}
_STR_OR_NULL = {"type": ["string", "null"]}
_INT = {"type": "integer"}
_INT_OR_NULL = {"type": ["integer", "null"]}
_NUM_OR_NULL = {"type": ["number", "null"]}
_BOOL_OR_NULL = {"type": ["boolean", "null"]}
_MODE = {"enum": ["FACE_TO_FACE", "TELEPHONY"]}
_SHA = {"type": "string", "pattern": "^[0-9a-f]{64}$"}
_CONSENT = {"enum": ["GIVEN", "REFUSED", "WITHDRAWN", None]}


def _object(properties: dict[str, Any], *, open_: bool = False) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": sorted(properties),
        "additionalProperties": open_,
    }


# One row per recording: recordings.json holds a list of these, recordings.csv / .tsv the same
# columns in the same order.
RECORDING_ROW: dict[str, Any] = _object(
    {
        "task_code": _STR,
        "recording_id": {"type": "string", "format": "uuid"},
        "mode": _MODE,
        "task_status": _STR,
        "recorded_at": _STR_OR_NULL,
        "duration_seconds": _NUM_OR_NULL,
        "sample_rate": _INT_OR_NULL,
        "bit_depth": _INT_OR_NULL,
        "channels": _INT_OR_NULL,
        "participant_a": _STR,
        "participant_a_language": _STR,
        "participant_a_dialect": _STR,
        "participant_a_consent": _CONSENT,
        "participant_b": _STR,
        "participant_b_language": _STR,
        "participant_b_dialect": _STR,
        "participant_b_consent": _CONSENT,
        "moderator": _STR_OR_NULL,
        "automatic_check": _STR_OR_NULL,
        "qc_decision": _STR_OR_NULL,
        "audio_file": _STR_OR_NULL,
        "audio_sha256": {"anyOf": [_SHA, {"type": "null"}]},
        "audio_bytes": _INT_OR_NULL,
        "original_files": {"type": "array", "items": _STR},
        "metadata_file": _STR_OR_NULL,
        "consent_file": _STR_OR_NULL,
    }
)
RECORDING_COLUMNS: tuple[str, ...] = tuple(RECORDING_ROW["properties"])

RECORDINGS: dict[str, Any] = {
    "$schema": DRAFT,
    "$id": "ccp.export-recordings/1",
    "title": "Recordings in an export bundle",
    "type": "array",
    "items": RECORDING_ROW,
}

_FILE = _object(
    {
        "path": _STR,
        "bytes": {"type": "integer", "minimum": 0},
        "sha256": _SHA,
        "kind": {"enum": ["audio", "original", "metadata", "consent", "table", "schema", "readme"]},
        "mode": {"anyOf": [_MODE, {"type": "null"}]},
        "task_code": _STR_OR_NULL,
        "recording_id": _STR_OR_NULL,
    }
)

MANIFEST: dict[str, Any] = {
    "$schema": DRAFT,
    "$id": "ccp.export-manifest/1",
    "title": "What an export bundle holds",
    **_object(
        {
            "format": {"const": "ccp.export-manifest/1"},
            "export_id": _STR,
            "created_at": _STR,
            "requested_by": _STR,
            "project": _object({"code": _STR, "name": _STR}),
            "selection": _object(
                {
                    "content": {"enum": ["audio", "metadata", "both"]},
                    "scope": {"enum": ["approved", "finished"]},
                    "table_format": {"enum": ["csv", "tsv"]},
                    "mode": {"anyOf": [_MODE, {"type": "null"}]},
                    "language": _STR_OR_NULL,
                    "recorded_from": _STR_OR_NULL,
                    "recorded_to": _STR_OR_NULL,
                    "originals": {"type": "boolean"},
                    "contact": {"type": "boolean"},
                }
            ),
            "counts": _object(
                {
                    "recordings": _INT,
                    "face_to_face": _INT,
                    "telephony": _INT,
                    "files": _INT,
                    "bytes": _INT,
                }
            ),
            "transcripts": _STR,
            "files": {"type": "array", "items": _FILE},
        }
    ),
}

# The details file of one recording (audio_qc.metadata_body). The measured values of a check and
# the parameters of a processing step differ by tool, so those two stay open.
_PARTICIPANT = _object(
    {
        "slot": {"enum": ["A", "B"]},
        "participant_code": _STR,
        "language": _STR,
        "session_consent": _CONSENT,
        "session_consent_at": _STR_OR_NULL,
        "session_consent_method": _STR_OR_NULL,
        "consent_form_answer": _CONSENT,
        "consent_form_version": _STR_OR_NULL,
        "consent_form_review": _STR_OR_NULL,
    }
)
_STEP = _object(
    {
        "tool": _STR,
        "tool_version": _STR_OR_NULL,
        "parameters": {},
        "input_sha256": _STR_OR_NULL,
        "output_sha256": _STR_OR_NULL,
    }
)
_ASSET = _object(
    {
        "id": _STR,
        "kind": _STR,
        "version": _INT,
        "derived_from": _STR_OR_NULL,
        "container": _STR,
        "codec": _STR,
        "sample_format": _STR,
        "sample_rate": _INT,
        "bit_depth": _INT,
        "channels": _INT,
        "duration_ms": _INT,
        "size_bytes": _INT,
        "sha256": _SHA,
        "peak_dbfs": _NUM_OR_NULL,
        "rms_dbfs": _NUM_OR_NULL,
        "clip_count": _INT,
        "clip_pct": {"type": "number"},
        "silence_pct": _NUM_OR_NULL,
        "dynamic_range_db": _NUM_OR_NULL,
        "content_fingerprint": _STR_OR_NULL,
        "created_at": _STR_OR_NULL,
        "processing": {"type": "array", "items": _STEP},
    }
)
_CHECK = _object(
    {
        "code": _STR,
        "state": _STR,
        "measured": {},
        "expected": {},
        "message": _STR_OR_NULL,
    }
)
_AUTOMATIC = _object(
    {
        "outcome": _STR,
        "reason_code": _STR_OR_NULL,
        "summary": _STR_OR_NULL,
        "checked_at": _STR_OR_NULL,
        "checks": {"type": "array", "items": _CHECK},
    }
)
_DECISION = _object(
    {
        "outcome": _STR,
        "reason_code": _STR_OR_NULL,
        "comment": _STR_OR_NULL,
        "reviewer_id": _STR_OR_NULL,
        "decided_at": _STR_OR_NULL,
    }
)

RECORDING_METADATA: dict[str, Any] = {
    "$schema": DRAFT,
    "$id": "ccp.recording-metadata/1",
    "title": "Details of one recording",
    "type": "object",
    "properties": {
        "format": {"const": "ccp.recording-metadata/1"},
        "generated_at": _STR,
        "project": _object({"code": _STR, "name": _STR}),
        "session": _object({"task_code": _STR, "recording_mode": _MODE, "status": _STR}),
        "participants": {"type": "array", "items": _PARTICIPANT, "minItems": 2, "maxItems": 2},
        "recording": _object(
            {
                "id": _STR,
                "state": _STR,
                "started_at": _STR_OR_NULL,
                "ended_at": _STR_OR_NULL,
                "native_sample_rate": _INT_OR_NULL,
                "channel_count": _INT_OR_NULL,
                "device_channel_count": _INT_OR_NULL,
                "channel_handling": _STR_OR_NULL,
                "echo_cancellation": _BOOL_OR_NULL,
                "noise_suppression": _BOOL_OR_NULL,
                "auto_gain_control": _BOOL_OR_NULL,
                "device_label": _STR_OR_NULL,
                "user_agent": _STR_OR_NULL,
                "parts_received": _INT_OR_NULL,
                "interrupted": _BOOL_OR_NULL,
                "interruption_reason": _STR_OR_NULL,
            }
        ),
        "files": {"type": "array", "items": _ASSET},
        "audio_qc": _object(
            {
                "automatic": {"anyOf": [_AUTOMATIC, {"type": "null"}]},
                "decision": {"anyOf": [_DECISION, {"type": "null"}]},
            }
        ),
        # Phone calls only: how the call went (D-103). Its content follows the call's history.
        "call": {"type": "object"},
    },
    "required": [
        "format",
        "generated_at",
        "project",
        "session",
        "participants",
        "recording",
        "files",
        "audio_qc",
    ],
    "additionalProperties": False,
}

# File name in the bundle -> schema.
FILES: dict[str, dict[str, Any]] = {
    "schema/recordings.schema.json": RECORDINGS,
    "schema/manifest.schema.json": MANIFEST,
    "schema/recording-metadata.schema.json": RECORDING_METADATA,
}

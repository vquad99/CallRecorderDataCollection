"""The tables of an export open in spreadsheet software, a selection survives being stored, and
a bundle goes to storage as it is written (D-105). No database needed.

Requirements: EXP-002, EXP-003, EXP-007
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
from datetime import date

import jsonschema

from app.core.storage import _PartsReader
from app.modules.exports import bundle, schemas

ROWS: list[list[object]] = [["आशा राव", "=1+1", 7], ["Bina", "a,b\tc", None], ["Chitra", "-2", 0]]
EXPECTED = [
    ["name", "note", "count"],
    ["आशा राव", "'=1+1", "7"],
    ["Bina", "a,b\tc", ""],
    ["Chitra", "'-2", "0"],
]


def test_tables_carry_the_utf8_mark_and_never_a_formula() -> None:
    as_csv = bundle.table(["name", "note", "count"], ROWS, "csv")
    # The mark makes spreadsheet software read the file as UTF-8, so names in any script show.
    assert as_csv.encode("utf-8")[:3] == b"\xef\xbb\xbf"
    assert list(csv.reader(io.StringIO(as_csv.lstrip("\ufeff")))) == EXPECTED
    as_tsv = bundle.table(["name", "note", "count"], ROWS, "tsv")
    assert as_tsv.splitlines()[0] == "\ufeffname\tnote\tcount"
    assert list(csv.reader(io.StringIO(as_tsv.lstrip("\ufeff")), delimiter="\t")) == EXPECTED


def test_a_selection_is_stored_and_read_back_unchanged() -> None:
    sel = bundle.Selection(
        content="audio",
        scope="finished",
        table_format="tsv",
        mode="TELEPHONY",
        language="hi",
        recorded_from=date(2026, 11, 1),
        recorded_to=date(2026, 11, 14),
        originals=True,
    )
    assert bundle.Selection.from_filters(json.loads(json.dumps(sel.as_filters()))) == sel
    assert bundle.Selection.from_filters({}) == bundle.Selection()


def test_the_schemas_are_valid_and_name_every_column_once() -> None:
    for schema in schemas.FILES.values():
        jsonschema.Draft202012Validator.check_schema(schema)
    columns = schemas.RECORDING_COLUMNS
    assert columns[0] == "task_code"
    assert len(set(columns)) == len(columns)
    assert set(columns) == set(schemas.RECORDING_ROW["required"])


def test_parts_are_read_as_one_file_with_its_size_and_checksum() -> None:
    reader = _PartsReader(iter([b"abc", b"", b"defgh"]))
    first = bytearray(2)
    assert reader.readinto(first) == 2
    assert bytes(first) == b"ab"
    rest = reader.read()
    assert rest == b"cdefgh"
    assert reader.read() == b""
    assert (reader.size, reader.sha256) == (8, hashlib.sha256(b"abcdefgh").hexdigest())

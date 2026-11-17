"""CSV and TSV in and out: the one place tables are read from and written for people.

Writing: every cell goes through `safe_cell`, so spreadsheet software never runs a value as a
formula (D-088). Reading: the header is checked, the row count capped, and every row comes back
with its line number, lower-case column names and trimmed values.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Collection, Iterable, Sequence
from dataclasses import dataclass

from app.core.errors import AppError

BOM = "﻿"  # spreadsheet software reads a UTF-8 table correctly only with it (EXP-007)
_FORMULA_START = ("=", "+", "-", "@", "\t", "\r")


def safe_cell(value: object) -> str:
    """A cell that spreadsheet software will not run as a formula."""
    text = "" if value is None else str(value)
    return "'" + text if text.startswith(_FORMULA_START) else text


def write_table(
    columns: Sequence[str],
    rows: Iterable[Sequence[object]],
    *,
    delimiter: str = ",",
    bom: bool = False,
) -> str:
    """A table as text: the header, then every row with each cell made safe."""
    out = io.StringIO()
    writer = csv.writer(out, delimiter=delimiter)
    writer.writerow(columns)
    writer.writerows([safe_cell(v) for v in row] for row in rows)
    return (BOM if bom else "") + out.getvalue()


@dataclass(frozen=True)
class CsvRow:
    line: int  # the line in the file (the header is line 1)
    values: dict[str, str]  # lower-case column name -> trimmed value
    extra: bool  # the line has more values than the header has columns


def read_rows(
    text: str,
    columns: Sequence[str],
    *,
    required: Collection[str] | None = None,
    max_rows: int,
    noun: str,
) -> list[CsvRow]:
    """The rows of an uploaded CSV file.

    The header must hold the `required` columns (any order, others allowed), or, with
    `required=None`, exactly `columns` in that order; otherwise 422 INVALID_CSV (INVALID_CSV_HEADER
    for an exact header). More than `max_rows` rows: 422 TOO_MANY_ROWS."""
    reader = csv.DictReader(io.StringIO(text.removeprefix(BOM)))
    header = [(h or "").strip().lower() for h in (reader.fieldnames or [])]
    if required is None and tuple(header) != tuple(columns):
        raise AppError(
            f"CSV header must be exactly: {','.join(columns)}",
            code="INVALID_CSV_HEADER",
            status_code=422,
        )
    if required is not None and not set(required) <= set(header):
        raise AppError(
            f"The first line must name the columns: {','.join(columns)}",
            code="INVALID_CSV",
            status_code=422,
        )
    rows: list[CsvRow] = []
    for line, raw in enumerate(reader, start=2):
        if len(rows) == max_rows:
            raise AppError(
                f"At most {max_rows} {noun} per file", code="TOO_MANY_ROWS", status_code=422
            )
        # csv puts values beyond the header under the key None, as a list (D-088: was a 500).
        extra = raw.pop(None, None)
        values = {(k or "").strip().lower(): (v or "").strip() for k, v in raw.items()}
        rows.append(CsvRow(line, values, bool(extra)))
    return rows

"""CSV and TSV in and out: the one place tables are read from and written for people.

Writing: every cell goes through `safe_cell`, so spreadsheet software never runs a value as a
formula (D-088); a number the server worked out is written as the number it is. Reading: the
header is checked, the row count capped, and every row comes back with its line number,
lower-case column names and trimmed values; a file the csv module cannot read (a value over its
size limit, often a quote never closed) is 422 INVALID_CSV, not a 500.
"""

from __future__ import annotations

import csv
import io
import math
from collections.abc import Collection, Iterable, Sequence
from dataclasses import dataclass
from decimal import Decimal

from app.core.errors import AppError

BOM = "﻿"  # spreadsheet software reads a UTF-8 table correctly only with it (EXP-007)
_FORMULA_START = ("=", "+", "-", "@", "\t", "\r")
UNREADABLE = "The file could not be read: a value is too long or a quote is not closed"


def _finite_number(value: object) -> bool:
    """A number (not True or False, which are text here), and one a spreadsheet can show."""
    if isinstance(value, bool) or not isinstance(value, int | float | Decimal):
        return False
    if isinstance(value, Decimal):
        return value.is_finite()
    return math.isfinite(value)


def safe_cell(value: object) -> str:
    """A cell that spreadsheet software will not run as a formula. Text starting with = + - @, a
    tab or a carriage return gets a ' in front; a number (int, float, Decimal) is written as it
    is, so a negative one such as a variance of -6.0 stays a number (it cannot be a formula)."""
    if _finite_number(value):
        return str(value)
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
    for an exact header). More than `max_rows` rows: 422 TOO_MANY_ROWS. A file the csv module
    cannot read (a value over its limit of 131 072 characters, which a quote never closed
    causes): 422
    INVALID_CSV, for every import that reads through here (participants, users, tasks)."""
    reader = csv.DictReader(io.StringIO(text.removeprefix(BOM)))
    try:
        header = [(h or "").strip().lower() for h in (reader.fieldnames or [])]
    except csv.Error:
        raise AppError(UNREADABLE, code="INVALID_CSV", status_code=422) from None
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
    try:
        for line, raw in enumerate(reader, start=2):
            if len(rows) == max_rows:
                raise AppError(
                    f"At most {max_rows} {noun} per file", code="TOO_MANY_ROWS", status_code=422
                )
            # csv puts values beyond the header under the key None, as a list (D-088: was a 500).
            extra = raw.pop(None, None)
            values = {(k or "").strip().lower(): (v or "").strip() for k, v in raw.items()}
            rows.append(CsvRow(line, values, bool(extra)))
    except csv.Error:
        raise AppError(UNREADABLE, code="INVALID_CSV", status_code=422) from None
    return rows

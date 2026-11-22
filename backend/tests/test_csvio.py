"""CSV in and out (core/csvio.py): text that could run as a formula gets a quote in front, a number
the server worked out stays a number (a negative variance too), and a file the csv module cannot
read is refused in words (422 INVALID_CSV), never a 500.

Requirements: EXP-007, SEC-006, SEC-007, PART-016
"""

from __future__ import annotations

import csv
import io
from decimal import Decimal

import pytest

from app.core import csvio
from app.core.errors import AppError


@pytest.mark.parametrize(
    ("value", "written"),
    [
        ('=HYPERLINK("http://evil.example")', '\'=HYPERLINK("http://evil.example")'),
        ("+91 98200 00000", "'+91 98200 00000"),
        ("-2", "'-2"),  # text, even when it looks like a number
        ("@SUM(A1)", "'@SUM(A1)"),
        ("\tTab", "'\tTab"),
        ("\rReturn", "'\rReturn"),
        ("North Goa", "North Goa"),
        (None, ""),
        ("", ""),
        (-6.0, "-6.0"),
        (-6, "-6"),
        (12.5, "12.5"),
        (0, "0"),
        (Decimal("-0.50"), "-0.50"),
        (True, "True"),
        (False, "False"),
        # Not a number a spreadsheet can show: treated as text.
        (float("-inf"), "'-inf"),
        (float("nan"), "nan"),
        (Decimal("-Infinity"), "'-Infinity"),
    ],
)
def test_a_cell_is_never_a_formula_and_a_number_stays_a_number(value: object, written: str) -> None:
    assert csvio.safe_cell(value) == written


def test_a_table_has_the_bom_a_header_and_safe_cells() -> None:
    text = csvio.write_table(["label", "variance"], [["=1+1", -6.0], ["Male", 4]], bom=True)
    assert text.startswith(csvio.BOM)
    rows = list(csv.reader(io.StringIO(text.removeprefix(csvio.BOM))))
    assert rows == [["label", "variance"], ["'=1+1", "-6.0"], ["Male", "4"]]


def _read(text: str) -> list[csvio.CsvRow]:
    return csvio.read_rows(text, ["name", "email"], required=["name"], max_rows=10, noun="people")


def test_rows_come_back_trimmed_with_their_line() -> None:
    rows = _read(csvio.BOM + "Name, EMAIL\n Asha , asha@example.org \nGita,,extra\n")
    assert [(r.line, r.values, r.extra) for r in rows] == [
        (2, {"name": "Asha", "email": "asha@example.org"}, False),
        (3, {"name": "Gita", "email": ""}, True),
    ]


@pytest.mark.parametrize(
    "text",
    [
        # A value over the csv module's limit (131 072 characters).
        "name,email\n" + "a" * 140_000 + ",a@example.org\n",
        # A quote never closed: everything after it becomes one value, over the limit.
        'name,email\n"Asha,asha@example.org\n' + "Gita,gita@example.org\n" * 8_000,
        # The same in the header line.
        '"' + "name," * 30_000 + "\n",
    ],
    ids=["long value", "quote not closed", "header"],
)
def test_a_file_the_csv_module_cannot_read_is_refused_in_words(text: str) -> None:
    with pytest.raises(AppError) as info:
        _read(text)
    assert (info.value.code, info.value.status_code) == ("INVALID_CSV", 422)
    assert info.value.message == (
        "The file could not be read: a value is too long or a quote is not closed"
    )


def test_too_many_rows_and_a_wrong_header_are_still_their_own_errors() -> None:
    with pytest.raises(AppError) as info:
        _read("name,email\n" + "Asha,a@example.org\n" * 11)
    assert info.value.code == "TOO_MANY_ROWS"
    with pytest.raises(AppError) as info:
        _read("who,email\nAsha,a@example.org\n")
    assert info.value.code == "INVALID_CSV"

"""The Excel writer (core/xlsx.py): a valid workbook, one sheet per table, numbers as numbers and
text that can never run as a formula (the Progress tab's download, owner's request).

Requirements: EXP-002, EXP-007, SEC-006, SEC-007
"""

from __future__ import annotations

import io
import zipfile
from decimal import Decimal
from xml.etree import ElementTree

import pytest

from app.core import xlsx

NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
REL = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"


def _open(data: bytes) -> zipfile.ZipFile:
    archive = zipfile.ZipFile(io.BytesIO(data))
    assert archive.testzip() is None
    return archive


def _xml(archive: zipfile.ZipFile, name: str) -> ElementTree.Element:
    return ElementTree.fromstring(archive.read(name))  # noqa: S314 - our own file


def _sheet(archive: zipfile.ZipFile, number: int) -> list[list[object]]:
    """A sheet's rows as values: inline text as str, numbers as float, booleans as bool."""
    rows = []
    for row in _xml(archive, f"xl/worksheets/sheet{number}.xml").iterfind(".//m:row", NS):
        values: list[object] = []
        for cell in row.iterfind("m:c", NS):
            assert cell.find("m:f", NS) is None, "never a formula"
            kind = cell.get("t")
            if kind == "inlineStr":
                values.append("".join(t.text or "" for t in cell.iterfind(".//m:t", NS)))
            elif kind == "b":
                values.append(cell.findtext("m:v", namespaces=NS) == "1")
            else:
                assert kind is None, kind
                values.append(float(cell.findtext("m:v", namespaces=NS) or "nan"))
        rows.append(values)
    return rows


def test_a_workbook_has_the_parts_excel_needs_and_one_sheet_per_table() -> None:
    data = xlsx.write_workbook(
        [
            ("Key figures", ["Figure", "Value"], [["Approved conversations", 3]]),
            ("Balance", ["Row", "Variance (points)"], [["Male", -6.0], ["Female", 6]]),
        ]
    )
    archive = _open(data)
    assert archive.namelist()[0] == "[Content_Types].xml"
    assert set(archive.namelist()) == {
        "[Content_Types].xml",
        "_rels/.rels",
        "xl/workbook.xml",
        "xl/_rels/workbook.xml.rels",
        "xl/styles.xml",
        "xl/worksheets/sheet1.xml",
        "xl/worksheets/sheet2.xml",
    }
    for name in archive.namelist():
        _xml(archive, name)  # every part is well-formed XML
    workbook = _xml(archive, "xl/workbook.xml")
    sheets = workbook.findall(".//m:sheet", NS)
    assert [(s.get("name"), s.get("sheetId"), s.get(REL)) for s in sheets] == [
        ("Key figures", "1", "rId1"),
        ("Balance", "2", "rId2"),
    ]
    types = archive.read("[Content_Types].xml").decode()
    assert types.count("worksheet+xml") == 2
    assert "styles+xml" in types
    assert _sheet(archive, 1) == [["Figure", "Value"], ["Approved conversations", 3.0]]
    assert _sheet(archive, 2) == [["Row", "Variance (points)"], ["Male", -6.0], ["Female", 6.0]]
    # The heading row is styled (bold), frozen above the rows that scroll.
    first = _xml(archive, "xl/worksheets/sheet1.xml")
    heading = first.find(".//m:row", NS)
    pane = first.find(".//m:pane", NS)
    assert heading is not None
    assert pane is not None
    assert {c.get("s") for c in heading.iterfind("m:c", NS)} == {"1"}
    assert pane.get("state") == "frozen"
    assert xlsx.write_workbook([("A", ["x"], [[1]])]) == xlsx.write_workbook(
        [("A", ["x"], [[1]])]
    ), "the same content gives the same bytes"


def test_text_never_runs_as_a_formula_and_numbers_stay_numbers() -> None:
    """A district typed by a participant (free text) reaches the file as plain text."""
    nasty = '=HYPERLINK("http://evil.example","Click")'
    data = xlsx.write_workbook(
        [
            (
                "Districts",
                ["District", "Count", "Share", "Exact", "Flag", "Nothing"],
                [
                    [nasty, 2, 40.0, Decimal("12.50"), True, None],
                    ["+1 & <b>", -3, -0.5, Decimal("-6.0"), False, ""],
                    ["@SUM(A1)", float("nan"), float("inf"), Decimal("NaN"), 0, "  spaced  "],
                ],
            )
        ]
    )
    archive = _open(data)
    raw = archive.read("xl/worksheets/sheet1.xml").decode()
    assert "<f>" not in raw
    assert "&lt;b&gt;" in raw
    assert "&amp;" in raw
    rows = _sheet(archive, 1)
    assert rows[1] == [nasty, 2.0, 40.0, 12.5, True]  # None: no cell at all
    assert rows[2] == ["+1 & <b>", -3.0, -0.5, -6.0, False, ""]
    # Not a number a cell can hold: written as its text, never as a broken number.
    assert rows[3] == ["@SUM(A1)", "nan", "inf", "NaN", 0.0, "  spaced  "]


def test_characters_xml_refuses_are_dropped_and_long_text_is_cut() -> None:
    text = "North\x00 Goa\x0b" + chr(0xD800) + chr(0xFFFE) + "\tok\n" + chr(0x2028)
    data = xlsx.write_workbook([("S", ["Text"], [[text], ["x" * 40_000]])])
    rows = _sheet(_open(data), 1)
    assert rows[1] == ["North Goa\tok\n" + chr(0x2028)]
    assert len(str(rows[2][0])) == xlsx.MAX_CELL_TEXT


def test_sheet_names_excel_accepts() -> None:
    names = xlsx.sheet_names(
        [
            "Speakers by age and gender",
            "speakers BY age and gender",
            "a[b]:c*d?e/f\\g",
            "'Quoted'",
            "History",
            "",
            "A name much longer than thirty-one characters",
            "A name much longer than thirty-one characters",
        ]
    )
    assert names == [
        "Speakers by age and gender",
        "speakers BY age and gender (2)",
        "a b c d e f g",
        "Quoted",
        "History 5",
        "Sheet 6",
        "A name much longer than thirty-",
        "A name much longer than thi (2)",
    ]
    assert all(len(n) <= xlsx.MAX_SHEET_NAME for n in names)
    workbook = _xml(
        _open(xlsx.write_workbook([('Tom & "Jerry" <x>', ["A"], [])])), "xl/workbook.xml"
    )
    sheet = workbook.find(".//m:sheet", NS)
    assert sheet is not None
    assert sheet.get("name") == 'Tom & "Jerry" <x>'


def test_columns_are_lettered_like_excel_and_a_workbook_needs_a_sheet() -> None:
    assert [xlsx.column_letter(i) for i in (0, 25, 26, 51, 52, 701, 702)] == [
        "A",
        "Z",
        "AA",
        "AZ",
        "BA",
        "ZZ",
        "AAA",
    ]
    with pytest.raises(ValueError, match="at least one sheet"):
        xlsx.write_workbook([])

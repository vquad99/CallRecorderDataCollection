"""Excel workbooks (.xlsx) for people to open: one sheet per table, without a library.

An .xlsx file is a ZIP of XML parts (Office Open XML, ECMA-376). This writes the few parts Excel,
LibreOffice and Google Sheets need: the content types, the package and workbook relationships,
the workbook, a small style sheet (a bold, shaded heading row) and one worksheet per table.

Safe by construction (D-088's rule for tables, as core/csvio.py keeps it for CSV):
- text is written as an inline string (`t="inlineStr"`), never as a formula, so a value such as
  `=HYPERLINK(...)` typed into a free-text field shows as that text and never runs;
- numbers are written as numbers, so a variance of -6.0 stays a number;
- characters XML 1.0 does not allow (control characters, lone surrogates) are dropped and the
  rest escaped; text longer than a cell holds (32 767 characters) is cut;
- sheet names lose the characters Excel refuses (`[]:*?/\\`), keep at most 31 characters and are
  made unique.

The same content always gives the same bytes (fixed ZIP times), so a file can be compared.
"""

from __future__ import annotations

import io
import math
import re
import zipfile
from collections.abc import Sequence
from decimal import Decimal
from xml.sax.saxutils import escape

Cell = str | int | float | Decimal | bool | None
# A sheet: its name, the heading row, then the rows.
Sheet = tuple[str, Sequence[str], Sequence[Sequence[Cell]]]

MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
MAX_SHEET_NAME = 31
MAX_CELL_TEXT = 32_767
_MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_DOC_RELS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_PKG_RELS = "http://schemas.openxmlformats.org/package/2006/relationships"
_TYPES = "http://schemas.openxmlformats.org/package/2006/content-types"
_HEAD = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
# Characters XML 1.0 does not allow (control characters, lone surrogates), and the two
# non-characters it allows but no file should carry.
_NOT_XML = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\U0000d800-\U0000dfff\U0000fffe\U0000ffff]")
_NOT_IN_SHEET_NAME = re.compile(r"[\[\]:*?/\\]")
_ZIP_TIME = (1980, 1, 1, 0, 0, 0)
_HEADING_STYLE = 1  # cellXfs index of the heading row: bold, shaded, a line under it


def clean_text(value: str) -> str:
    """Text as a cell may hold it: no character XML 1.0 refuses, at most 32 767 characters."""
    return _NOT_XML.sub("", value)[:MAX_CELL_TEXT]


def sheet_names(titles: Sequence[str]) -> list[str]:
    """Names Excel accepts: none of []:*?/\\, at most 31 characters, not starting or ending with
    an apostrophe, not "History" (Excel keeps that name), each different (capitals aside)."""
    names: list[str] = []
    seen: set[str] = set()
    for number, title in enumerate(titles, start=1):
        base = " ".join(_NOT_IN_SHEET_NAME.sub(" ", clean_text(title)).split())
        base = base[:MAX_SHEET_NAME].strip().strip("'").strip() or f"Sheet {number}"
        if base.casefold() == "history":
            base = f"{base} {number}"
        name, again = base, 2
        while name.casefold() in seen:
            suffix = f" ({again})"
            name = base[: MAX_SHEET_NAME - len(suffix)].rstrip() + suffix
            again += 1
        seen.add(name.casefold())
        names.append(name)
    return names


def column_letter(index: int) -> str:
    """The letters of a column, counted from 0: A, ..., Z, AA, AB, ..."""
    letters = ""
    index += 1
    while index:
        index, rest = divmod(index - 1, 26)
        letters = chr(ord("A") + rest) + letters
    return letters


def _attribute(text: str) -> str:
    return escape(text, {'"': "&quot;"})


def _number(value: int | float | Decimal) -> str | None:
    """A number as the file writes it; None for one a cell cannot hold (not a number, infinite)."""
    if isinstance(value, Decimal):
        return format(value, "f") if value.is_finite() else None
    if isinstance(value, float):
        return repr(value) if math.isfinite(value) else None
    return str(value)


def _cell(ref: str, value: Cell, style: int = 0) -> str:
    if value is None:
        return ""
    styled = f' s="{style}"' if style else ""
    if isinstance(value, bool):
        return f'<c r="{ref}" t="b"{styled}><v>{int(value)}</v></c>'
    if isinstance(value, int | float | Decimal):
        number = _number(value)
        if number is not None:
            return f'<c r="{ref}"{styled}><v>{number}</v></c>'
    text = escape(clean_text(str(value)))
    return f'<c r="{ref}" t="inlineStr"{styled}><is><t xml:space="preserve">{text}</t></is></c>'


def _shown(value: Cell) -> int:
    """About how many characters a cell shows, for the column's width."""
    if value is None:
        return 0
    if isinstance(value, float):
        return len(f"{value:g}")
    return max((len(line) for line in str(value).splitlines()), default=0)


def _width(index: int, header: Sequence[str], rows: Sequence[Sequence[Cell]]) -> int:
    """A column as wide as its longest value (the bold heading a little wider), 8 to 60."""
    longest = max(
        [len(header[index]) + 2 if index < len(header) else 0]
        + [_shown(r[index]) for r in rows if index < len(r)]
    )
    return min(60, max(8, longest + 2))


def _row(number: int, values: Sequence[Cell], style: int = 0) -> str:
    cells = "".join(
        _cell(f"{column_letter(i)}{number}", value, style) for i, value in enumerate(values)
    )
    return f'<row r="{number}">{cells}</row>'


def _worksheet(header: Sequence[str], rows: Sequence[Sequence[Cell]], first: bool) -> str:
    """A sheet: the heading row (bold, shaded, kept in view while the rows scroll), then the rows,
    each column as wide as its values."""
    lines = [_row(1, header, _HEADING_STYLE)]
    lines += [_row(number, row) for number, row in enumerate(rows, start=2)]
    width = max([len(header), *(len(r) for r in rows)])
    cols = "".join(
        f'<col min="{i + 1}" max="{i + 1}" width="{_width(i, header, rows)}" customWidth="1"/>'
        for i in range(width)
    )
    selected = ' tabSelected="1"' if first else ""
    return (
        f'{_HEAD}<worksheet xmlns="{_MAIN}" xmlns:r="{_DOC_RELS}">'
        f'<sheetViews><sheetView workbookViewId="0"{selected}>'
        '<pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/>'
        '<selection pane="bottomLeft" activeCell="A2" sqref="A2"/>'
        "</sheetView></sheetViews>"
        '<sheetFormatPr defaultRowHeight="15"/>'
        + (f"<cols>{cols}</cols>" if cols else "")
        + f"<sheetData>{''.join(lines)}</sheetData></worksheet>"
    )


_STYLES = (
    f'{_HEAD}<styleSheet xmlns="{_MAIN}">'
    '<fonts count="2">'
    '<font><sz val="11"/><name val="Calibri"/><family val="2"/></font>'
    '<font><b/><sz val="11"/><name val="Calibri"/><family val="2"/></font>'
    "</fonts>"
    '<fills count="3">'
    '<fill><patternFill patternType="none"/></fill>'
    '<fill><patternFill patternType="gray125"/></fill>'
    '<fill><patternFill patternType="solid"><fgColor rgb="FFEEF2F7"/><bgColor indexed="64"/>'
    "</patternFill></fill>"
    "</fills>"
    '<borders count="2">'
    "<border><left/><right/><top/><bottom/><diagonal/></border>"
    '<border><left/><right/><top/><bottom style="thin"><color rgb="FFB6C2D2"/></bottom>'
    "<diagonal/></border>"
    "</borders>"
    '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
    '<cellXfs count="2">'
    '<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'
    '<xf numFmtId="0" fontId="1" fillId="2" borderId="1" xfId="0" applyFont="1" applyFill="1"'
    ' applyBorder="1"/>'
    "</cellXfs>"
    '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>'
    "</styleSheet>"
)


def write_workbook(sheets: Sequence[Sheet]) -> bytes:
    """The tables as an .xlsx file: one sheet each, its heading row bold and kept in view."""
    if not sheets:
        raise ValueError("a workbook needs at least one sheet")
    names = sheet_names([name for name, _, _ in sheets])
    count = len(sheets)
    parts: list[tuple[str, str]] = [
        (
            "[Content_Types].xml",
            f'{_HEAD}<Types xmlns="{_TYPES}">'
            '<Default Extension="rels" '
            'ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/xl/workbook.xml" ContentType="application/'
            'vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
            '<Override PartName="/xl/styles.xml" ContentType="application/'
            'vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
            + "".join(
                f'<Override PartName="/xl/worksheets/sheet{n}.xml" ContentType="application/'
                'vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
                for n in range(1, count + 1)
            )
            + "</Types>",
        ),
        (
            "_rels/.rels",
            f'{_HEAD}<Relationships xmlns="{_PKG_RELS}">'
            f'<Relationship Id="rId1" Type="{_DOC_RELS}/officeDocument" '
            'Target="xl/workbook.xml"/></Relationships>',
        ),
        (
            "xl/workbook.xml",
            f'{_HEAD}<workbook xmlns="{_MAIN}" xmlns:r="{_DOC_RELS}">'
            '<bookViews><workbookView activeTab="0"/></bookViews><sheets>'
            + "".join(
                f'<sheet name="{_attribute(name)}" sheetId="{n}" r:id="rId{n}"/>'
                for n, name in enumerate(names, start=1)
            )
            + "</sheets></workbook>",
        ),
        (
            "xl/_rels/workbook.xml.rels",
            f'{_HEAD}<Relationships xmlns="{_PKG_RELS}">'
            + "".join(
                f'<Relationship Id="rId{n}" Type="{_DOC_RELS}/worksheet" '
                f'Target="worksheets/sheet{n}.xml"/>'
                for n in range(1, count + 1)
            )
            + f'<Relationship Id="rId{count + 1}" Type="{_DOC_RELS}/styles" '
            'Target="styles.xml"/></Relationships>',
        ),
        ("xl/styles.xml", _STYLES),
    ]
    parts += [
        (f"xl/worksheets/sheet{n}.xml", _worksheet(header, rows, first=n == 1))
        for n, (_, header, rows) in enumerate(sheets, start=1)
    ]
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, xml in parts:
            info = zipfile.ZipInfo(name, date_time=_ZIP_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, xml.encode("utf-8"))
    return out.getvalue()

"""Master requirements checklist, generated from docs/BUILD_STATUS.md (the single source).

Writes docs/REQUIREMENTS_CHECKLIST.md: every requirement with a plain state - Verified, Built
(automated tests pass), Partly built / needs testing, Not built, Blocked, Withdrawn, Needs fixing,
or Process rule (GEN / PROC: how the work is done, not a feature). With --check it fails when the
file is out of date, so the checklist can never drift from the tracker.

  python tools/requirements_checklist.py          # write
  python tools/requirements_checklist.py --check  # verify
"""

from __future__ import annotations

import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "docs" / "BUILD_STATUS.md"
TARGET = ROOT / "docs" / "REQUIREMENTS_CHECKLIST.md"

STATES = {
    "VERIFIED": "Verified",
    "ACCEPTED": "Verified",
    "IMPLEMENTED — AUTOMATED TESTS PASS": "Built",
    "IMPLEMENTED — TESTS FAILING": "Needs fixing",
    "IN PROGRESS": "Partly built / needs testing",
    "NOT STARTED": "Not built",
    "BLOCKED": "Blocked",
    "WITHDRAWN": "Withdrawn",
}
ORDER = [
    "Verified",
    "Built",
    "Partly built / needs testing",
    "Needs fixing",
    "Not built",
    "Blocked",
    "Withdrawn",
    "Process rule",
]
MEANING = {
    "Verified": "built, automated tests pass and checked by hand or accepted at a gate",
    "Built": "built and automated tests pass; not yet checked by hand",
    "Partly built / needs testing": "some of it is built, or it needs a test that is not done yet",
    "Needs fixing": "built but a test fails",
    "Not built": "not started",
    "Blocked": "waiting on a decision or account from the owner or client (see Note)",
    "Withdrawn": "removed by an owner decision (see Note)",
    "Process rule": "how the work is done (GEN, PROC), not a feature of the app",
}


def rows() -> list[tuple[str, str, str, str, str]]:
    text = SOURCE.read_text(encoding="utf-8")
    body = text[text.index("## Requirements") : text.index("## Session log")]
    out = []
    for line in body.splitlines():
        m = re.match(r"\| ([A-Z]+)-(\d{3}) \|", line)
        if not m:
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        rid, desc, phase, status, note = cells[0], cells[1], cells[2], cells[-2], cells[-1]
        state = "Process rule" if m.group(1) in ("GEN", "PROC") else STATES[status]
        out.append((rid, desc, phase, state, "" if note == "-" else note))
    return out


def render() -> str:
    data = rows()
    count = Counter(r[3] for r in data)
    live = len(data) - count["Withdrawn"] - count["Process rule"]
    done = count["Verified"] + count["Built"]
    lines = [
        "# Requirements checklist",
        "",
        "GENERATED from docs/BUILD_STATUS.md by `python tools/requirements_checklist.py`;",
        "do not edit by hand. Change the requirement's row in BUILD_STATUS.md, then regenerate.",
        "",
        f"{len(data)} requirements. Of the {live} that describe the product (not withdrawn, not a",
        f"process rule), {done} are built with passing automated tests"
        f" ({count['Verified']} of them also verified) - {round(100 * done / live)} %.",
        "",
        "| State | Count | Meaning |",
        "|---|---:|---|",
    ]
    lines += [f"| {s} | {count[s]} | {MEANING[s]} |" for s in ORDER]
    modules: dict[str, list[tuple[str, str, str, str, str]]] = {}
    for r in data:
        modules.setdefault(r[0].split("-")[0], []).append(r)
    lines += ["", "## By module", "", "| Module | " + " | ".join(ORDER) + " |"]
    lines.append("|---|" + "---:|" * len(ORDER))
    for mod, items in modules.items():
        c = Counter(i[3] for i in items)
        lines.append(f"| {mod} | " + " | ".join(str(c[s] or "") for s in ORDER) + " |")
    for mod, items in modules.items():
        lines += ["", f"## {mod}", "", "| ID | State | Requirement | Note |", "|---|---|---|---|"]
        for rid, desc, _phase, state, note in items:
            lines.append(f"| {rid} | {state} | {desc} | {note} |")
    return "\n".join(lines) + "\n"


def main() -> int:
    text = render()
    if "--check" in sys.argv:
        if not TARGET.exists() or TARGET.read_text(encoding="utf-8") != text:
            print("REQUIREMENTS_CHECKLIST.md is out of date: run tools/requirements_checklist.py")
            return 1
        print("requirements checklist: up to date")
        return 0
    TARGET.write_text(text, encoding="utf-8")
    print(f"wrote {TARGET.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Repository rules that tests in the app cannot see. Exit 1 on any failure.

  TA-GEN-01  no TODO/FIXME/NotImplemented/test imports in production source
  TA-GEN-03  BUILD_STATUS.md uses only allowed statuses; checked boxes cite existing evidence
  TA-GEN-06  every test file declares the requirement IDs it covers, and they exist
  TA-GEN-07  every Phase 0 document exists
  TA-ARCH-01 lockfiles exist; TECH_STACK.md pinned versions equal the lockfiles and image tags

Standard library only, so it runs before any dependency is installed.
"""

from __future__ import annotations

import json
import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"

ALLOWED_STATUSES = {
    "NOT STARTED",
    "IN PROGRESS",
    "BLOCKED",
    "IMPLEMENTED — TESTS FAILING",
    "IMPLEMENTED — AUTOMATED TESTS PASS",
    "VERIFIED",
    "ACCEPTED",
    "WITHDRAWN",  # removed by an owner decision named in the row (D-062)
}
REQUIRED_DOCS = [
    "REQUIREMENTS.md",
    "REQUIREMENT_TRACEABILITY.md",
    "ARCHITECTURE.md",
    "DATABASE.md",
    "API_CONTRACT.md",
    "SECURITY.md",
    "AUDIO_SPECIFICATION.md",
    "TELEPHONY_PROVIDER_EVALUATION.md",
    "TEST_PLAN.md",
    "BUILD_STATUS.md",
    "DECISIONS.md",
    "TECH_STACK.md",
    "DEPLOYMENT.md",
    "integrations",
    "evidence",
]
FORBIDDEN_IN_PRODUCTION = [
    (re.compile(r"\b(TODO|FIXME|XXX)\b"), "unfinished-work marker"),
    (re.compile(r"NotImplementedError|NotImplemented\b"), "NotImplemented"),
    (re.compile(r"^\s*(from|import)\s+tests\b", re.M), "test import in production code"),
    (re.compile(r"from\s+[\"'](vitest|@testing-library/[^\"']+|@playwright/test)[\"']"), "test library import"),
]
REQ_LINE = re.compile(r"Requirements:\s*([A-Z]+-\d{3}(?:\s*,\s*[A-Z]+-\d{3})*)")


def _rel(path: Path) -> str:
    return str(path.relative_to(ROOT))


def check_docs() -> list[str]:
    return [f"TA-GEN-07: missing docs/{name}" for name in REQUIRED_DOCS if not (DOCS / name).exists()]


def production_files() -> list[Path]:
    files = sorted((ROOT / "backend/app").rglob("*.py"))
    for path in sorted((ROOT / "frontend/src").rglob("*")):
        if path.suffix in {".ts", ".tsx"} and ".test." not in path.name and "/src/test/" not in str(path):
            files.append(path)
    return files


def check_placeholders() -> list[str]:
    problems = []
    for path in production_files():
        text = path.read_text(encoding="utf-8")
        for pattern, label in FORBIDDEN_IN_PRODUCTION:
            match = pattern.search(text)
            if match:
                line = text.count("\n", 0, match.start()) + 1
                problems.append(f"TA-GEN-01: {_rel(path)}:{line}: {label}")
    return problems


def requirement_ids() -> set[str]:
    text = (DOCS / "REQUIREMENTS.md").read_text(encoding="utf-8")
    return set(re.findall(r"^\| ([A-Z]+-\d{3}) \|", text, re.M))


def test_files() -> list[Path]:
    files = sorted((ROOT / "backend/tests").glob("test_*.py"))
    files += sorted(p for p in (ROOT / "frontend/src").rglob("*.test.ts*"))
    files += sorted((ROOT / "frontend/e2e").glob("*.spec.ts"))
    return files


def check_test_requirement_ids() -> list[str]:
    known = requirement_ids()
    problems = []
    for path in test_files():
        match = REQ_LINE.search(path.read_text(encoding="utf-8"))
        if not match:
            problems.append(f"TA-GEN-06: {_rel(path)} declares no 'Requirements:' line")
            continue
        for rid in re.split(r"\s*,\s*", match.group(1)):
            if rid not in known:
                problems.append(f"TA-GEN-06: {_rel(path)} cites unknown requirement {rid}")
    return problems


def _table_rows(text: str, header_start: str) -> tuple[list[str], list[list[str]]]:
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if line.startswith(header_start):
            header = [c.strip() for c in line.strip().strip("|").split("|")]
            rows = []
            for row in lines[i + 2 :]:
                if not row.startswith("|"):
                    break
                rows.append([c.strip() for c in row.strip().strip("|").split("|")])
            return header, rows
    return [], []


def check_build_status() -> list[str]:
    text = (DOCS / "BUILD_STATUS.md").read_text(encoding="utf-8")
    problems = []
    for start in ("| Module |", "| Requirement ID |", "| Phase |"):
        header, rows = _table_rows(text, start)
        if not header:
            problems.append(f"TA-GEN-03: BUILD_STATUS.md has no table starting '{start}'")
            continue
        status_col = header.index("Status")
        evidence_col = header.index("Evidence path") if "Evidence path" in header else None
        for row in rows:
            if row[0].startswith("**"):
                continue
            status = row[status_col]
            if status not in ALLOWED_STATUSES:
                problems.append(f"TA-GEN-03: '{row[0]}' has status '{status}'")
            if evidence_col is not None and any("[x]" in cell for cell in row):
                paths = re.findall(r"(?:docs|backend|frontend|tools|infra)/[^\s,;]+", row[evidence_col])
                if not paths or not all((ROOT / p).exists() for p in paths):
                    problems.append(f"TA-GEN-03: '{row[0]}' has a checked box without existing evidence")
    return problems


def _uv_versions() -> dict[str, str]:
    data = tomllib.loads((ROOT / "backend/uv.lock").read_text(encoding="utf-8"))
    return {pkg["name"]: pkg["version"] for pkg in data.get("package", []) if "version" in pkg}


def _npm_versions() -> dict[str, str]:
    data = json.loads((ROOT / "frontend/package-lock.json").read_text(encoding="utf-8"))
    out = {}
    for key, meta in data.get("packages", {}).items():
        if key.startswith("node_modules/") and key.count("node_modules/") == 1 and "version" in meta:
            out[key.removeprefix("node_modules/")] = meta["version"]
    return out


def check_pins() -> list[str]:
    problems = []
    for lock in ("backend/uv.lock", "frontend/package-lock.json"):
        if not (ROOT / lock).exists():
            problems.append(f"TA-ARCH-01: missing {lock}")
    if problems:
        return problems
    header, rows = _table_rows((DOCS / "TECH_STACK.md").read_text(encoding="utf-8"), "| Component | Package |")
    if not rows:
        return ["TA-ARCH-01: TECH_STACK.md has no pinned-versions table"]
    sources = {"uv.lock": _uv_versions(), "package-lock.json": _npm_versions()}
    for row in rows:
        _, package, version, source = row[:4]
        if source in sources:
            actual = sources[source].get(package)
            if actual != version:
                problems.append(f"TA-ARCH-01: {package} is {actual} in {source}, TECH_STACK.md says {version}")
        else:
            target = ROOT / source
            if not target.exists() or f"{package}:{version}" not in target.read_text(encoding="utf-8"):
                problems.append(f"TA-ARCH-01: {package}:{version} not found in {source}")
    return problems


def main() -> int:
    checks = [check_docs, check_placeholders, check_test_requirement_ids, check_build_status, check_pins]
    problems = [p for check in checks for p in check()]
    for problem in problems:
        print(problem)
    print(f"check_repo: {len(problems)} problem(s) in {len(checks)} checks")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())

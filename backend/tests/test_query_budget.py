"""Query budgets (owner's list, O5): a list page costs the same number of database queries for
2 rows as for 10, so pages stay fast as projects grow. Measured from the request log (O8).

Requirements: FND-008, LOAD-005
"""

from __future__ import annotations

import logging
from typing import Any

import pytest

from tests.conftest import Api, make_participant, make_project, make_user

pytestmark = pytest.mark.db


def _logged(caplog: pytest.LogCaptureFixture, path: str) -> int:
    """Database queries of the last request to `path`, from the request log."""
    line = [
        r
        for r in caplog.records
        if r.getMessage() == "request" and r.__dict__.get("path") == path.split("?")[0]
    ]
    return int(line[-1].__dict__["db_queries"])


def _queries(api: Api, path: str, caplog: pytest.LogCaptureFixture) -> int:
    caplog.clear()
    response = api.get(path)
    assert response.status_code == 200, (path, response.text[:200])
    return _logged(caplog, path)


def _estate(db: Any, new_api: Any, size: int, tag: str) -> dict[str, Any]:
    project = make_project(db, f"QB{tag.upper()}")
    make_user(db, f"sa.{tag}@example.org", ["SUPER_ADMIN"])
    mod = make_user(db, f"mod.{tag}@example.org", ["MODERATOR"], projects=[project])
    for i in range(size):
        make_user(db, f"u{i}.{tag}@example.org", ["MODERATOR", "QC_EXECUTIVE"], projects=[project])
    sa: Api = new_api()
    sa.login(f"sa.{tag}@example.org")
    people = [make_participant(sa, project.id, f"P{i} {tag}") for i in range(size + 1)]
    task_ids = []
    for i in range(size):
        task = sa.post(
            "/api/v1/tasks",
            json={
                "project_id": str(project.id),
                "recording_mode": "FACE_TO_FACE",
                "participant_a_id": people[i]["id"],
                "participant_b_id": people[i + 1]["id"],
            },
        ).json()
        sa.post(f"/api/v1/tasks/{task['id']}/assign", json={"user_id": str(mod.id)})
        task_ids.append(task["id"])
    for i in range(size):
        sa.post(f"/api/v1/tasks/{task_ids[0]}/comments", json={"body": f"note {i}"})
    moderator: Api = new_api()
    moderator.login(f"mod.{tag}@example.org")
    return {"sa": sa, "mod": moderator, "project": str(project.id), "task": task_ids[0]}


# Highest count after the O5 work is 8 (sign-in check 4, page 4); a page passing this has
# gained a query that needs a reason.
MAX_QUERIES = 10
# Pages allowed more, each with its reason (still flat: the same count for 2 rows as for 10).
ALLOWED = {
    # D-095: the minutes columns (recorded, approved, payable) are one query for the whole page,
    # sent only to people who may export the project; D-143: who each one is paired with, one
    # query for the whole page, sent only to people who make tasks; D-144: which documents each
    # one has uploaded, one query for the whole page.
    ("sa", "/api/v1/projects/{project}/participants?page_size=100"): MAX_QUERIES + 3,
}

PAGES = [
    ("sa", "/api/v1/users?page_size=100"),
    ("sa", "/api/v1/users/export"),
    ("sa", "/api/v1/projects"),
    ("sa", "/api/v1/projects/{project}/members"),
    ("sa", "/api/v1/projects/{project}/member-candidates"),
    ("sa", "/api/v1/projects/{project}/participants?page_size=100"),
    ("sa", "/api/v1/projects/{project}/participants/export"),
    # D-148: the Progress tab, a few set-based queries over the project's tasks.
    ("sa", "/api/v1/projects/{project}/progress"),
    ("sa", "/api/v1/tasks?page_size=100"),
    ("mod", "/api/v1/tasks?page_size=100"),
    ("sa", "/api/v1/tasks/{task}/timeline"),
    ("sa", "/api/v1/audit-logs?page_size=200"),
]


def test_list_pages_cost_the_same_for_2_and_10_rows(
    db: Any, new_api: Any, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO)
    small, large = _estate(db, new_api, 2, "s"), _estate(db, new_api, 10, "l")
    grows = []
    for who, template in PAGES:
        counts = [
            _queries(e[who], template.format(project=e["project"], task=e["task"]), caplog)
            for e in (small, large)
        ]
        print(f"QUERIES {who} {template}: {counts}")  # shown with -s, kept for the evidence file
        limit = ALLOWED.get((who, template), MAX_QUERIES)
        if counts[1] > counts[0] or counts[1] > limit:
            grows.append(
                f"{who} {template}: {counts[0]} queries for 2 rows, {counts[1]} for 10 "
                f"(limit {limit})"
            )
    assert not grows, "\n".join(grows)


def test_emailing_the_consent_form_again_costs_the_same_for_2_and_10_people(
    db: Any, new_api: Any, caplog: pytest.LogCaptureFixture
) -> None:
    """D-139: everyone chosen is read at once, not one by one."""
    caplog.set_level(logging.INFO)
    counts = []
    for size, tag in ((2, "s"), (10, "l")):
        project = make_project(db, f"AGAIN{tag.upper()}")
        make_user(db, f"pa.{tag}@example.org", ["PROJECT_ADMIN"], projects=[project])
        pa: Api = new_api()
        pa.login(f"pa.{tag}@example.org")
        ids = [make_participant(pa, project.id, f"P{i} {tag}")["id"] for i in range(size)]
        path = f"/api/v1/projects/{project.id}/participants/bulk"
        caplog.clear()
        answer = pa.post(path, json={"action": "send_consent", "participant_ids": ids})
        assert answer.status_code == 200, answer.text
        assert {r["message"] for r in answer.json()["results"]} == {"Already agreed: no form sent"}
        counts.append(_logged(caplog, path))
    assert counts[0] == counts[1], f"{counts[0]} queries for 2 people, {counts[1]} for 10"

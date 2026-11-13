"""List endpoints stay bounded (owner's list, O7): every endpoint that returns a list either pages
it (page_size at most 200) or is on the short list below with the reason it cannot grow, and the
task list can be searched by code.

Requirements: FND-016, TASK-010, LOAD-005
"""

from __future__ import annotations

import typing
from typing import Any

import pytest

from tests.conftest import Api, make_participant, make_project, make_user
from tests.test_permissions import _route_contexts

# Lists that are small by nature, with the reason. A new list endpoint fails this file until it
# pages its results or earns a line here.
NATURALLY_BOUNDED = {
    "/api/v1/auth/sessions": "the caller's own unexpired sessions",
    "/api/v1/roles": "the five fixed roles",
    "/api/v1/settings": "the fixed set of capacity settings",
    "/api/v1/projects/{project_id}/members": "a project's staff (capacity: 50 accounts)",
    "/api/v1/projects/{project_id}/member-candidates": "capped at 20 by the service",
    "/api/v1/projects/{project_id}/participants/link-candidates": "capped at 50 by the service",
    "/api/v1/projects/{project_id}/participants/{participant_id}/consent": "one person's consent history",
    "/api/v1/tasks/{task_id}/timeline": "one task's history",
    "/api/v1/tasks/{task_id}/recordings": "one task's recordings",
    "/api/v1/tasks/{task_id}/calls": "one task's phone calls",
    "/api/v1/storage/usage": "one row per project and file kind",
}


def _list_routes() -> list[Any]:
    return [
        c
        for c in _route_contexts()
        if "GET" in c.methods
        and typing.get_origin(getattr(c.route, "response_model", None)) is list
    ]


def test_every_list_endpoint_is_paged_or_naturally_bounded() -> None:
    unexplained = sorted(c.path for c in _list_routes() if c.path not in NATURALLY_BOUNDED)
    stale = sorted(set(NATURALLY_BOUNDED) - {c.path for c in _list_routes()})
    assert not unexplained, f"list endpoints with no page size and no reason: {unexplained}"
    assert not stale, f"reasons for endpoints that no longer return lists: {stale}"


def test_every_paged_endpoint_caps_its_page_size() -> None:
    problems = []
    for c in _route_contexts():
        for param in c.route.dependant.query_params:
            if param.name != "page_size":
                continue
            caps = [m.le for m in param.field_info.metadata if getattr(m, "le", None) is not None]
            if not caps or caps[0] > 200:
                problems.append(f"{c.path}: page_size cap {caps}")
    assert not problems, problems


@pytest.mark.db
def test_tasks_can_be_found_by_task_or_participant_code(db: Any, new_api: Any) -> None:
    project = make_project(db, "SEARCH")
    make_user(db, "find@example.org", ["SUPER_ADMIN"])
    api: Api = new_api()
    api.login("find@example.org")
    people = [make_participant(api, project.id, n) for n in ("Asha", "Bina", "Chandra")]
    tasks = []
    for a, b in ((0, 1), (1, 2)):
        tasks.append(
            api.post(
                "/api/v1/tasks",
                json={
                    "project_id": str(project.id),
                    "recording_mode": "FACE_TO_FACE",
                    "participant_a_id": people[a]["id"],
                    "participant_b_id": people[b]["id"],
                },
            ).json()
        )

    def codes(term: str) -> list[str]:
        page = api.get("/api/v1/tasks", params={"search": term}).json()
        return sorted(t["task_code"] for t in page["items"])

    assert codes(tasks[0]["task_code"].lower()) == [tasks[0]["task_code"]]
    assert codes(people[0]["participant_code"]) == [tasks[0]["task_code"]]
    assert codes(people[1]["participant_code"]) == sorted(t["task_code"] for t in tasks)
    assert codes("Asha") == [], "names are not searchable here, only codes"
    assert codes("%") == [], "wildcards are matched literally"
    assert codes("_") == []

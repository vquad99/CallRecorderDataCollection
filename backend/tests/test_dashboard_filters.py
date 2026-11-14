"""Dashboard filters, and every figure checked against SQL written on its own (owner 2026-11-14,
D-108): mode, language, dialect, status, staff, chosen days; days counted in India time.

Requirements: DASH-001, DASH-002, DASH-003, DASH-004, DASH-006
"""

from __future__ import annotations

from datetime import UTC, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import text

from tests import test_audio_qc, test_export_jobs, test_telephony
from tests.conftest import Api, make_user, set_status

pytestmark = pytest.mark.db

audio = test_telephony.audio
world = test_telephony.world
w = test_export_jobs.w

IST = ZoneInfo("Asia/Kolkata")
FINAL = "('FTF_DERIVED_PCM', 'TELEPHONY_DERIVED_PCM', 'TELEPHONY_FINAL_STEREO')"
HOUR = 3_600_000


@pytest.fixture
def board(w: dict[str, Any]) -> dict[str, Any]:
    """Three recordings with known lengths at known moments:

    - the phone call (Hindi, moderator "mod"): 2 hours, started 23:55 India time on day A;
    - a face-to-face one (Hindi, "mod"): 1.5 hours, started 00:05 on day A+1 - ten minutes
      later, but the next day in India (and the same day in UTC);
    - a face-to-face one (Tamil, dialect Madurai, "mod2"), approved: 0.5 hours, on day A+2.
    """
    db, pa, pid = w["db"], w["pa"], w["project_id"]
    people = [
        pa.post(
            f"/api/v1/projects/{pid}/participants",
            json={"display_label": name, "language_code": "ta", "dialect": dialect},
        ).json()
        for name, dialect in (("Chitra", "Madurai"), ("Devi", ""))
    ]
    made = pa.post(
        "/api/v1/tasks",
        json={
            "project_id": pid,
            "recording_mode": "FACE_TO_FACE",
            "participant_a_id": people[0]["id"],
            "participant_b_id": people[1]["id"],
        },
    )
    assert made.status_code == 201, made.text
    tamil = made.json()["id"]
    assert (
        pa.post(f"/api/v1/tasks/{tamil}/assign", json={"user_id": w["mod2_id"]}).status_code == 200
    )
    mod2: Api = w["api"]("mod2@example.org")
    assert (
        mod2.post(f"/api/v1/tasks/{tamil}/transition", json={"to": "IN_PROGRESS"}).status_code
        == 200
    )
    test_audio_qc._record({**w, "mod": mod2}, 3, tamil, send=False)
    set_status(db, tamil, "APPROVED")

    day_a = datetime.now(UTC).astimezone(IST).date() - timedelta(days=3)
    moments = {
        w["phone_task"]: (datetime.combine(day_a, time(23, 55), IST), 2 * HOUR),
        w["ftf_task"]: (
            datetime.combine(day_a + timedelta(days=1), time(0, 5), IST),
            HOUR * 3 // 2,
        ),
        tamil: (datetime.combine(day_a + timedelta(days=2), time(11, 30), IST), HOUR // 2),
    }
    for task_id, (started, ms) in moments.items():
        db.execute(
            text("UPDATE recordings SET started_at = :at WHERE task_id = :t"),
            {"at": started, "t": task_id},
        )
        db.execute(
            text(
                f"UPDATE audio_assets SET duration_ms = :ms WHERE kind IN {FINAL} AND"  # noqa: S608 - fixed text, no input
                " recording_id IN (SELECT id FROM recordings WHERE task_id = :t)"
            ),
            {"ms": ms, "t": task_id},
        )
    project = db.execute(text("SELECT id FROM projects WHERE id = :p"), {"p": pid}).scalar_one()
    db.execute(
        text(
            "UPDATE projects SET target_face_to_face_hours_per_day = 4,"
            " target_telephony_hours_per_day = 6 WHERE id = :p"
        ),
        {"p": project},
    )
    db.commit()
    return {**w, "tamil_task": tamil, "day_a": day_a, "mod2": mod2}


def get(b: dict[str, Any], who: str = "pa", **params: Any) -> Any:
    answer = b[who].get("/api/v1/dashboard", params={"project_id": b["project_id"], **params})
    return answer.json() if answer.status_code == 200 else answer.status_code


def hours(ms: Any) -> float:
    return round(float(ms or 0) / HOUR, 2)


def test_every_figure_matches_sql_written_on_its_own(board: dict[str, Any]) -> None:
    b, db, pid = board, board["db"], board["project_id"]
    body = get(b, days=7)
    final = (
        f"(SELECT recording_id, max(duration_ms) AS ms FROM audio_assets WHERE kind IN {FINAL}"  # noqa: S608 - fixed text, no input
        " GROUP BY recording_id) f"
    )
    ready = (
        f"FROM recordings r JOIN tasks t ON t.id = r.task_id JOIN {final} ON f.recording_id = r.id"
        " WHERE r.state = 'READY' AND t.project_id = :p"
    )

    # Hours and recordings by mode, and what of it is approved.
    by_mode = {
        row.mode: row
        for row in db.execute(
            text(
                "SELECT r.mode, sum(f.ms) AS ms, count(*) AS n,"
                " sum(CASE WHEN t.status = 'APPROVED' THEN f.ms ELSE 0 END) AS approved "
                f"{ready} GROUP BY r.mode"
            ),
            {"p": pid},
        )
    }
    assert {
        m["mode"]: (m["recorded_hours"], m["approved_hours"], m["recordings"])
        for m in body["by_mode"]
    } == {mode: (hours(row.ms), hours(row.approved), row.n) for mode, row in by_mode.items()}
    assert (body["recorded_hours"], body["approved_hours"], body["recordings"]) == (4.0, 0.5, 3)
    assert body["target_hours_per_day"] == 10.0

    # Hours per day, the day counted in India: 23:55 and 00:05 are different days there.
    per_day = {
        str(row.d): hours(row.ms)
        for row in db.execute(
            text(
                "SELECT (r.started_at AT TIME ZONE 'Asia/Kolkata')::date AS d, sum(f.ms) AS ms "
                f"{ready} GROUP BY 1"
            ),
            {"p": pid},
        )
    }
    day_a = b["day_a"]
    assert per_day == {
        str(day_a): 2.0,
        str(day_a + timedelta(days=1)): 1.5,
        str(day_a + timedelta(days=2)): 0.5,
    }
    shown = {d["day"]: d["recorded_hours"] for d in body["daily"]}
    assert len(shown) == 7
    assert {day: h for day, h in shown.items() if h} == per_day
    # In UTC the first two would have been one day: the report must not count that way.
    utc_days = db.execute(
        text(f"SELECT count(DISTINCT (r.started_at AT TIME ZONE 'UTC')::date) {ready}"), {"p": pid}
    ).scalar_one()
    assert utc_days == 2

    # Tasks by status.
    statuses = dict(
        db.execute(
            text("SELECT status, count(*) FROM tasks WHERE project_id = :p GROUP BY status"),
            {"p": pid},
        ).all()
    )
    assert body["tasks_by_status"] == statuses
    assert body["tasks_total"] == sum(statuses.values())
    assert body["tasks_approved"] == statuses["APPROVED"] == 1

    # Output per moderator, storage in use, and phone calls.
    team = {
        row.display_name: (row.n, hours(row.ms))
        for row in db.execute(
            text(
                "SELECT u.display_name, count(*) AS n, sum(f.ms) AS ms FROM recordings r"  # noqa: S608 - fixed text, no input
                f" JOIN tasks t ON t.id = r.task_id JOIN {final} ON f.recording_id = r.id"
                " JOIN users u ON u.id = r.created_by"
                " WHERE r.state = 'READY' AND t.project_id = :p GROUP BY u.display_name"
            ),
            {"p": pid},
        )
    }
    assert {m["name"]: (m["recordings"], m["recorded_hours"]) for m in body["team"]} == team
    assert team == {"mod": (2, 3.5), "mod2": (1, 0.5)}
    stored = db.execute(
        text(
            "SELECT sum(size_bytes) FROM audio_assets WHERE project_id = :p AND deleted_at IS NULL"
        ),
        {"p": pid},
    ).scalar_one()
    assert body["storage_bytes"] == stored
    calls = db.execute(
        text(
            "SELECT count(*) AS placed, count(*) FILTER (WHERE state = 'RECORDED') AS recorded"
            " FROM calls WHERE project_id = :p"
        ),
        {"p": pid},
    ).one()
    assert (body["calls"]["placed"], body["calls"]["recorded"]) == (calls.placed, calls.recorded)
    assert body["calls"] == {
        "placed": 1,
        "recorded": 1,
        "could_not_be_placed": 0,
        "needs_a_person": 0,
        "open": 0,
    }


def test_filters_narrow_every_figure(board: dict[str, Any]) -> None:
    b = board

    def figures(**params: Any) -> tuple[float, int, int]:
        body = get(b, **params)
        return body["recorded_hours"], body["recordings"], body["tasks_total"]

    assert figures() == (4.0, 3, 3)
    # Mode: the other mode's hours and target are left out.
    assert figures(mode="TELEPHONY") == (2.0, 1, 1)
    assert figures(mode="FACE_TO_FACE") == (2.0, 2, 2)
    phone = get(b, mode="TELEPHONY")
    assert phone["target_hours_per_day"] == 6.0
    assert [m["recordings"] for m in phone["by_mode"]] == [0, 1]
    assert get(b, mode="FACE_TO_FACE")["calls"]["placed"] == 0
    # Language and dialect of the people in the conversation.
    assert figures(language="hi") == (3.5, 2, 2)
    assert figures(language="ta") == (0.5, 1, 1)
    assert figures(dialect="Madurai") == (0.5, 1, 1)
    assert figures(language="hi", dialect="Madurai") == (0.0, 0, 0)
    assert figures(language="bn") == (0.0, 0, 0)  # nobody speaks it here: empty, not an error
    # Status of the task.
    assert figures(status="APPROVED") == (0.5, 1, 1)
    approved = get(b, status="APPROVED")
    assert approved["approved_hours"] == 0.5
    assert approved["tasks_by_status"] == {"APPROVED": 1}
    # One person's work: the tasks given to them and the recordings they made.
    theirs = get(b, staff_id=b["mod2_id"])
    assert (theirs["recorded_hours"], theirs["recordings"]) == (0.5, 1)
    assert [m["name"] for m in theirs["team"]] == ["mod2"]
    assert theirs["calls"]["placed"] == 0
    assert get(b, staff_id=b["mod_id"])["calls"]["placed"] == 1
    assert figures(staff_id=b["mod_id"], mode="FACE_TO_FACE") == (1.5, 1, 1)
    # Several filters together.
    assert figures(mode="FACE_TO_FACE", language="ta", status="APPROVED") == (0.5, 1, 1)
    # Storage follows the filters too.
    assert 0 < get(b, language="ta")["storage_bytes"] < get(b)["storage_bytes"]

    # What can be chosen.
    options = get(b)["options"]
    assert options["languages"] == ["hi", "ta"]
    assert options["dialects"] == ["Madurai"]
    assert sorted(s["name"] for s in options["staff"]) == ["mod", "mod2"]

    # What makes no sense is refused.
    assert get(b, mode="RADIO") == 422
    assert get(b, status="FINISHED") == 422
    assert get(b, language="x") == 422
    assert get(b, staff_id="not-an-id") == 422


def test_chosen_days_count_in_india_time_and_are_bounded(board: dict[str, Any]) -> None:
    b, day_a = board, board["day_a"]
    one = timedelta(days=1)

    def on(first: Any, last: Any) -> Any:
        return get(b, date_from=str(first), date_to=str(last))

    first = on(day_a, day_a)
    assert (first["recorded_hours"], first["recordings"]) == (2.0, 1)
    assert [d["day"] for d in first["daily"]] == [str(day_a)]
    assert (first["date_from"], first["date_to"]) == (str(day_a), str(day_a))
    # Ten minutes later is the next day: it is not in the first day and is in the second.
    second = on(day_a + one, day_a + one)
    assert (second["recorded_hours"], second["recordings"]) == (1.5, 1)
    both = on(day_a, day_a + one)
    assert (both["recorded_hours"], both["recordings"]) == (3.5, 2)
    assert [d["recorded_hours"] for d in both["daily"]] == [2.0, 1.5]
    assert both["team"] == [{"name": "mod", "recordings": 2, "recorded_hours": 3.5}]
    # Days with nothing: zeros, not an error; today's figure is 0 when today is not among them.
    empty = on(day_a - 10 * one, day_a - one)
    assert (empty["recorded_hours"], empty["recordings"], empty["today_hours"]) == (0.0, 0, 0.0)
    assert len(empty["daily"]) == 10
    assert empty["calls"]["placed"] == 0
    # Only a first day: up to today. Only a last day: the period before it.
    open_ended = get(b, date_from=str(day_a + 2 * one))
    assert (open_ended["recorded_hours"], len(open_ended["daily"])) == (0.5, 2)
    assert len(get(b, date_to=str(day_a), days=7)["daily"]) == 7
    # Without chosen days nothing changes: every recording counts, the last N days are shown.
    plain = get(b, days=7)
    assert (plain["recorded_hours"], plain["date_from"], len(plain["daily"])) == (4.0, None, 7)
    # Bounds (DASH-006).
    assert on(day_a, day_a - one) == 422
    assert on(day_a - 400 * one, day_a) == 422
    assert len(on(day_a - 365 * one, day_a)["daily"]) == 366
    assert get(b, date_from="yesterday") == 422


def test_filters_respect_who_is_asking(board: dict[str, Any]) -> None:
    b = board
    # A moderator has their own work, filtered like anyone's; never someone else's.
    mine = get(b, "mod")
    assert (mine["view"], mine["recorded_hours"], mine["recordings"]) == ("worker", 3.5, 2)
    assert get(b, "mod", mode="TELEPHONY")["recorded_hours"] == 2.0
    assert get(b, "mod", language="ta")["recordings"] == 0
    assert "staff" not in mine["options"]
    assert mine["calls"] is None
    assert get(b, "mod", staff_id=b["mod2_id"]) == 403
    assert get(b, "mod", staff_id=b["mod_id"]) == 403
    # A client viewer has progress, with the same filters and no people.
    project = (
        b["db"]
        .execute(text("SELECT id FROM projects WHERE id = :p"), {"p": b["project_id"]})
        .scalar_one()
    )
    from app.modules.projects.models import Project

    make_user(
        b["db"], "cv@example.org", ["CLIENT_VIEWER"], projects=[b["db"].get(Project, project)]
    )
    b["cv"] = b["api"]("cv@example.org")
    seen = get(b, "cv", mode="FACE_TO_FACE", date_from=str(b["day_a"]))
    assert (seen["view"], seen["recorded_hours"]) == ("client", 2.0)
    assert seen["options"] == {"languages": ["hi", "ta"], "dialects": ["Madurai"]}
    assert seen["team"] is None
    assert seen["calls"] is None
    assert seen["tasks_by_status"] is None
    assert get(b, "cv", staff_id=b["mod_id"]) == 403
    # A project that is not theirs is not there, with or without filters.
    make_user(b["db"], "pa.other@example.org", ["PROJECT_ADMIN"])
    b["outsider"] = b["api"]("pa.other@example.org")
    assert get(b, "outsider", mode="TELEPHONY") == 404

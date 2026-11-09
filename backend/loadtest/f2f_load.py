"""Face-to-face load test (owner's test list, Option G).

N moderators record at the same time: each signs in, starts its task, uploads a 5-second chunk
every 5 seconds (as the browser does), completes, and waits for its files. Meanwhile M people browse
the busiest list pages. Every request's time and status, the delay from "complete" to "files ready",
and the machine's CPU, memory, database connections and backend memory are recorded once a second.

The run stops by itself when CPU (5-second average) or memory passes --stop-at percent
(the owner's rule).

This measures the platform on the machine it runs on. It is NOT a capacity proof: CAP-004 accepts
only a load test on the production environment plus the telephony provider's confirmation.

Usage (backend running, DATABASE_URL pointing at its database, seed-dev done):
  uv run python -m loadtest.f2f_load --base http://127.0.0.1:8000 \
      --admin-email demo.super-admin@example.org --admin-password "$DEMO_PASSWORD" \
      --users 50 --browsers 10 --seconds 30 --report load.json
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import statistics
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx2 as httpx
import numpy as np
from sqlalchemy import create_engine, select, text

CHUNK_SECONDS = 5
RATE = 48_000


@dataclass
class Stats:
    calls: list[tuple[str, int, float]] = field(default_factory=list)  # (label, status, seconds)
    ready_delay: list[float] = field(default_factory=list)
    failed_recordings: list[str] = field(default_factory=list)
    samples: list[dict[str, float]] = field(default_factory=list)
    uploaded_bytes: int = 0
    stopped: str | None = None


STATS = Stats()
STOP = asyncio.Event()


async def call(client: httpx.AsyncClient, label: str, method: str, url: str, **kw: Any) -> Any:
    headers = dict(kw.pop("headers", {}))
    token = client.cookies.get("csrf_token")
    if method != "GET" and token:
        headers["X-CSRF-Token"] = token
    started = time.perf_counter()
    try:
        response = await client.request(method, url, headers=headers, **kw)
        status = response.status_code
    except httpx.HTTPError:
        response, status = None, 0
    STATS.calls.append((label, status, time.perf_counter() - started))
    return response


async def sign_in(base: str, email: str, password: str) -> httpx.AsyncClient:
    client = httpx.AsyncClient(base_url=base, timeout=120)
    await client.get("/api/v1/auth/csrf")
    r = await call(
        client, "sign in", "POST", "/api/v1/auth/login", json={"email": email, "password": password}
    )
    if r is None or r.status_code != 200:
        raise RuntimeError(f"sign-in failed for {email}: {r.status_code if r else 'no answer'}")
    return client


# ------------------------------------------------------------------------------------------ setup


def create_moderators(
    database_url: str, project_id: str, count: int, password: str, tag: str
) -> list[str]:
    """Moderator accounts written straight to the database (no invitation emails for 50 people)."""
    import app.db.models  # noqa: F401  (registers every model for the relationships)
    from app.modules.auth.models import RoleRecord, User
    from app.modules.auth.security import hash_password
    from app.modules.projects.models import ProjectMembership

    engine = create_engine(database_url)
    emails = [f"load.{tag}.{i:03d}@example.org" for i in range(count)]
    hashed = hash_password(password)
    from sqlalchemy.orm import Session

    with Session(engine) as db:
        role = db.scalars(select(RoleRecord).where(RoleRecord.code == "MODERATOR")).one()
        for email in emails:
            user = User(
                email=email, display_name=email.split("@")[0], password_hash=hashed, status="ACTIVE"
            )
            user.roles = [role]
            db.add(user)
            db.flush()
            db.add(ProjectMembership(user_id=user.id, project_id=uuid.UUID(project_id)))
        db.commit()
    engine.dispose()
    return emails


async def setup(args: argparse.Namespace, tag: str) -> list[tuple[str, str]]:
    admin = await sign_in(args.base, args.admin_email, args.admin_password)
    code = f"LOAD{tag.upper()}"
    project = (
        await call(
            admin,
            "setup",
            "POST",
            "/api/v1/projects",
            json={
                "code": code,
                "name": f"Load {code}",
                "allows_telephony": False,
                "allows_face_to_face": True,
            },
        )
    ).json()
    await call(
        admin,
        "setup",
        "POST",
        f"/api/v1/projects/{project['id']}/status",
        json={"status": "ACTIVE"},
    )
    await call(
        admin,
        "setup",
        "PUT",
        f"/api/v1/projects/{project['id']}/languages",
        json={"languages": [{"language_code": "hi", "dialect": ""}]},
    )
    emails = create_moderators(
        os.environ["DATABASE_URL"], project["id"], args.users, args.password, tag
    )
    users = (
        await call(admin, "setup", "GET", f"/api/v1/users?search=load.{tag}.&page_size=100")
    ).json()["items"]
    ids = {u["email"]: u["id"] for u in users}
    people = [
        (
            await call(
                admin,
                "setup",
                "POST",
                f"/api/v1/projects/{project['id']}/participants",
                json={"display_label": f"Person {n} {code}", "language_code": "hi"},
            )
        ).json()["id"]
        for n in (1, 2)
    ]
    pairs = []
    for email in emails:
        task = (
            await call(
                admin,
                "setup",
                "POST",
                "/api/v1/tasks",
                json={
                    "project_id": project["id"],
                    "recording_mode": "FACE_TO_FACE",
                    "participant_a_id": people[0],
                    "participant_b_id": people[1],
                },
            )
        ).json()
        await call(
            admin,
            "setup",
            "POST",
            f"/api/v1/tasks/{task['id']}/assign",
            json={"user_id": ids[email]},
        )
        pairs.append((email, task["id"]))
    await admin.aclose()
    return pairs


# ------------------------------------------------------------------------------------- workloads


def chunk_bytes() -> bytes:
    t = np.arange(RATE * CHUNK_SECONDS) / RATE
    return (0.3 * np.sin(2 * np.pi * 220 * t)).astype("<f4").tobytes()


async def moderator(
    args: argparse.Namespace, email: str, task_id: str, delay: float, data: bytes
) -> None:
    await asyncio.sleep(delay)
    client = await sign_in(args.base, email, args.password)
    sha = hashlib.sha256(data).hexdigest()
    try:
        await call(client, "task list", "GET", "/api/v1/tasks?page_size=25")
        await call(client, "task detail", "GET", f"/api/v1/tasks/{task_id}")
        await call(
            client,
            "task start",
            "POST",
            f"/api/v1/tasks/{task_id}/transition",
            json={"to": "IN_PROGRESS"},
        )
        rec = (
            await call(
                client,
                "recording start",
                "POST",
                f"/api/v1/tasks/{task_id}/recordings",
                json={
                    "native_sample_rate": RATE,
                    "channel_count": 1,
                    "device_channel_count": 1,
                    "echo_cancellation": False,
                    "noise_suppression": False,
                    "auto_gain_control": False,
                    "device_label": "load test",
                    "user_agent": "loadtest",
                },
            )
        ).json()
        chunks = args.seconds // CHUNK_SECONDS
        tick = time.monotonic()
        for seq in range(chunks):
            tick += CHUNK_SECONDS  # a chunk becomes available every 5 seconds of recording
            await asyncio.sleep(max(0.0, tick - time.monotonic()))
            if STOP.is_set():
                return
            for _attempt in range(5):  # the browser retries until the part is stored
                r = await call(
                    client,
                    "chunk upload",
                    "PUT",
                    f"/api/v1/recordings/{rec['id']}/chunks/{seq}",
                    content=data,
                    headers={"Content-Type": "application/octet-stream", "X-Content-SHA256": sha},
                )
                if r is not None and r.status_code == 200:
                    STATS.uploaded_bytes += len(data)
                    break
                await asyncio.sleep(2)
        await call(
            client,
            "recording complete",
            "POST",
            f"/api/v1/recordings/{rec['id']}/complete",
            json={"chunk_count": chunks},
        )
        done_at = time.monotonic()
        while not STOP.is_set() and time.monotonic() - done_at < 600:
            r = await call(client, "recording poll", "GET", f"/api/v1/recordings/{rec['id']}")
            state = r.json()["state"] if r is not None and r.status_code == 200 else ""
            if state == "READY":
                STATS.ready_delay.append(time.monotonic() - done_at)
                return
            if state == "FAILED":
                STATS.failed_recordings.append(rec["id"])
                return
            await asyncio.sleep(1)
        STATS.failed_recordings.append(f"{rec['id']} (not ready after 600 s)")
    finally:
        await client.aclose()


async def browser(args: argparse.Namespace, until: float) -> None:
    client = await sign_in(args.base, args.admin_email, args.admin_password)
    pages = [
        "/api/v1/projects?page_size=25",
        "/api/v1/tasks?page_size=25",
        "/api/v1/audit-logs?page_size=50",
        "/api/v1/users?page_size=25",
        "/api/v1/storage/usage",
    ]
    try:
        i = 0
        while not STOP.is_set() and time.monotonic() < until:
            path = pages[i % len(pages)]
            await call(client, f"browse {path.split('?')[0].removeprefix('/api/v1/')}", "GET", path)
            i += 1
            await asyncio.sleep(1)
    finally:
        await client.aclose()


# ------------------------------------------------------------------------------------- monitoring


def _cpu() -> tuple[int, int]:
    fields = [int(x) for x in Path("/proc/stat").read_text().splitlines()[0].split()[1:]]
    idle = fields[3] + fields[4]
    return sum(fields), idle


def _memory_pct() -> float:
    info = {
        row.split(":")[0]: int(row.split()[1])
        for row in Path("/proc/meminfo").read_text().splitlines()
    }
    return 100 * (1 - info["MemAvailable"] / info["MemTotal"])


def _rss_mb(pid: int) -> float:
    """Memory of the backend process and its worker processes (uvicorn --workers)."""
    pids = {pid}
    for stat in Path("/proc").glob("[0-9]*/stat"):
        try:
            parts = stat.read_text().rsplit(")", 1)[1].split()
        except OSError:
            continue
        if int(parts[1]) == pid:
            pids.add(int(stat.parent.name))
    total = 0.0
    for each in pids:
        try:
            for line in Path(f"/proc/{each}/status").read_text().splitlines():
                if line.startswith("VmRSS:"):
                    total += int(line.split()[1]) / 1024
        except OSError:
            continue
    return total


async def monitor(args: argparse.Namespace) -> None:
    engine = create_engine(os.environ["DATABASE_URL"])
    last = _cpu()
    window: list[float] = []
    while not STOP.is_set():
        await asyncio.sleep(1)
        now = _cpu()
        total, idle = now[0] - last[0], now[1] - last[1]
        last = now
        cpu = 100 * (1 - idle / total) if total else 0.0
        window = [*window, cpu][-5:]
        with engine.connect() as conn:
            connections = conn.execute(
                text("SELECT count(*) FROM pg_stat_activity WHERE datname = current_database()")
            ).scalar_one()
        sample = {
            "t": time.time(),
            "cpu": cpu,
            "mem": _memory_pct(),
            "backend_rss_mb": _rss_mb(args.backend_pid),
            "db_connections": connections,
        }
        STATS.samples.append(sample)
        if statistics.mean(window) > args.stop_at:
            STATS.stopped = (
                f"CPU above {args.stop_at}% (5-second average {statistics.mean(window):.0f}%)"
            )
        elif sample["mem"] > args.stop_at:
            STATS.stopped = f"memory above {args.stop_at}% ({sample['mem']:.0f}%)"
        if STATS.stopped:
            STOP.set()
    engine.dispose()


# ----------------------------------------------------------------------------------------- report


def pct(values: list[float], p: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, round(p / 100 * (len(ordered) - 1)))] if ordered else 0.0


def report(args: argparse.Namespace, wall: float) -> dict[str, Any]:
    by_label: dict[str, list[tuple[int, float]]] = defaultdict(list)
    for label, status, seconds in STATS.calls:
        by_label[label].append((status, seconds))
    endpoints = {}
    for label, rows in sorted(by_label.items()):
        times = [s for _, s in rows]
        errors: dict[str, int] = defaultdict(int)
        for status, _ in rows:
            if status == 0 or status >= 400:
                errors[str(status)] += 1
        endpoints[label] = {
            "requests": len(rows),
            "errors": dict(errors),
            "p50_ms": round(1000 * pct(times, 50)),
            "p95_ms": round(1000 * pct(times, 95)),
            "p99_ms": round(1000 * pct(times, 99)),
            "max_ms": round(1000 * max(times)),
        }
    s = STATS.samples
    return {
        "moderators": args.users,
        "browsers": args.browsers,
        "recording_seconds": args.seconds,
        "wall_seconds": round(wall),
        "stopped_early": STATS.stopped,
        "requests": len(STATS.calls),
        "error_requests": sum(1 for _, st, _ in STATS.calls if st == 0 or st >= 400),
        "uploaded_mb": round(STATS.uploaded_bytes / 1e6, 1),
        "recordings_ready": len(STATS.ready_delay),
        "recordings_failed": STATS.failed_recordings,
        "ready_delay_s": {
            "p50": round(pct(STATS.ready_delay, 50), 1),
            "p95": round(pct(STATS.ready_delay, 95), 1),
            "max": round(max(STATS.ready_delay or [0]), 1),
        },
        "machine": {
            "cpu_5s_average_max": round(
                max(
                    (statistics.mean(x["cpu"] for x in s[i : i + 5]) for i in range(len(s))),
                    default=0,
                )
            ),
            "cpu_max": round(max((x["cpu"] for x in s), default=0)),
            "cpu_mean": round(statistics.mean(x["cpu"] for x in s)) if s else 0,
            "memory_max_pct": round(max((x["mem"] for x in s), default=0)),
            "backend_rss_max_mb": round(max((x["backend_rss_mb"] for x in s), default=0)),
            "db_connections_max": max((x["db_connections"] for x in s), default=0),
        },
        "endpoints": endpoints,
        "timeline": [
            {k: round(v, 1) for k, v in x.items() if k != "t"}
            | {"second": round(x["t"] - s[0]["t"])}
            for x in s
        ],
    }


async def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--base", default="http://127.0.0.1:8000")
    parser.add_argument("--admin-email", default="demo.super-admin@example.org")
    parser.add_argument("--admin-password", required=True)
    parser.add_argument("--password", default=f"load-{uuid.uuid4().hex}")
    parser.add_argument("--users", type=int, default=50)
    parser.add_argument("--browsers", type=int, default=10)
    parser.add_argument("--seconds", type=int, default=30)
    parser.add_argument(
        "--ramp", type=float, default=10.0, help="seconds over which moderators start"
    )
    parser.add_argument("--stop-at", type=float, default=90.0)
    parser.add_argument("--backend-pid", type=int, required=True, help="server (or uvicorn parent)")
    parser.add_argument("--report", default="load.json")
    args = parser.parse_args()

    tag = uuid.uuid4().hex[:6]
    print(f"setting up {args.users} moderators and tasks (tag {tag}) ...", flush=True)
    pairs = await setup(args, tag)
    STATS.calls.clear()
    data = chunk_bytes()
    print(
        f"running: {args.users} moderators x {args.seconds} s, {args.browsers} browsers", flush=True
    )
    started = time.monotonic()
    until = started + args.ramp + args.seconds + 60
    mon = asyncio.create_task(monitor(args))
    work = [
        moderator(args, email, task, i * args.ramp / max(1, args.users), data)
        for i, (email, task) in enumerate(pairs)
    ]
    work += [browser(args, until) for _ in range(args.browsers)]
    await asyncio.gather(*work, return_exceptions=False)
    STOP.set()
    await mon
    result = report(args, time.monotonic() - started)
    await asyncio.to_thread(Path(args.report).write_text, json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    asyncio.run(main())

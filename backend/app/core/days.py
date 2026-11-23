"""Calendar days as people choose them (in the report time zone, India), turned into the moments
stored times are compared with: from the start of the first day to the start of the day after the
last one."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.core.errors import AppError


def start_of(day: date, zone: ZoneInfo) -> datetime:
    """Midnight at the start of `day` in `zone`."""
    return datetime.combine(day, time.min, zone)


def local_now(tz_name: str) -> datetime:
    """Now in `tz_name` (the report time zone). Download file names are dated with it, so a file
    saved at 01:00 in India carries that day, not the day before in UTC."""
    return datetime.now(ZoneInfo(tz_name))


# The days anyone may choose: wide enough for every real report, narrow enough that turning a day
# into a moment never runs off the calendar (9999-12-31 + 1 day failed with a 500; security audit
# 2026-11-23, D-160).
EARLIEST_DAY = date(2000, 1, 1)
LATEST_DAY = date(2100, 12, 31)


def check_days(first: date | None, last: date | None) -> None:
    """422 when a day is outside 2000-2100, or both are given and the first is after the last."""
    for day in (first, last):
        if day is not None and not EARLIEST_DAY <= day <= LATEST_DAY:
            raise AppError(
                f"Choose a day between {EARLIEST_DAY.year} and {LATEST_DAY.year}",
                code="VALIDATION_ERROR",
                status_code=422,
            )
    if first and last and first > last:
        raise AppError(
            "The first day must not be after the last day",
            code="VALIDATION_ERROR",
            status_code=422,
        )


def day_bounds(
    first: date | None, last: date | None, tz_name: str
) -> tuple[datetime | None, datetime | None]:
    """(start, end) for times t with start <= t < end; a day not given leaves that end open.
    The days are checked first (check_days)."""
    check_days(first, last)
    zone = ZoneInfo(tz_name)
    return (
        start_of(first, zone) if first else None,
        start_of(last + timedelta(days=1), zone) if last else None,
    )

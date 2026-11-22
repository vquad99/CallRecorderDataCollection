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


def check_days(first: date | None, last: date | None) -> None:
    """422 when both days are given and the first is after the last."""
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

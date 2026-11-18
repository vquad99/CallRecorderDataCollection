"""Calendar days as people choose them (in the report time zone, India), turned into the moments
stored times are compared with: from the start of the first day to the start of the day after the
last one."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo


def start_of(day: date, zone: ZoneInfo) -> datetime:
    """Midnight at the start of `day` in `zone`."""
    return datetime.combine(day, time.min, zone)


def day_bounds(
    first: date | None, last: date | None, tz_name: str
) -> tuple[datetime | None, datetime | None]:
    """(start, end) for times t with start <= t < end; a day not given leaves that end open."""
    zone = ZoneInfo(tz_name)
    return (
        start_of(first, zone) if first else None,
        start_of(last + timedelta(days=1), zone) if last else None,
    )

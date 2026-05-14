"""Display formatting utilities — convert UTC datetimes to local display timezone."""

from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from gatekeeper.config import settings


def _tz() -> ZoneInfo:
    """Get the display timezone (cached after first call by ZoneInfo internals)."""
    return ZoneInfo(settings.display_timezone)


def format_dt(dt: datetime | None, fmt: str = "%Y-%m-%d %H:%M") -> str | None:
    """Convert a UTC datetime to the display timezone and format it.

    Args:
        dt: A datetime (assumed UTC if tz-aware, treated as UTC if naive).
        fmt: strftime format string. Default is 24-hour: "2025-01-15 14:30".

    Returns:
        Formatted string, or None if dt is None.
    """
    if dt is None:
        return None

    # Naive datetimes from SQLite are UTC — make them aware
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)

    local_dt = dt.astimezone(_tz())
    return local_dt.strftime(fmt)


def format_dt_iso(dt: datetime | None) -> str | None:
    """Convert a UTC datetime to the display timezone in ISO 8601 format.

    Returns something like "2025-01-15T14:30:00-06:00" — ISO format with
    the local offset. Used for JSON API responses where clients need
    unambiguous timestamps but should see local time.
    """
    if dt is None:
        return None

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)

    local_dt = dt.astimezone(_tz())
    return local_dt.isoformat()

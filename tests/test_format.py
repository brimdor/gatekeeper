"""Tests for display timezone formatting."""

from datetime import UTC, datetime

from gatekeeper.format import format_dt, format_dt_iso


class TestFormatDt:
    """format_dt converts UTC datetimes to the display timezone."""

    def test_none_returns_none(self):
        assert format_dt(None) is None

    def test_naive_datetime_treated_as_utc(self):
        # Naive datetime (from SQLite) — should be treated as UTC
        dt = datetime(2025, 5, 14, 18, 30)  # 18:30 UTC
        result = format_dt(dt)
        # America/Chicago is CDT (UTC-5) in May, so 18:30 UTC = 13:30 CDT
        assert result == "2025-05-14 13:30"

    def test_aware_utc_datetime(self):
        dt = datetime(2025, 5, 14, 18, 30, tzinfo=UTC)
        result = format_dt(dt)
        assert result == "2025-05-14 13:30"

    def test_24_hour_format(self):
        # 01:30 UTC = 20:30 CDT on May 13
        dt = datetime(2025, 5, 14, 1, 30, tzinfo=UTC)
        result = format_dt(dt)
        assert result == "2025-05-13 20:30"

    def test_custom_format(self):
        dt = datetime(2025, 5, 14, 18, 30, tzinfo=UTC)
        result = format_dt(dt, fmt="%Y-%m-%d %H:%M:%S")
        assert result == "2025-05-14 13:30:00"

    def test_winter_time_cst(self):
        # January = CST (UTC-6), so 12:00 UTC = 06:00 CST
        dt = datetime(2025, 1, 15, 12, 0, tzinfo=UTC)
        result = format_dt(dt)
        assert result == "2025-01-15 06:00"


class TestFormatDtIso:
    """format_dt_iso returns ISO 8601 with local offset."""

    def test_none_returns_none(self):
        assert format_dt_iso(None) is None

    def test_naive_datetime(self):
        dt = datetime(2025, 5, 14, 18, 30)
        result = format_dt_iso(dt)
        # CDT = UTC-5
        assert result is not None
        assert result.startswith("2025-05-14T13:30:")
        assert "-05:00" in result

    def test_aware_utc_datetime(self):
        dt = datetime(2025, 1, 15, 12, 0, tzinfo=UTC)
        result = format_dt_iso(dt)
        # CST = UTC-6
        assert result is not None
        assert result.startswith("2025-01-15T06:00:")
        assert "-06:00" in result

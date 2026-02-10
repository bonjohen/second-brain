"""Tests for core.utils helpers."""

from datetime import UTC, datetime, timezone

from second_brain.core.utils import parse_utc_datetime, safe_json_loads


class TestParseUtcDatetime:
    def test_parse_iso_string(self):
        result = parse_utc_datetime("2025-06-15T12:30:00")
        assert result == datetime(2025, 6, 15, 12, 30, 0, tzinfo=UTC)

    def test_naive_datetime_gets_utc(self):
        naive = datetime(2025, 1, 1, 0, 0, 0)
        result = parse_utc_datetime(naive)
        assert result.tzinfo is UTC

    def test_aware_datetime_unchanged(self):
        from datetime import timedelta

        tz = timezone(timedelta(hours=-5))
        aware = datetime(2025, 1, 1, 12, 0, 0, tzinfo=tz)
        result = parse_utc_datetime(aware)
        assert result.tzinfo is tz  # not replaced

    def test_datetime_passthrough(self):
        dt = datetime(2025, 3, 15, 8, 0, 0, tzinfo=UTC)
        result = parse_utc_datetime(dt)
        assert result is dt  # exact same object


class TestSafeJsonLoads:
    def test_valid_json(self):
        assert safe_json_loads('{"a": 1}') == {"a": 1}

    def test_valid_list(self):
        assert safe_json_loads('[1, 2, 3]') == [1, 2, 3]

    def test_corrupt_json_returns_default(self):
        assert safe_json_loads("{bad json", default=[]) == []

    def test_none_returns_default(self):
        assert safe_json_loads(None, default={}) == {}

    def test_default_is_none(self):
        assert safe_json_loads(None) is None

from datetime import date

import pytest

from finbro.domain.coverage import DateRange, coverage_gaps, merge_ranges, uncovered


def r(a: str, b: str) -> DateRange:
    return DateRange(date.fromisoformat(a), date.fromisoformat(b))


def test_gap_between_imports():
    imports = [r("2026-10-05", "2026-10-11"), r("2026-10-19", "2026-10-25")]
    assert coverage_gaps(imports, date(2026, 10, 5)) == [r("2026-10-12", "2026-10-18")]


def test_no_gap_for_overlapping_and_adjacent_imports():
    imports = [r("2026-10-05", "2026-10-11"), r("2026-10-08", "2026-10-18"), r("2026-10-19", "2026-10-25")]
    assert coverage_gaps(imports, date(2026, 10, 5)) == []


def test_gap_after_start_date_before_first_import():
    imports = [r("2026-10-08", "2026-10-11")]
    assert coverage_gaps(imports, date(2026, 10, 5)) == [r("2026-10-05", "2026-10-07")]


def test_history_before_start_is_ignored():
    imports = [r("2026-01-01", "2026-01-31"), r("2026-10-05", "2026-10-11")]
    assert coverage_gaps(imports, date(2026, 10, 5)) == []


def test_no_imports_or_no_start_date():
    assert coverage_gaps([], date(2026, 10, 5)) == []
    assert coverage_gaps([r("2026-10-05", "2026-10-11")], None) == []


def test_uncovered_within_week():
    week = r("2026-10-12", "2026-10-18")
    assert uncovered([r("2026-10-08", "2026-10-14")], week) == [r("2026-10-15", "2026-10-18")]
    assert uncovered([r("2026-10-01", "2026-10-31")], week) == []
    assert uncovered([], week) == [week]
    assert uncovered([r("2026-10-13", "2026-10-13"), r("2026-10-15", "2026-10-16")], week) == [
        r("2026-10-12", "2026-10-12"),
        r("2026-10-14", "2026-10-14"),
        r("2026-10-17", "2026-10-18"),
    ]


def test_merge_ranges():
    assert merge_ranges([r("2026-10-10", "2026-10-12"), r("2026-10-01", "2026-10-09")]) == [r("2026-10-01", "2026-10-12")]


def test_invalid_range():
    with pytest.raises(ValueError):
        r("2026-10-12", "2026-10-11")


def test_label():
    assert r("2026-10-12", "2026-10-18").label() == "2026-10-12 – 2026-10-18"
    assert r("2026-10-12", "2026-10-12").days == 1

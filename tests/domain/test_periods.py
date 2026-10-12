from datetime import date

import pytest

from finbro.domain.periods import (
    IsoWeek,
    Month,
    PeriodKind,
    Year,
    parse_period,
    period_of,
    periods_ending_at,
)


def test_week_of_saturday_2026_10_10_is_t41():
    week = IsoWeek.of(date(2026, 10, 10))
    assert week == IsoWeek(2026, 41)
    assert week.label == "2026-T41"
    assert week.start == date(2026, 10, 5)
    assert week.end == date(2026, 10, 11)


def test_week_of_2026_10_31_is_t44():
    week = IsoWeek.of(date(2026, 10, 31))
    assert week.label == "2026-T44"
    assert week.start == date(2026, 10, 26)
    assert week.end == date(2026, 11, 1)


def test_monday_belongs_to_new_week():
    assert IsoWeek.of(date(2026, 10, 12)) == IsoWeek(2026, 42)
    assert IsoWeek.of(date(2026, 10, 11)) == IsoWeek(2026, 41)


@pytest.mark.parametrize(
    ("day", "label"),
    [
        (date(2026, 12, 31), "2026-T53"),  # 2026 ma 53 tygodnie (1 stycznia to czwartek)
        (date(2027, 1, 1), "2026-T53"),
        (date(2027, 1, 3), "2026-T53"),
        (date(2027, 1, 4), "2027-T01"),
        (date(2024, 12, 30), "2025-T01"),  # poniedziałek grudnia w pierwszym tygodniu nowego roku
        (date(2021, 1, 3), "2020-T53"),
    ],
)
def test_year_boundary(day, label):
    assert IsoWeek.of(day).label == label


def test_prev_and_next_across_year_boundary():
    assert IsoWeek(2026, 53).next() == IsoWeek(2027, 1)
    assert IsoWeek(2027, 1).prev() == IsoWeek(2026, 53)
    assert IsoWeek(2025, 52).next() == IsoWeek(2026, 1)
    assert IsoWeek(2026, 41).prev() == IsoWeek(2026, 40)


def test_week_parse_and_validation():
    assert IsoWeek.parse("2026-T41") == IsoWeek(2026, 41)
    assert IsoWeek.parse("2026-t7") == IsoWeek(2026, 7)
    with pytest.raises(ValueError):
        IsoWeek(2025, 53)  # 2025 ma 52 tygodnie
    with pytest.raises(ValueError):
        IsoWeek.parse("2026-41")


def test_week_contains():
    week = IsoWeek(2026, 41)
    assert week.contains(date(2026, 10, 5))
    assert week.contains(date(2026, 10, 11))
    assert not week.contains(date(2026, 10, 12))


def test_month_period():
    month = Month.of(date(2026, 10, 31))
    assert month.label == "2026-10"
    assert month.title == "październik 2026"
    assert month.start == date(2026, 10, 1)
    assert month.end == date(2026, 10, 31)
    assert Month(2026, 2).end == date(2026, 2, 28)
    assert Month(2028, 2).end == date(2028, 2, 29)
    assert Month(2026, 12).next() == Month(2027, 1)
    assert Month(2026, 1).prev() == Month(2025, 12)
    assert Month.parse("2026-11") == Month(2026, 11)
    with pytest.raises(ValueError):
        Month(2026, 13)


def test_year_period():
    year = Year.of(date(2026, 10, 10))
    assert year.start == date(2026, 1, 1)
    assert year.end == date(2026, 12, 31)
    assert year.prev() == Year(2025) and year.next() == Year(2027)
    assert Year.parse("2026") == year


def test_card_payment_from_saturday_booked_on_monday():
    # Data transakcji wyznacza okres, niezależnie od daty księgowania.
    tx_date = date(2026, 10, 31)
    assert period_of(PeriodKind.MONTH, tx_date) == Month(2026, 10)
    assert period_of(PeriodKind.WEEK, tx_date).label == "2026-T44"


def test_parse_period_and_trend_window():
    assert parse_period(PeriodKind.WEEK, "2026-T41") == IsoWeek(2026, 41)
    weeks = periods_ending_at(IsoWeek(2026, 2), 4)
    assert [w.label for w in weeks] == ["2025-T51", "2025-T52", "2026-T01", "2026-T02"]
    months = periods_ending_at(Month(2026, 2), 3)
    assert [m.label for m in months] == ["2025-12", "2026-01", "2026-02"]

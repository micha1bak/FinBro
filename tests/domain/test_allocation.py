from datetime import date

import pytest
from hypothesis import given
from hypothesis import strategies as st

from finbro.domain.allocation import Plan, PlanError, format_percent, parse_percent, plan_for, split, total
from finbro.domain.envelopes import Envelope
from finbro.domain.money import Money

P, W, X, O = Envelope.PKO, Envelope.WAKACJE, Envelope.XTB, Envelope.OBLIGACJE
DEFAULT = Plan(date(2000, 1, 1), {P: 5000, W: 2500, X: 1250, O: 1250})


def zl(text: str) -> Money:
    return Money.parse(text)


def test_split_with_grosze():
    assert split(zl("2401,30"), DEFAULT) == {P: zl("1201,30"), W: zl("600"), X: zl("300"), O: zl("300")}


def test_split_rounds_halves_up():
    # 43,50 -> 44, 21,75 -> 22
    assert split(zl("174,00"), DEFAULT) == {P: zl("86"), W: zl("44"), X: zl("22"), O: zl("22")}


def test_split_rounds_down_below_half():
    # 25% z 1,98 = 0,495 -> 0; 12,5% = 0,2475 -> 0
    assert split(zl("1,98"), DEFAULT) == {P: zl("1,98"), W: zl("0"), X: zl("0"), O: zl("0")}


def test_split_order_starts_with_pko():
    assert list(split(zl("100"), DEFAULT)) == [P, W, X, O]


def test_split_rejects_non_positive_amount():
    with pytest.raises(ValueError):
        split(Money.zero(), DEFAULT)


@given(st.integers(min_value=1, max_value=10**10), st.integers(0, 3333), st.integers(0, 3333), st.integers(0, 3333))
def test_split_always_sums_to_amount(grosze, w, x, o):
    plan = Plan(date(2000, 1, 1), {P: 10_000 - w - x - o, W: w, X: x, O: o})
    parts = split(Money(grosze), plan)
    assert sum(parts.values(), Money.zero()) == Money(grosze)
    assert all(parts[e].grosze % 100 == 0 for e in (W, X, O))


def test_total_of_month():
    month = total([split(zl("2401,30"), DEFAULT), split(zl("174,00"), DEFAULT)])
    assert month == {P: zl("1287,30"), W: zl("644"), X: zl("322"), O: zl("322")}
    assert sum(month.values(), Money.zero()) == zl("2575,30")


def test_plan_for_day():
    november = Plan(date(2026, 11, 1), {P: 6000, W: 2000, X: 1000, O: 1000})
    plans = [november, DEFAULT]
    assert plan_for(plans, date(2026, 10, 31)) is DEFAULT
    assert plan_for(plans, date(2026, 11, 1)) is november
    with pytest.raises(PlanError):
        plan_for(plans, date(1999, 12, 31))


@pytest.mark.parametrize(
    "shares, message",
    [
        ({P: 5000, W: 2000, X: 1250, O: 1250}, "95%"),
        ({P: 11000, W: -1000, X: 0, O: 0}, "ujemne"),
        ({P: 10000}, "każdej koperty"),
    ],
)
def test_invalid_plan(shares, message):
    with pytest.raises(PlanError, match=message):
        Plan(date(2026, 11, 1), shares)


@pytest.mark.parametrize("text, bp", [("50", 5000), ("12,5", 1250), ("12.5%", 1250), ("0", 0), ("33,33", 3333)])
def test_parse_percent(text, bp):
    assert parse_percent(text) == bp


@pytest.mark.parametrize("text", ["", "abc", "-5", "12,555", "1000"])
def test_parse_percent_rejects(text):
    with pytest.raises(PlanError):
        parse_percent(text)


@pytest.mark.parametrize("bp, text", [(5000, "50%"), (1250, "12,5%"), (3333, "33,33%"), (9500, "95%")])
def test_format_percent(bp, text):
    assert format_percent(bp) == text

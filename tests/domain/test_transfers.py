from datetime import date

from hypothesis import given
from hypothesis import strategies as st

from finbro.domain.allocation import Plan
from finbro.domain.envelopes import Envelope
from finbro.domain.money import Money
from finbro.domain.transfers import PlannedIncome, Transfer, distribute, pooled, transfer_title, transfers

P, W, X, O = Envelope.PKO, Envelope.WAKACJE, Envelope.XTB, Envelope.OBLIGACJE
DEFAULT = Plan(date(2000, 1, 1), {P: 5000, W: 2500, X: 1250, O: 1250})
NOVEMBER = Plan(date(2026, 11, 1), {P: 6000, W: 2000, X: 1000, O: 1000})
DAY = date(2026, 10, 19)


def zl(text):
    return Money.parse(text)


def incomes(*amounts, plan=DEFAULT):
    return [PlannedIncome(zl(a), plan) for a in amounts]


def test_two_incomes_give_three_transfers_without_pko():
    result = transfers(incomes("2401,30", "174"), DAY)
    assert result == [
        Transfer(W, zl("644"), "FinBro Wakacje 2026-10-19"),
        Transfer(X, zl("322"), "FinBro XTB 2026-10-19"),
        Transfer(O, zl("322"), "FinBro Obligacje 2026-10-19"),
    ]


def test_transfers_are_rounded_from_the_sum():
    # 348 × 25% = 87, a nie 44 + 44 z podziałów pojedynczych dochodów; 43,50 -> 44.
    assert pooled(incomes("174", "174")) == {P: zl("173"), W: zl("87"), X: zl("44"), O: zl("44")}


def test_incomes_from_different_plans_are_summed_per_plan():
    mixed = incomes("174") + incomes("174", "174", plan=NOVEMBER)
    # Październik: 44 / 22 / 22; listopad od 348 zł: 69,60 -> 70, 34,80 -> 35 (a nie 17 + 17).
    assert [(t.envelope, t.amount) for t in transfers(mixed, DAY)] == [(W, zl("114")), (X, zl("57")), (O, zl("57"))]


def test_envelope_with_zero_sum_is_skipped():
    # 1,98 zł: Wakacje, XTB i Obligacje zaokrąglają się do 0 zł.
    assert transfers(incomes("1,98"), DAY) == []
    no_bonds = Plan(date(2000, 1, 1), {P: 5000, W: 2500, X: 2500, O: 0})
    assert [t.envelope for t in transfers(incomes("100", plan=no_bonds), DAY)] == [W, X]


def test_no_incomes_no_transfers():
    assert transfers([], DAY) == []
    assert distribute([]) == []


def test_title_format():
    assert transfer_title(O, date(2026, 1, 5)) == "FinBro Obligacje 2026-01-05"


def test_distribute_gives_tied_zloty_to_earlier_income():
    # Wakacje 43,50 + 43,50 = 87: brakujący złoty dostaje wcześniejszy dochód; XTB 21,75 + 21,75 = 44: oba w górę.
    assert distribute(incomes("174", "174")) == [
        {P: zl("86"), W: zl("44"), X: zl("22"), O: zl("22")},
        {P: zl("87"), W: zl("43"), X: zl("22"), O: zl("22")},
    ]


def test_distribute_prefers_largest_remainder():
    # Wakacje 25,10 + 25,90 = 51: reszta 0,90 wygrywa z 0,10.
    first, second = distribute(incomes("100,40", "103,60"))
    assert (first[W], second[W]) == (zl("25"), zl("26"))


def test_distribute_keeps_plan_groups_apart():
    mixed = incomes("174") + incomes("174", "174", plan=NOVEMBER)
    parts = distribute(mixed)
    assert parts[0] == {P: zl("86"), W: zl("44"), X: zl("22"), O: zl("22")}
    # Listopad: Wakacje 34,80 + 34,80 = 70 -> 35 / 35; XTB 17,40 + 17,40 = 35 -> 18 / 17.
    assert parts[1] == {P: zl("103"), W: zl("35"), X: zl("18"), O: zl("18")}
    assert parts[2] == {P: zl("105"), W: zl("35"), X: zl("17"), O: zl("17")}


@given(
    st.lists(st.tuples(st.integers(1, 10**8), st.booleans()), min_size=1, max_size=12),
    st.integers(0, 3333),
    st.integers(0, 3333),
    st.integers(0, 3333),
)
def test_distribute_sums_to_transfers_and_amounts(items, w, x, o):
    other = Plan(date(2026, 11, 1), {P: 10_000 - w - x - o, W: w, X: x, O: o})
    planned = [PlannedIncome(Money(grosze), other if later else DEFAULT) for grosze, later in items]
    parts = distribute(planned)
    sums = pooled(planned)
    for envelope in Envelope:
        assert sum((p[envelope] for p in parts), Money.zero()) == sums[envelope]
    for income, p in zip(planned, parts, strict=True):
        assert sum(p.values(), Money.zero()) == income.amount
        assert all(p[e].grosze % 100 == 0 and not p[e].is_negative for e in (W, X, O))

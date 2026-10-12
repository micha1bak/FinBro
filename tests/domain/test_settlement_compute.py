from datetime import date

from finbro.domain.allocation import AllocationPlan
from finbro.domain.enums import SettlementStatus
from finbro.domain.money import Money
from finbro.domain.periods import IsoWeek
from finbro.domain.settlement import (
    IncomeContribution,
    LineState,
    Settlement,
    SettlementLine,
    carryover_before,
    compute_lines,
    line_state,
    nearest_open_week,
    settlement_status,
)

LIFE, XTB, BONDS, HOLIDAY = 1, 2, 3, 4
ENVELOPES = [LIFE, XTB, BONDS, HOLIDAY]
PLAN = AllocationPlan(date(2000, 1, 1), {LIFE: 5000, XTB: 1250, BONDS: 1250, HOLIDAY: 2500}, LIFE)
NEW_PLAN = AllocationPlan(date(2026, 11, 2), {LIFE: 6000, XTB: 1000, BONDS: 1000, HOLIDAY: 2000}, LIFE)
M = Money.parse


def lines_by_envelope(lines):
    return {line.envelope_id: line for line in lines}


def compute(contributions, carry=None, plans=(PLAN,)):
    return lines_by_envelope(compute_lines(contributions, list(plans), ENVELOPES, LIFE, carry or {}))


def test_split_with_rounding():
    lines = compute([IncomeContribution(M("4250.00"), date(2026, 10, 5)), IncomeContribution(M("700.03"), date(2026, 10, 9))])
    assert lines[XTB].due == M("618.75")
    assert lines[BONDS].due == M("618.75")
    assert lines[HOLIDAY].due == M("1237.50")
    assert lines[LIFE].due == M("2475.03")
    assert sum((line.to_transfer for line in lines.values()), Money.zero()) == M("4950.03")


def closed_t41(lines):
    return Settlement(
        week=IsoWeek(2026, 41),
        status=SettlementStatus.CLOSED,
        lines=tuple(SettlementLine(l.envelope_id, l.due, l.corrections, l.carryover, id=100 + l.envelope_id) for l in lines.values()),
    )


def test_underpayment_is_carried_forward():
    t41 = closed_t41(compute([IncomeContribution(M("4950.03"), date(2026, 10, 7))]))
    carry = carryover_before([t41], {100 + HOLIDAY: M("1200.00"), 100 + XTB: M("618.75"), 100 + BONDS: M("618.75")}, LIFE)
    assert carry[HOLIDAY] == M("37.50")
    t42 = compute([IncomeContribution(M("1000.00"), date(2026, 10, 14))], carry)
    assert t42[HOLIDAY].carryover == M("37.50")
    assert t42[HOLIDAY].to_transfer == M("287.50")
    assert t42[LIFE].carryover == Money.zero()


def test_overpayment_reduces_next_transfer():
    t41 = closed_t41(compute([IncomeContribution(M("4950.03"), date(2026, 10, 7))]))
    carry = carryover_before([t41], {100 + XTB: M("700.00")}, LIFE)
    assert carry[XTB] == M("-81.25")
    t42 = compute([], carry)
    assert t42[XTB].to_transfer == M("-81.25")  # ujemna kwota: brak przelewu
    assert line_state(t42[XTB], Money.zero(), carried_forward=False) is LineState.NO_TRANSFER


def test_negative_amount_keeps_moving_until_covered():
    t41 = closed_t41(compute([IncomeContribution(M("4950.03"), date(2026, 10, 7))]))
    t42 = Settlement(
        week=IsoWeek(2026, 42),
        status=SettlementStatus.CLOSED,
        lines=(SettlementLine(XTB, Money.zero(), Money.zero(), M("-81.25"), id=200),),
    )
    carry = carryover_before([t41, t42], {100 + XTB: M("700.00")}, LIFE)
    assert carry[XTB] == M("-81.25")  # T42 nic nie spłacał, więc nadpłata dalej pomniejsza
    t43 = compute([IncomeContribution(M("1000.00"), date(2026, 10, 21))], carry)
    assert t43[XTB].to_transfer == M("125.00") - M("81.25")


def test_corrections_are_rounded_separately_and_use_plan_of_income_date():
    lines = compute(
        [
            IncomeContribution(M("1000.00"), date(2026, 11, 3)),  # dochód tygodnia, nowy plan
            IncomeContribution(M("1000.00"), date(2026, 10, 28), correction=True),  # późny, stary plan
            IncomeContribution(M("-400.00"), date(2026, 10, 8), correction=True),  # wycofanie, stary plan
        ],
        plans=(PLAN, NEW_PLAN),
    )
    assert lines[HOLIDAY].due == M("200.00")  # 20% nowego planu
    assert lines[HOLIDAY].corrections == M("150.00")  # 25% z (1000 - 400)
    assert lines[XTB].corrections == M("75.00")
    assert lines[LIFE].due == M("600.00") and lines[LIFE].corrections == M("300.00")
    assert sum((l.due + l.corrections for l in lines.values()), Money.zero()) == M("1600.00")


def test_proportion_change_does_not_affect_earlier_incomes():
    lines = compute(
        [IncomeContribution(M("100.01"), date(2026, 11, 1)), IncomeContribution(M("100.01"), date(2026, 11, 2))],
        plans=(PLAN, NEW_PLAN),
    )
    # Dwie grupy zaokrąglane osobno: 12,50 (stary 12,5%) i 10,00 (nowy 10%).
    assert lines[XTB].due == M("12.50") + M("10.00")
    assert lines[HOLIDAY].due == M("25.00") + M("20.00")
    assert sum((l.due for l in lines.values()), Money.zero()) == M("200.02")


def test_status_settled_when_all_transfers_covered():
    t41 = closed_t41(compute([IncomeContribution(M("4950.03"), date(2026, 10, 7))]))
    paid = {100 + XTB: M("618.75"), 100 + BONDS: M("618.75")}
    assert settlement_status(t41, paid, carried_forward=False, life_envelope_id=LIFE) is SettlementStatus.CLOSED
    paid[100 + HOLIDAY] = M("1237.50")
    assert settlement_status(t41, paid, carried_forward=False, life_envelope_id=LIFE) is SettlementStatus.SETTLED


def test_underpaid_week_is_settled_once_shortfall_moved_to_later_closed_week():
    t41 = closed_t41(compute([IncomeContribution(M("4950.03"), date(2026, 10, 7))]))
    paid = {100 + XTB: M("618.75"), 100 + BONDS: M("618.75"), 100 + HOLIDAY: M("1200.00")}
    assert line_state(t41.line_for(HOLIDAY), paid[100 + HOLIDAY], carried_forward=False) is LineState.PENDING
    assert line_state(t41.line_for(HOLIDAY), paid[100 + HOLIDAY], carried_forward=True) is LineState.CARRIED
    assert settlement_status(t41, paid, carried_forward=True, life_envelope_id=LIFE) is SettlementStatus.SETTLED


def test_nearest_open_week():
    closed = {IsoWeek(2026, 41), IsoWeek(2026, 42)}
    assert nearest_open_week(IsoWeek(2026, 41), closed) == IsoWeek(2026, 43)
    assert nearest_open_week(IsoWeek(2026, 40), closed) == IsoWeek(2026, 40)

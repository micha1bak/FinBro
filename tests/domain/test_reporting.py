from datetime import date
from itertools import count

from finbro.domain.enums import TransferKind, TxSource, TxType
from finbro.domain.money import Money
from finbro.domain.periods import IsoWeek, Month, periods_ending_at
from finbro.domain.reporting import (
    category_breakdown,
    expenses_by_category,
    incomplete,
    top_counterparties,
    totals,
    trend,
)
from finbro.domain.transactions import Classification, Transaction, TransactionData

T41 = IsoWeek(2026, 41)
GROCERIES, RESTAURANTS, GIFTS, CASH = 1, 2, 10, 14
_ids = count(1)
M = Money.parse


def tx(amount: str, tx_type: TxType | None, day=date(2026, 10, 7), confirmed=True, source=TxSource.IMPORT, **c) -> Transaction:
    return Transaction(
        id=next(_ids),
        data=TransactionData(source=source, transaction_date=day, amount=M(amount), merchant=c.pop("merchant", None)),
        classification=Classification(type=tx_type, confirmed=confirmed and tx_type is not None, **c),
    )


def test_refund_and_repayment_are_not_income():
    txs = [
        tx("+705.87", TxType.DOCHOD),
        tx("+477.08", TxType.TRANSFER, transfer_kind=TransferKind.FAMILY),
        tx("+500.00", TxType.SPLATA, debtor_id=1),
    ]
    assert totals(txs, T41).income == M("705.87")


def test_savings_and_own_transfers_are_not_expenses():
    txs = [
        tx("-200.00", TxType.WYDATEK, category_id=GROCERIES),
        tx("-1237.50", TxType.ODKLADANIE, envelope_id=4),
        tx("-2300.00", TxType.TRANSFER, transfer_kind=TransferKind.WALLET),
        tx("-645.00", TxType.POZYCZKA, debtor_id=1),
    ]
    assert totals(txs, T41).expenses == M("200.00")


def test_shared_expense_settlement_reduces_category():
    txs = [
        tx("-200.00", TxType.WYDATEK, category_id=RESTAURANTS),
        tx("+150.00", TxType.ROZLICZENIE, category_id=RESTAURANTS),
    ]
    assert expenses_by_category(txs) == {RESTAURANTS: M("50.00")}
    assert totals(txs, T41).expenses == M("50.00")
    assert totals(txs, T41).income == Money.zero()


def test_refund_for_purchase_reduces_category():
    txs = [tx("-300.00", TxType.WYDATEK, category_id=GROCERIES), tx("+40.00", TxType.ZWROT, category_id=GROCERIES)]
    assert expenses_by_category(txs) == {GROCERIES: M("260.00")}


def test_forgiveness_and_inventory_shortfall_are_expenses():
    txs = [
        tx("-150.00", TxType.WYDATEK, source=TxSource.FORGIVENESS, category_id=GIFTS, debtor_id=1),
        tx("-560.00", TxType.WYDATEK, source=TxSource.INVENTORY, category_id=CASH),
    ]
    assert totals(txs, T41).expenses == M("710.00")
    assert expenses_by_category(txs) == {GIFTS: M("150.00"), CASH: M("560.00")}


def test_unconfirmed_items_are_not_counted():
    txs = [tx("+477.08", TxType.DOCHOD, confirmed=False), tx("-30.00", None)]
    result = totals(txs, T41)
    assert (result.income, result.expenses) == (Money.zero(), Money.zero())


def test_transaction_date_decides_period():
    # Płatność z 31.10 zaksięgowana 2.11 należy do października i do T44.
    payment = Transaction(
        id=next(_ids),
        data=TransactionData(source=TxSource.IMPORT, transaction_date=date(2026, 10, 31), booking_date=date(2026, 11, 2),
                             amount=M("-99.00")),
        classification=Classification(type=TxType.WYDATEK, category_id=GROCERIES, confirmed=True),
    )
    assert totals([payment], Month(2026, 10)).expenses == M("99.00")
    assert totals([payment], Month(2026, 11)).expenses == Money.zero()
    assert totals([payment], IsoWeek(2026, 44)).expenses == M("99.00")


def test_month_balance():
    txs = [tx("+9000.00", TxType.DOCHOD, day=date(2026, 10, 2)), tx("-5200.00", TxType.WYDATEK, day=date(2026, 10, 20), category_id=1)]
    result = totals(txs, Month(2026, 10))
    assert (result.income, result.expenses, result.balance) == (M("9000.00"), M("5200.00"), M("3800.00"))


def test_trend_ends_with_selected_period():
    txs = [tx("+100.00", TxType.DOCHOD, day=date(2026, 10, 7)), tx("-40.00", TxType.WYDATEK, day=date(2026, 9, 30), category_id=1)]
    points = trend(txs, periods_ending_at(T41, 3))
    assert [p.period.label for p in points] == ["2026-T39", "2026-T40", "2026-T41"]
    assert [(p.income, p.expenses) for p in points] == [
        (Money.zero(), Money.zero()),
        (Money.zero(), M("40.00")),
        (M("100.00"), Money.zero()),
    ]


def test_category_breakdown_with_shares():
    txs = [
        tx("-100.00", TxType.WYDATEK, category_id=GROCERIES),
        tx("-50.00", TxType.WYDATEK, category_id=GROCERIES),
        tx("-50.00", TxType.WYDATEK, category_id=3),
    ]
    shares = category_breakdown(txs, T41)
    assert [(s.category_id, s.amount, s.percent) for s in shares] == [
        (GROCERIES, M("150.00"), "75%"),
        (3, M("50.00"), "25%"),
    ]


def test_category_share_rounding():
    txs = [tx("-1.00", TxType.WYDATEK, category_id=1), tx("-2.00", TxType.WYDATEK, category_id=2)]
    assert [s.percent for s in category_breakdown(txs, T41)] == ["66,67%", "33,33%"]


def test_system_cash_category_is_included():
    txs = [tx("-560.00", TxType.WYDATEK, source=TxSource.INVENTORY, category_id=CASH)]
    assert [(s.category_id, s.percent) for s in category_breakdown(txs, T41)] == [(CASH, "100%")]


def test_top_merchants():
    txs = [
        tx("-54.30", TxType.WYDATEK, category_id=1, merchant="JMP S.A. BIEDRONKA 2422"),
        tx("-88.10", TxType.WYDATEK, category_id=1, merchant="JMP S.A. BIEDRONKA 2422", day=date(2026, 10, 9)),
        tx("-120.45", TxType.WYDATEK, category_id=2, merchant="RESTAURACJA POD TESTEM"),
        tx("-7.00", TxType.WYDATEK, category_id=1, merchant="ZABKA Z8627 K.1"),
        tx("-2300.00", TxType.TRANSFER, merchant="BANKOMAT"),  # nie jest wydatkiem
    ]
    ranking = top_counterparties(txs, Month(2026, 10))
    assert [(c.name, c.amount, c.count) for c in ranking] == [
        ("JMP S.A. BIEDRONKA 2422", M("142.40"), 2),
        ("RESTAURACJA POD TESTEM", M("120.45"), 1),
        ("ZABKA Z8627 K.1", M("7.00"), 1),
    ]


def test_incomplete_items_are_reported_but_not_counted():
    txs = [tx("+705.87", TxType.DOCHOD), tx("+477.08", TxType.DOCHOD, confirmed=False)]
    info = incomplete(txs, T41)
    assert (info.count, info.total) == (1, M("477.08"))
    assert totals(txs, T41).income == M("705.87")

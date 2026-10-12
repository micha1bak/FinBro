from datetime import date
from itertools import count

from finbro.domain.enums import TransferKind, TxSource, TxType
from finbro.domain.money import Money
from finbro.domain.periods import IsoWeek, Month, periods_ending_at
from finbro.domain.reporting import expenses_by_category, totals, trend
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

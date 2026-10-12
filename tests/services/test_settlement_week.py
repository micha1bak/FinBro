from datetime import date

from finbro.domain.enums import SettlementStatus, TxSource, TxType
from finbro.domain.money import Money
from finbro.domain.periods import IsoWeek
from finbro.domain.settlement import CLOSED_STATUSES, Settlement
from finbro.domain.transactions import TransactionData
from finbro.services.classification import ClassificationService, Decision
from finbro.services.wallet import WalletService

T41, T42, T43 = IsoWeek(2026, 41), IsoWeek(2026, 42), IsoWeek(2026, 43)


def income_tx(uow, amount: str, day: date):
    account = uow.reference.account("pko")
    return uow.transactions.add(
        TransactionData(source=TxSource.MANUAL, account_id=account.id, transaction_date=day, amount=Money.parse(amount),
                        counterparty_name="KLIENT TESTOWY")
    )


def close(uow, week: IsoWeek):
    uow.settlements.save_closed(Settlement(week=week, status=SettlementStatus.CLOSED))
    uow.commit()


def confirm_income(uow, tx):
    return ClassificationService(uow).decide(tx.id, Decision(type=TxType.DOCHOD))


def test_income_goes_to_week_of_its_date(uow):
    tx = confirm_income(uow, income_tx(uow, "+705.87", date(2026, 10, 11)))
    assert tx.classification.settlement_week == T41.start


def test_late_approved_income_goes_to_next_open_week_as_correction(uow):
    tx = income_tx(uow, "+1000.00", date(2026, 10, 7))
    close(uow, T41)
    confirmed = confirm_income(uow, tx)
    assert confirmed.classification.settlement_week == T42.start
    assert uow.settlements.get(T41).status in CLOSED_STATUSES  # T41 się nie zmienia
    assert uow.settlements.get(T41).lines == ()


def test_skips_all_closed_weeks(uow):
    tx = income_tx(uow, "+1000.00", date(2026, 10, 7))
    close(uow, T41)
    close(uow, T42)
    assert confirm_income(uow, tx).classification.settlement_week == T43.start


def test_withdrawn_income_from_closed_week_creates_negative_correction(uow):
    WalletService(uow).add_cash_loan(date(2026, 10, 1), Money.parse("500.00"), None, "Martyna")
    martyna = uow.reference.debtor_by_name("Martyna")
    tx = confirm_income(uow, income_tx(uow, "+400.00", date(2026, 10, 8)))
    assert tx.classification.settlement_week == T41.start
    close(uow, T41)

    changed = ClassificationService(uow).decide(tx.id, Decision(type=TxType.SPLATA, debtor_id=martyna.id))
    assert changed.classification.settlement_week is None
    [adjustment] = uow.settlements.adjustments(T42)
    assert (adjustment.amount, adjustment.income_date, adjustment.transaction_id) == (
        Money.parse("-400.00"), date(2026, 10, 8), tx.id)


def test_withdrawing_income_from_open_week_needs_no_correction(uow):
    tx = confirm_income(uow, income_tx(uow, "+400.00", date(2026, 10, 8)))
    changed = ClassificationService(uow).decide(tx.id, Decision(type=TxType.TRANSFER))
    assert changed.classification.settlement_week is None
    assert uow.settlements.adjustments(T41) == [] and uow.settlements.adjustments(T42) == []


def test_reapproving_withdrawn_income_from_closed_week(uow):
    tx = confirm_income(uow, income_tx(uow, "+400.00", date(2026, 10, 8)))
    close(uow, T41)
    ClassificationService(uow).decide(tx.id, Decision(type=TxType.TRANSFER))
    again = confirm_income(uow, tx)
    # Ujemna korekta i ponowny dochód w T42 znoszą się.
    assert again.classification.settlement_week == T42.start
    assert [a.amount for a in uow.settlements.adjustments(T42)] == [Money.parse("-400.00")]


def test_income_before_start_date_is_not_split(uow):
    tx = confirm_income(uow, income_tx(uow, "+300.00", date(2026, 10, 4)))
    assert tx.classification.type is TxType.DOCHOD
    assert tx.classification.settlement_week is None


def test_cash_income_gets_settlement_week(uow):
    tx = WalletService(uow).add_cash_income(date(2026, 10, 7), Money.parse("800.00"))
    assert tx.classification.settlement_week == T41.start

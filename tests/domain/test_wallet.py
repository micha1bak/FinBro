from datetime import date

from finbro.domain.enums import ProposalSource, TransferKind, TxSource, TxType
from finbro.domain.money import Money
from finbro.domain.transactions import Classification, Transaction, TransactionData
from finbro.domain.wallet import expected_balance, wallet_effect

BANK, WALLET = 1, 2
START = date(2026, 10, 5)
_ids = iter(range(1, 10_000))


def tx(account: int | None, amount: str, day: date = date(2026, 10, 7), **classification) -> Transaction:
    c = Classification(confirmed=True, **classification) if classification else Classification()
    data = TransactionData(
        source=TxSource.IMPORT if account == BANK else TxSource.MANUAL,
        account_id=account,
        transaction_date=day,
        amount=Money.parse(amount),
    )
    return Transaction(id=next(_ids), data=data, classification=c)


def balance(*txs: Transaction, opening: str = "500.00", at: date = date(2026, 10, 11)) -> Money:
    return expected_balance(Money.parse(opening), START, txs, WALLET, at)


def test_opening_balance_only():
    assert balance() == Money.parse("500.00")


def test_cash_income_increases():
    assert balance(tx(WALLET, "+800.00", type=TxType.DOCHOD)) == Money.parse("1300.00")


def test_cash_expense_decreases():
    assert balance(tx(WALLET, "-120.00", type=TxType.WYDATEK, category_id=2)) == Money.parse("380.00")


def test_atm_withdrawal_increases():
    atm = tx(BANK, "-2300.00", type=TxType.TRANSFER, transfer_kind=TransferKind.WALLET, source=ProposalSource.RULE)
    assert wallet_effect(atm, WALLET) == Money.parse("2300.00")
    assert balance(atm) == Money.parse("2800.00")


def test_cash_deposit_decreases():
    deposit = tx(BANK, "+1000.00", type=TxType.TRANSFER, transfer_kind=TransferKind.WALLET)
    assert balance(deposit, opening="1500.00") == Money.parse("500.00")


def test_cash_loan_and_repayment():
    loan = tx(WALLET, "-200.00", type=TxType.POZYCZKA, debtor_id=1)
    repayment = tx(WALLET, "+50.00", day=date(2026, 10, 9), type=TxType.SPLATA, debtor_id=1)
    assert balance(loan, repayment) == Money.parse("350.00")


def test_inventory_shortfall_and_surplus():
    shortfall = tx(WALLET, "-560.00", type=TxType.WYDATEK, category_id=14)
    # Nadwyżka czeka w skrzynce na decyzję, ale już wyrównuje stan oczekiwany.
    surplus = tx(WALLET, "+150.00", day=date(2026, 10, 10))
    assert balance(shortfall, surplus, opening="900.00") == Money.parse("490.00")


def test_unrelated_bank_transactions_are_ignored():
    family = tx(BANK, "-300.00", type=TxType.TRANSFER, transfer_kind=TransferKind.FAMILY)
    expense = tx(BANK, "-54.30", type=TxType.WYDATEK, category_id=1)
    unconfirmed_atm = Transaction(
        id=next(_ids),
        data=TransactionData(source=TxSource.IMPORT, account_id=BANK, transaction_date=date(2026, 10, 7), amount=Money.parse("-100.00")),
        classification=Classification(type=TxType.TRANSFER, transfer_kind=TransferKind.WALLET, confirmed=False),
    )
    assert balance(family, expense, unconfirmed_atm) == Money.parse("500.00")


def test_date_window():
    before_start = tx(WALLET, "-100.00", day=date(2026, 10, 1), type=TxType.WYDATEK, category_id=1)
    later = tx(WALLET, "-100.00", day=date(2026, 10, 12), type=TxType.WYDATEK, category_id=1)
    assert balance(before_start, later) == Money.parse("500.00")
    assert balance(later, at=date(2026, 10, 12)) == Money.parse("400.00")
    # Przed dniem startu nie ma jeszcze stanu początkowego.
    assert balance(at=date(2026, 10, 4)) == Money.zero()

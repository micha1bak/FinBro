from datetime import date

import pytest
from sqlalchemy import func, select

from finbro.db import models
from finbro.domain.enums import ProposalSource, TxSource, TxType
from finbro.domain.money import Money
from finbro.services.wallet import WalletError, WalletService

DAY = date(2026, 10, 11)


@pytest.fixture
def wallet(uow):
    service = WalletService(uow)
    return service


def tx_count(db_session) -> int:
    return db_session.scalar(select(func.count()).select_from(models.Transaction))


def test_shortfall_becomes_uncategorized_cash_expense(wallet, uow, db_session):
    wallet.set_opening_balance(Money.parse("900.00"), date(2026, 10, 5))
    assert wallet.expected(DAY) == Money.parse("900.00")

    result = wallet.inventory(DAY, Money.parse("340.00"))

    tx = result.transaction
    assert tx.amount == Money.parse("-560.00")
    assert tx.transaction_date == DAY
    assert tx.data.source is TxSource.INVENTORY
    c = tx.classification
    system = uow.reference.system_category()
    assert (c.type, c.category_id, c.confirmed, c.source) == (TxType.WYDATEK, system.id, True, ProposalSource.SYSTEM)
    assert wallet.expected(DAY) == Money.parse("340.00")
    assert result.inventory.expected == Money.parse("900.00")
    assert result.inventory.transaction_id == tx.id


def test_matching_balance_creates_no_entry(wallet, db_session):
    wallet.set_opening_balance(Money.parse("300.00"), date(2026, 10, 5))
    before = tx_count(db_session)
    result = wallet.inventory(DAY, Money.parse("300.00"))
    assert result.transaction is None
    assert result.inventory.difference == Money.zero()
    assert tx_count(db_session) == before


def test_surplus_goes_to_inbox_and_is_not_income_until_decided(wallet, uow):
    wallet.set_opening_balance(Money.parse("300.00"), date(2026, 10, 5))
    result = wallet.inventory(DAY, Money.parse("450.00"))

    tx = result.transaction
    assert tx.amount == Money.parse("150.00")
    assert (tx.classification.type, tx.classification.confirmed) == (None, False)
    assert "DOCHÓD" in tx.classification.reason and "TRANSFER" in tx.classification.reason
    assert tx.id in {t.id for t in uow.transactions.unconfirmed()}
    assert tx.id not in uow.llm_jobs.queued_transaction_ids()
    assert wallet.expected(DAY) == Money.parse("450.00")


def test_negative_actual_balance_is_rejected(wallet):
    with pytest.raises(WalletError):
        wallet.inventory(DAY, Money.parse("-1.00"))


"""Portfel gotówkowy: stan początkowy, ręczne wpisy gotówkowe i stan oczekiwany."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from finbro.domain.enums import ProposalSource, TxSource, TxType
from finbro.domain.money import Money
from finbro.domain.reference import Account
from finbro.domain.transactions import Classification, Transaction, TransactionData
from finbro.domain.wallet import WalletEntry, expected_balance, wallet_entries
from finbro.services.classification import ClassificationService
from finbro.services.uow import UnitOfWork

WALLET_ACCOUNT_CODE = "portfel"


class WalletError(ValueError):
    """Niepoprawny wpis gotówkowy."""


def positive(amount: Money, what: str = "Kwota") -> Money:
    if not amount.is_positive:
        raise WalletError(f"{what} musi być większa od zera.")
    return amount


@dataclass(frozen=True)
class WalletState:
    account: Account
    at: date
    expected: Money
    entries: list[WalletEntry]


class WalletService:
    def __init__(self, uow: UnitOfWork) -> None:
        self.uow = uow

    @property
    def account(self) -> Account:
        return self.uow.reference.account(WALLET_ACCOUNT_CODE)

    def expected(self, at: date) -> Money:
        account = self.account
        txs = self.uow.transactions.wallet_related(account.id)
        return expected_balance(account.opening_balance, account.opening_date, txs, account.id, at)

    def state(self, at: date) -> WalletState:
        account = self.account
        txs = self.uow.transactions.wallet_related(account.id)
        entries = [e for e in wallet_entries(txs, account.id) if e.transaction.transaction_date <= at]
        expected = expected_balance(account.opening_balance, account.opening_date, txs, account.id, at)
        return WalletState(account=account, at=at, expected=expected, entries=entries)

    def set_opening_balance(self, amount: Money, on: date) -> Account:
        if amount.is_negative:
            raise WalletError("Stan początkowy nie może być ujemny.")
        account = self.uow.reference.set_opening_balance(WALLET_ACCOUNT_CODE, amount, on)
        self.uow.commit()
        return account

    def _add(self, day: date, amount: Money, note: str | None) -> Transaction:
        return self.uow.transactions.add(
            TransactionData(
                source=TxSource.MANUAL,
                account_id=self.account.id,
                transaction_date=day,
                booking_date=day,
                amount=amount,
                note=(note or "").strip() or None,
            )
        )

    def _add_confirmed(self, day: date, amount: Money, note: str | None, classification: Classification) -> Transaction:
        try:
            tx = self._add(day, amount, note)
            confirmed = ClassificationService(self.uow).confirm(tx, classification)
        except Exception:
            self.uow.rollback()
            raise
        self.uow.commit()
        return confirmed

    def add_cash_income(self, day: date, amount: Money, note: str | None = None) -> Transaction:
        """Dochód gotówkowy jest od razu zatwierdzonym DOCHODEM (bez skrzynki)."""
        return self._add_confirmed(
            day, positive(amount), note, Classification(type=TxType.DOCHOD, source=ProposalSource.USER)
        )

    def add_cash_expense(self, day: date, amount: Money, category_id: int | None, note: str | None = None) -> Transaction:
        return self._add_confirmed(
            day,
            -positive(amount),
            note,
            Classification(type=TxType.WYDATEK, category_id=category_id, source=ProposalSource.USER),
        )

"""Portfel gotówkowy: stan początkowy, ręczne wpisy gotówkowe i stan oczekiwany."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from finbro.domain.enums import ProposalSource, TxSource, TxType
from finbro.domain.money import Money
from finbro.domain.reference import Account
from finbro.domain.transactions import Classification, Transaction, TransactionData
from finbro.domain.wallet import Inventory, WalletEntry, expected_balance, wallet_entries
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
class InventoryResult:
    inventory: Inventory
    transaction: Transaction | None


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

    def inventory(self, day: date, actual: Money) -> InventoryResult:
        """Inwentaryzacja: porównuje faktyczny stan z oczekiwanym i wyrównuje różnicę.

        Niedobór staje się wydatkiem w kategorii systemowej z datą inwentaryzacji.
        Nadwyżka trafia do skrzynki jako niezatwierdzona pozycja (dochód gotówkowy albo
        korekta stanu) i do czasu decyzji nie wchodzi do podziału. Stan zgodny nie tworzy wpisu.
        """
        if actual.is_negative:
            raise WalletError("Faktyczny stan Portfela nie może być ujemny.")
        try:
            expected = self.expected(day)
            difference = actual - expected
            tx: Transaction | None = None
            if difference.is_negative:
                tx = self._add_inventory_tx(day, difference, "Inwentaryzacja: niezapisane wydatki gotówkowe")
                system = self.uow.reference.system_category()
                tx = ClassificationService(self.uow).confirm(
                    tx,
                    Classification(type=TxType.WYDATEK, category_id=system.id, source=ProposalSource.SYSTEM),
                    chosen_by_user=False,
                )
            elif difference.is_positive:
                tx = self._add_inventory_tx(day, difference, "Inwentaryzacja: nadwyżka gotówki")
                tx = self.uow.transactions.set_classification(
                    tx.id,
                    Classification(
                        reason="Nadwyżka w Portfelu: wybierz DOCHÓD (niezapisany dochód gotówkowy) "
                        "albo TRANSFER (korekta stanu)."
                    ),
                )
            record = self.uow.inventories.add(day, actual, expected, tx.id if tx else None)
        except Exception:
            self.uow.rollback()
            raise
        self.uow.commit()
        return InventoryResult(inventory=record, transaction=tx)

    def _add_inventory_tx(self, day: date, amount: Money, note: str) -> Transaction:
        return self.uow.transactions.add(
            TransactionData(
                source=TxSource.INVENTORY,
                account_id=self.account.id,
                transaction_date=day,
                booking_date=day,
                amount=amount,
                note=note,
            )
        )

    def add_cash_expense(self, day: date, amount: Money, category_id: int | None, note: str | None = None) -> Transaction:
        return self._add_confirmed(
            day,
            -positive(amount),
            note,
            Classification(type=TxType.WYDATEK, category_id=category_id, source=ProposalSource.USER),
        )

    def _debtor_id(self, debtor_id: int | None, new_debtor_name: str | None) -> int:
        if debtor_id is not None:
            return debtor_id
        name = (new_debtor_name or "").strip()
        if not name:
            raise WalletError("Wybierz dłużnika albo wpisz nowego.")
        debtor = self.uow.reference.debtor_by_name(name) or self.uow.reference.add_debtor(name)
        return debtor.id

    def add_cash_loan(
        self, day: date, amount: Money, debtor_id: int | None, new_debtor_name: str | None = None, note: str | None = None
    ) -> Transaction:
        """Pożyczka gotówkowa: zwiększa saldo dłużnika i zmniejsza stan Portfela, nie jest wydatkiem."""
        debtor = self._debtor_id(debtor_id, new_debtor_name)
        return self._add_confirmed(
            day, -positive(amount), note, Classification(type=TxType.POZYCZKA, debtor_id=debtor, source=ProposalSource.USER)
        )

    def add_cash_repayment(
        self, day: date, amount: Money, debtor_id: int | None, new_debtor_name: str | None = None, note: str | None = None
    ) -> Transaction:
        """Spłata gotówkowa: zmniejsza saldo dłużnika i zwiększa stan Portfela, nie jest dochodem."""
        debtor = self._debtor_id(debtor_id, new_debtor_name)
        return self._add_confirmed(
            day, positive(amount), note, Classification(type=TxType.SPLATA, debtor_id=debtor, source=ProposalSource.USER)
        )

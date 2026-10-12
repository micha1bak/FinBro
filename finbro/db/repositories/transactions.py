"""Repozytorium transakcji i ich klasyfikacji."""

from __future__ import annotations

from datetime import date

from sqlalchemy import ColumnElement, func, or_, select
from sqlalchemy.orm import Session, selectinload

from finbro.db import models
from finbro.domain.enums import TransferKind, TxType
from finbro.domain.history import CounterpartyKey
from finbro.domain.money import Money
from finbro.domain.transactions import Classification, Direction, Transaction, TransactionData, TransactionFilter

_PL_UPPER, _PL_PLAIN = "ĄĆĘŁŃÓŚŹŻąćęłńóśźż", "ACELNOSZZacelnoszz"


def _folded(column: ColumnElement[str | None]) -> ColumnElement[str]:
    """Odpowiednik ``finbro.domain.text.fold`` w SQL: małe litery, bez polskich znaków i nadmiarowych spacji."""
    collapsed = func.trim(func.regexp_replace(column, r"\s+", " ", "g"))
    return func.lower(func.translate(collapsed, _PL_UPPER, _PL_PLAIN))

_DATA_FIELDS = (
    "source",
    "transaction_date",
    "account_id",
    "booking_date",
    "occurrence",
    "bank_type",
    "raw_description",
    "counterparty_name",
    "counterparty_account",
    "counterparty_address",
    "title",
    "merchant",
    "city",
    "country",
    "reference_number",
    "note",
    "import_batch_id",
)

_CLASSIFICATION_FIELDS = (
    "type",
    "category_id",
    "debtor_id",
    "transfer_kind",
    "envelope_id",
    "source",
    "rule_id",
    "reason",
    "confirmed",
    "confirmed_at",
    "settlement_week",
)


def data_to_row(data: TransactionData) -> models.Transaction:
    return models.Transaction(
        **{name: getattr(data, name) for name in _DATA_FIELDS},
        amount=data.amount.grosze,
        balance_after=data.balance_after.grosze if data.balance_after is not None else None,
        extra=dict(data.extra),
    )


def row_to_data(row: models.Transaction) -> TransactionData:
    return TransactionData(
        **{name: getattr(row, name) for name in _DATA_FIELDS},
        amount=Money(row.amount),
        balance_after=Money(row.balance_after) if row.balance_after is not None else None,
        extra=dict(row.extra or {}),
    )


def classification_to_domain(row: models.Classification | None) -> Classification:
    if row is None:
        return Classification()
    return Classification(**{name: getattr(row, name) for name in _CLASSIFICATION_FIELDS})


def row_to_domain(row: models.Transaction) -> Transaction:
    return Transaction(id=row.id, data=row_to_data(row), classification=classification_to_domain(row.classification))


class TransactionRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, data: TransactionData, classification: Classification | None = None) -> Transaction:
        row = data_to_row(data)
        self.session.add(row)
        self.session.flush()
        if classification is not None:
            self._write_classification(row.id, classification)
        return self.get(row.id)

    def get(self, transaction_id: int) -> Transaction:
        row = self.session.get(
            models.Transaction,
            transaction_id,
            options=[selectinload(models.Transaction.classification)],
            populate_existing=True,
        )
        if row is None:
            raise LookupError(f"Brak transakcji o id {transaction_id}")
        return row_to_domain(row)

    def get_many(self, ids: list[int]) -> list[Transaction]:
        if not ids:
            return []
        rows = self.session.scalars(
            select(models.Transaction)
            .where(models.Transaction.id.in_(ids))
            .options(selectinload(models.Transaction.classification))
            .order_by(models.Transaction.transaction_date, models.Transaction.id)
        ).all()
        return [row_to_domain(r) for r in rows]

    def list_between(self, date_from: date, date_to: date, account_id: int | None = None) -> list[Transaction]:
        stmt = (
            select(models.Transaction)
            .where(models.Transaction.transaction_date.between(date_from, date_to))
            .options(selectinload(models.Transaction.classification))
            .order_by(models.Transaction.transaction_date, models.Transaction.id)
        )
        if account_id is not None:
            stmt = stmt.where(models.Transaction.account_id == account_id)
        return [row_to_domain(r) for r in self.session.scalars(stmt)]

    def last_confirmed_like(self, key: CounterpartyKey, exclude_id: int | None = None) -> Transaction | None:
        """Ostatnia zatwierdzona transakcja tego kontrahenta w tym samym kierunku.

        Najpierw szukamy po rachunku kontrahenta, a gdy brak wyniku, po znormalizowanej
        nazwie kontrahenta lub sprzedawcy (bez wielkości liter, polskich znaków i nadmiarowych spacji).
        """
        tx, cl = models.Transaction, models.Classification
        base = (
            select(tx)
            .join(cl, cl.transaction_id == tx.id)
            .where(cl.confirmed, cl.type.is_not(None))
            .where(tx.amount > 0 if key.direction is Direction.IN else tx.amount < 0)
            .options(selectinload(tx.classification))
            .order_by(tx.transaction_date.desc(), tx.id.desc())
            .limit(1)
        )
        if exclude_id is not None:
            base = base.where(tx.id != exclude_id)
        if key.account:
            account = func.right(func.upper(func.regexp_replace(tx.counterparty_account, r"[^0-9A-Za-z]", "", "g")), len(key.account))
            row = self.session.scalar(base.where(account == key.account))
            if row is not None:
                return row_to_domain(row)
        if key.name:
            row = self.session.scalar(base.where(or_(_folded(tx.counterparty_name) == key.name, _folded(tx.merchant) == key.name)))
            if row is not None:
                return row_to_domain(row)
        return None

    def search(self, f: TransactionFilter) -> list[Transaction]:
        tx, cl = models.Transaction, models.Classification
        stmt = (
            select(tx)
            .outerjoin(cl, cl.transaction_id == tx.id)
            .where(tx.transaction_date.between(f.date_from, f.date_to))
            .options(selectinload(tx.classification))
            .order_by(tx.transaction_date.desc(), tx.id.desc())
        )
        if f.type is not None:
            stmt = stmt.where(cl.type == f.type)
        if f.category_id is not None:
            stmt = stmt.where(cl.category_id == f.category_id)
        if f.only_unconfirmed:
            stmt = stmt.where(or_(cl.transaction_id.is_(None), cl.confirmed.is_(False)))
        if f.text:
            pattern = f"%{f.text.strip()}%"
            stmt = stmt.where(
                or_(
                    tx.counterparty_name.ilike(pattern),
                    tx.merchant.ilike(pattern),
                    tx.title.ilike(pattern),
                    tx.note.ilike(pattern),
                )
            )
        return [row_to_domain(r) for r in self.session.scalars(stmt)]

    def debtor_related(self) -> list[Transaction]:
        """Zatwierdzone transakcje powiązane z dłużnikami (pożyczki, spłaty, darowania)."""
        tx, cl = models.Transaction, models.Classification
        stmt = (
            select(tx)
            .join(cl, cl.transaction_id == tx.id)
            .where(cl.confirmed.is_(True), cl.debtor_id.is_not(None))
            .options(selectinload(tx.classification))
            .order_by(tx.transaction_date, tx.id)
        )
        return [row_to_domain(r) for r in self.session.scalars(stmt)]

    def wallet_related(self, wallet_account_id: int) -> list[Transaction]:
        """Transakcje Portfela oraz zatwierdzone transfery z udziałem Portfela na innych kontach."""
        tx, cl = models.Transaction, models.Classification
        stmt = (
            select(tx)
            .outerjoin(cl, cl.transaction_id == tx.id)
            .where(
                or_(
                    tx.account_id == wallet_account_id,
                    (cl.confirmed.is_(True)) & (cl.type == TxType.TRANSFER) & (cl.transfer_kind == TransferKind.WALLET),
                )
            )
            .options(selectinload(tx.classification))
            .order_by(tx.transaction_date, tx.id)
        )
        return [row_to_domain(r) for r in self.session.scalars(stmt)]

    def unconfirmed(self) -> list[Transaction]:
        """Transakcje czekające na decyzję: bez klasyfikacji albo z niezatwierdzoną propozycją."""
        tx, cl = models.Transaction, models.Classification
        stmt = (
            select(tx)
            .outerjoin(cl, cl.transaction_id == tx.id)
            .where(or_(cl.transaction_id.is_(None), cl.confirmed.is_(False)))
            .options(selectinload(tx.classification))
            .order_by(tx.transaction_date, tx.id)
        )
        return [row_to_domain(r) for r in self.session.scalars(stmt)]

    def set_classification(self, transaction_id: int, classification: Classification) -> Transaction:
        self._write_classification(transaction_id, classification)
        return self.get(transaction_id)

    def _write_classification(self, transaction_id: int, classification: Classification) -> None:
        row = self.session.get(models.Classification, transaction_id)
        if row is None:
            row = models.Classification(transaction_id=transaction_id)
            self.session.add(row)
        for name in _CLASSIFICATION_FIELDS:
            setattr(row, name, getattr(classification, name))
        self.session.flush()

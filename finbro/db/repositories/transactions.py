"""Repozytorium transakcji i ich klasyfikacji."""

from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from finbro.db import models
from finbro.domain.money import Money
from finbro.domain.transactions import Classification, Transaction, TransactionData

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

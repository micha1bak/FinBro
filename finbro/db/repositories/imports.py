"""Repozytorium importów: zapis transakcji z deduplikacją i partie importu."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from finbro.db import models
from finbro.db.repositories.transactions import data_to_row
from finbro.domain.reference import ImportBatch
from finbro.domain.transactions import TransactionData


def _batch(row: models.ImportBatch) -> ImportBatch:
    return ImportBatch(
        id=row.id,
        account_id=row.account_id,
        filename=row.filename,
        date_from=row.date_from,
        date_to=row.date_to,
        new_count=row.new_count,
        existing_count=row.existing_count,
        skipped_count=row.skipped_count,
        created_at=row.created_at,
    )


class ImportRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create_batch(self, account_id: int, filename: str | None, date_from: date, date_to: date) -> int:
        row = models.ImportBatch(
            account_id=account_id,
            filename=filename,
            date_from=date_from,
            date_to=date_to,
            new_count=0,
            existing_count=0,
            skipped_count=0,
        )
        self.session.add(row)
        self.session.flush()
        return row.id

    def finish_batch(self, batch_id: int, new_count: int, existing_count: int, skipped_count: int) -> ImportBatch:
        row = self.session.get(models.ImportBatch, batch_id)
        assert row is not None
        row.new_count, row.existing_count, row.skipped_count = new_count, existing_count, skipped_count
        self.session.flush()
        return _batch(row)

    def insert_new(self, rows: Sequence[TransactionData]) -> list[int]:
        """Wstawia transakcje, pomijając istniejące odciski (D5). Zwraca id faktycznie dodanych."""
        if not rows:
            return []
        values = []
        for data in rows:
            row = data_to_row(data)
            values.append({c.key: getattr(row, c.key) for c in models.Transaction.__table__.columns if c.key not in ("id", "created_at")})
        stmt = (
            insert(models.Transaction)
            .values(values)
            .on_conflict_do_nothing(constraint="uq_transaction_fingerprint")
            .returning(models.Transaction.id)
        )
        return list(self.session.scalars(stmt))

    def batches(self, account_id: int | None = None) -> list[ImportBatch]:
        stmt = select(models.ImportBatch).order_by(models.ImportBatch.created_at, models.ImportBatch.id)
        if account_id is not None:
            stmt = stmt.where(models.ImportBatch.account_id == account_id)
        return [_batch(r) for r in self.session.scalars(stmt)]

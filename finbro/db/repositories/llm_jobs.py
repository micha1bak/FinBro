"""Kolejka zadań klasyfikacji modelem językowym (D9)."""

from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from finbro.db import models
from finbro.domain.enums import LlmJobStatus


class LlmJobRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def enqueue(self, transaction_ids: Iterable[int]) -> None:
        values = [{"transaction_id": tx_id, "status": LlmJobStatus.PENDING} for tx_id in transaction_ids]
        if not values:
            return
        stmt = insert(models.LlmJob).values(values)
        # Ponowne dodanie tej samej transakcji przywraca zadanie do kolejki.
        stmt = stmt.on_conflict_do_update(
            index_elements=[models.LlmJob.transaction_id],
            set_={"status": LlmJobStatus.PENDING, "attempts": 0, "last_error": None, "next_attempt_at": func.now()},
        )
        self.session.execute(stmt)

    def queued_transaction_ids(self) -> set[int]:
        stmt = select(models.LlmJob.transaction_id).where(
            models.LlmJob.status.in_([LlmJobStatus.PENDING, LlmJobStatus.RUNNING])
        )
        return set(self.session.scalars(stmt))

    def pending_count(self) -> int:
        stmt = select(func.count()).select_from(models.LlmJob).where(
            models.LlmJob.status.in_([LlmJobStatus.PENDING, LlmJobStatus.RUNNING])
        )
        return int(self.session.scalar(stmt) or 0)

    def cancel(self, transaction_id: int) -> None:
        """Usuwa zadanie, np. gdy użytkownik sklasyfikował transakcję przed modelem."""
        job = self.session.scalar(select(models.LlmJob).where(models.LlmJob.transaction_id == transaction_id))
        if job is not None:
            self.session.delete(job)
            self.session.flush()

"""Kolejka zadań klasyfikacji modelem językowym (D9)."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from finbro.db import models
from finbro.domain.enums import LlmJobStatus


@dataclass(frozen=True)
class LlmJob:
    id: int
    transaction_id: int
    status: LlmJobStatus
    attempts: int
    last_error: str | None


def _job(row: models.LlmJob) -> LlmJob:
    return LlmJob(
        id=row.id, transaction_id=row.transaction_id, status=row.status, attempts=row.attempts, last_error=row.last_error
    )


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

    def claim_next(self) -> LlmJob | None:
        """Pobiera najstarsze gotowe zadanie i oznacza je jako przetwarzane.

        ``FOR UPDATE SKIP LOCKED`` sprawia, że przypadkowy drugi worker nie weźmie tego samego zadania.
        """
        row = self.session.scalar(
            select(models.LlmJob)
            .where(models.LlmJob.status == LlmJobStatus.PENDING, models.LlmJob.next_attempt_at <= func.now())
            .order_by(models.LlmJob.id)
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        if row is None:
            return None
        row.status = LlmJobStatus.RUNNING
        row.attempts += 1
        self.session.flush()
        return _job(row)

    def get(self, job_id: int) -> LlmJob:
        row = self.session.get(models.LlmJob, job_id)
        if row is None:
            raise LookupError(f"Brak zadania {job_id}")
        return _job(row)

    def finish(self, job_id: int, status: LlmJobStatus, error: str | None = None, retry_at: datetime | None = None) -> None:
        row = self.session.get(models.LlmJob, job_id)
        if row is None:
            return  # zadanie anulowane w międzyczasie (użytkownik sklasyfikował transakcję)
        row.status = status
        row.last_error = error
        if retry_at is not None:
            row.next_attempt_at = retry_at
        self.session.flush()

    def requeue_running(self) -> int:
        """Po restarcie aplikacji zadania przerwane w trakcie wracają do kolejki."""
        result = self.session.execute(
            update(models.LlmJob).where(models.LlmJob.status == LlmJobStatus.RUNNING).values(status=LlmJobStatus.PENDING)
        )
        return result.rowcount or 0

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

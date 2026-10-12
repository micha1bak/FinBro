"""Jednostka pracy: sesja bazy i repozytoria dla jednego przypadku użycia."""

from __future__ import annotations

from functools import cached_property

from sqlalchemy.orm import Session

from finbro.db.repositories.settlements import SettlementRepository
from finbro.db.repositories.transactions import TransactionRepository


class UnitOfWork:
    """Daje serwisom dostęp do repozytoriów i zatwierdza zmiany w jednej transakcji."""

    def __init__(self, session: Session) -> None:
        self.session = session

    @cached_property
    def transactions(self) -> TransactionRepository:
        return TransactionRepository(self.session)

    @cached_property
    def settlements(self) -> SettlementRepository:
        return SettlementRepository(self.session)

    def commit(self) -> None:
        self.session.commit()

    def rollback(self) -> None:
        self.session.rollback()

    def close(self) -> None:
        self.session.close()

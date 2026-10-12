"""Jednostka pracy: sesja bazy i repozytoria dla jednego przypadku użycia."""

from __future__ import annotations

from functools import cached_property

from sqlalchemy.orm import Session

from finbro.db.repositories.imports import ImportRepository
from finbro.db.repositories.llm_jobs import LlmJobRepository
from finbro.db.repositories.reference import ReferenceRepository
from finbro.db.repositories.rules import RuleRepository
from finbro.db.repositories.settlements import SettlementRepository
from finbro.db.repositories.transactions import TransactionRepository
from finbro.db.repositories.wallet import InventoryRepository


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

    @cached_property
    def reference(self) -> ReferenceRepository:
        return ReferenceRepository(self.session)

    @cached_property
    def imports(self) -> ImportRepository:
        return ImportRepository(self.session)

    @cached_property
    def rules(self) -> RuleRepository:
        return RuleRepository(self.session)

    @cached_property
    def llm_jobs(self) -> LlmJobRepository:
        return LlmJobRepository(self.session)

    @cached_property
    def inventories(self) -> InventoryRepository:
        return InventoryRepository(self.session)

    def commit(self) -> None:
        self.session.commit()

    def rollback(self) -> None:
        self.session.rollback()

    def close(self) -> None:
        self.session.close()

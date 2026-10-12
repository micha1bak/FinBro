"""Repozytorium inwentaryzacji Portfela."""

from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from finbro.db import models
from finbro.domain.money import Money
from finbro.domain.wallet import Inventory


def _inventory(row: models.WalletInventory) -> Inventory:
    return Inventory(
        id=row.id,
        inventory_date=row.inventory_date,
        actual=Money(row.actual),
        expected=Money(row.expected),
        transaction_id=row.transaction_id,
    )


class InventoryRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, day: date, actual: Money, expected: Money, transaction_id: int | None) -> Inventory:
        row = models.WalletInventory(
            inventory_date=day, actual=actual.grosze, expected=expected.grosze, transaction_id=transaction_id
        )
        self.session.add(row)
        self.session.flush()
        return _inventory(row)

    def between(self, date_from: date, date_to: date) -> list[Inventory]:
        stmt = (
            select(models.WalletInventory)
            .where(models.WalletInventory.inventory_date.between(date_from, date_to))
            .order_by(models.WalletInventory.inventory_date, models.WalletInventory.id)
        )
        return [_inventory(r) for r in self.session.scalars(stmt)]

    def latest(self, limit: int = 10) -> list[Inventory]:
        stmt = (
            select(models.WalletInventory)
            .order_by(models.WalletInventory.inventory_date.desc(), models.WalletInventory.id.desc())
            .limit(limit)
        )
        return [_inventory(r) for r in self.session.scalars(stmt)]

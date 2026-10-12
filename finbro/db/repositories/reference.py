"""Repozytorium danych słownikowych: ustawienia, konta, kategorie, koperty, dłużnicy, plany."""

from __future__ import annotations

from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from finbro.db import models
from finbro.domain.allocation import AllocationPlan
from finbro.domain.money import Money
from finbro.domain.reference import Account, AppConfig, Category, Debtor, Envelope


def _account(row: models.Account) -> Account:
    return Account(
        id=row.id,
        code=row.code,
        name=row.name,
        kind=row.kind,
        opening_balance=Money(row.opening_balance),
        opening_date=row.opening_date,
    )


def _category(row: models.Category) -> Category:
    return Category(id=row.id, name=row.name, active=row.active, is_system=row.is_system, sort_order=row.sort_order)


def _envelope(row: models.Envelope) -> Envelope:
    return Envelope(
        id=row.id,
        code=row.code,
        name=row.name,
        target_account=row.target_account,
        is_life=row.is_life,
        sort_order=row.sort_order,
    )


def _debtor(row: models.Debtor) -> Debtor:
    aliases = tuple(line.strip() for line in (row.aliases or "").splitlines() if line.strip())
    return Debtor(id=row.id, name=row.name, aliases=aliases, note=row.note)


class ReferenceRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    # --- ustawienia ---
    def config(self) -> AppConfig:
        row = self.session.get(models.AppSettings, 1)
        if row is None:
            return AppConfig()
        return AppConfig(
            start_date=row.start_date,
            main_account_number=row.main_account_number,
            llm_model=row.llm_model,
        )

    def update_config(self, **values: object) -> AppConfig:
        row = self.session.get(models.AppSettings, 1) or models.AppSettings(id=1)
        for name, value in values.items():
            setattr(row, name, value)
        self.session.add(row)
        self.session.flush()
        return self.config()

    # --- konta ---
    def account(self, code: str) -> Account:
        row = self.session.scalar(select(models.Account).where(models.Account.code == code))
        if row is None:
            raise LookupError(f"Brak konta {code!r}")
        return _account(row)

    def set_opening_balance(self, code: str, amount: Money, on: date) -> Account:
        row = self.session.scalar(select(models.Account).where(models.Account.code == code))
        if row is None:
            raise LookupError(f"Brak konta {code!r}")
        row.opening_balance = amount.grosze
        row.opening_date = on
        self.session.flush()
        return _account(row)

    # --- kategorie ---
    def categories(self, active_only: bool = False) -> list[Category]:
        stmt = select(models.Category).order_by(models.Category.sort_order, models.Category.name)
        if active_only:
            stmt = stmt.where(models.Category.active)
        return [_category(r) for r in self.session.scalars(stmt)]

    def system_category(self) -> Category:
        row = self.session.scalar(select(models.Category).where(models.Category.is_system))
        if row is None:
            raise LookupError("Brak kategorii systemowej")
        return _category(row)

    # --- koperty i plany ---
    def envelopes(self) -> list[Envelope]:
        rows = self.session.scalars(select(models.Envelope).order_by(models.Envelope.sort_order, models.Envelope.id))
        return [_envelope(r) for r in rows]

    def plans(self) -> list[AllocationPlan[int]]:
        life = self.session.scalar(select(models.Envelope.id).where(models.Envelope.is_life))
        rows = self.session.scalars(
            select(models.AllocationPlan)
            .options(selectinload(models.AllocationPlan.shares))
            .order_by(models.AllocationPlan.effective_from)
        )
        return [
            AllocationPlan(
                effective_from=row.effective_from,
                shares={s.envelope_id: s.basis_points for s in row.shares},
                life=life,
                id=row.id,
            )
            for row in rows
        ]

    # --- dłużnicy ---
    def debtors(self) -> list[Debtor]:
        return [_debtor(r) for r in self.session.scalars(select(models.Debtor).order_by(models.Debtor.name))]

    def debtor(self, debtor_id: int) -> Debtor:
        row = self.session.get(models.Debtor, debtor_id)
        if row is None:
            raise LookupError(f"Brak dłużnika {debtor_id}")
        return _debtor(row)

    def debtor_by_name(self, name: str) -> Debtor | None:
        row = self.session.scalar(select(models.Debtor).where(func.lower(models.Debtor.name) == name.strip().lower()))
        return _debtor(row) if row is not None else None

    def add_debtor(self, name: str) -> Debtor:
        row = models.Debtor(name=name)
        self.session.add(row)
        self.session.flush()
        return _debtor(row)

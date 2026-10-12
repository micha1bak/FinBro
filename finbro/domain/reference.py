"""Dane słownikowe i ustawienia jako obiekty domenowe."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from finbro.domain.enums import AccountKind
from finbro.domain.money import Money


@dataclass(frozen=True)
class AppConfig:
    start_date: date | None = None
    main_account_number: str | None = None
    llm_model: str | None = None


@dataclass(frozen=True)
class Account:
    id: int
    code: str
    name: str
    kind: AccountKind
    opening_balance: Money
    opening_date: date | None


@dataclass(frozen=True)
class Category:
    id: int
    name: str
    active: bool
    is_system: bool
    sort_order: int


@dataclass(frozen=True)
class Envelope:
    id: int
    code: str
    name: str
    target_account: str | None
    is_life: bool
    sort_order: int


@dataclass(frozen=True)
class Debtor:
    id: int
    name: str
    aliases: tuple[str, ...] = ()
    note: str | None = None

    @property
    def names(self) -> tuple[str, ...]:
        """Wszystkie nazwy, pod którymi dłużnik może występować w banku."""
        return (self.name, *self.aliases)


@dataclass(frozen=True)
class ImportBatch:
    id: int
    account_id: int
    filename: str | None
    date_from: date
    date_to: date
    new_count: int
    existing_count: int
    skipped_count: int
    created_at: datetime | None = None

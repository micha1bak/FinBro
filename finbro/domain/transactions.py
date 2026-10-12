"""Transakcje i ich klasyfikacja jako zwykłe obiekty domenowe."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import StrEnum

from finbro.domain.enums import ProposalSource, TransferKind, TxSource, TxType
from finbro.domain.money import Money


class Direction(StrEnum):
    IN = "IN"  # wpływ
    OUT = "OUT"  # wydatek (obciążenie)

    @property
    def label(self) -> str:
        return "wpływ" if self is Direction.IN else "wydatek"

    @classmethod
    def of(cls, amount: Money) -> Direction:
        """Kierunek wynika wyłącznie ze znaku kwoty."""
        return cls.IN if amount.grosze > 0 else cls.OUT


@dataclass(frozen=True)
class TransactionData:
    """Dane transakcji przed zapisem (z importu albo z ręcznego wpisu)."""

    source: TxSource
    transaction_date: date
    amount: Money
    account_id: int | None = None
    booking_date: date | None = None
    balance_after: Money | None = None
    occurrence: int | None = None
    bank_type: str | None = None
    raw_description: str | None = None
    counterparty_name: str | None = None
    counterparty_account: str | None = None
    counterparty_address: str | None = None
    title: str | None = None
    merchant: str | None = None
    city: str | None = None
    country: str | None = None
    reference_number: str | None = None
    extra: Mapping[str, str] = field(default_factory=dict)
    note: str | None = None
    import_batch_id: int | None = None

    @property
    def direction(self) -> Direction:
        return Direction.of(self.amount)


@dataclass(frozen=True)
class Classification:
    """Klasyfikacja transakcji: propozycja albo decyzja ostateczna (``confirmed``)."""

    type: TxType | None = None
    category_id: int | None = None
    debtor_id: int | None = None
    transfer_kind: TransferKind | None = None
    envelope_id: int | None = None
    source: ProposalSource | None = None
    rule_id: int | None = None
    reason: str | None = None
    confirmed: bool = False
    confirmed_at: datetime | None = None
    settlement_week: date | None = None

    @property
    def is_final(self) -> bool:
        return self.confirmed and self.type is not None


@dataclass(frozen=True)
class Transaction:
    """Zapisana transakcja wraz z klasyfikacją."""

    id: int
    data: TransactionData
    classification: Classification = field(default_factory=Classification)

    @property
    def amount(self) -> Money:
        return self.data.amount

    @property
    def transaction_date(self) -> date:
        return self.data.transaction_date

    @property
    def direction(self) -> Direction:
        return self.data.direction

    @property
    def counterparty(self) -> str | None:
        """Nazwa kontrahenta albo sprzedawcy do wyświetlenia i grupowania."""
        return self.data.counterparty_name or self.data.merchant

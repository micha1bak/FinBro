"""Modele SQLAlchemy (D6) z konwencjami PostgreSQL z D11.

Kwoty w groszach jako BIGINT, daty transakcji jako DATE, znaczniki czasu jako
TIMESTAMPTZ, wyliczenia jako VARCHAR z ograniczeniem CHECK.
"""

from __future__ import annotations

import enum
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from finbro.domain.enums import (
    AccountKind,
    LlmJobStatus,
    ProposalSource,
    SettlementStatus,
    TransferKind,
    TxSource,
    TxType,
)

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def str_enum[E: enum.Enum](enum_cls: type[E], name: str) -> Enum:
    """VARCHAR + CHECK zamiast natywnego typu ENUM PostgreSQL (D11)."""
    return Enum(
        enum_cls,
        name=name,
        native_enum=False,
        create_constraint=True,
        length=20,
        values_callable=lambda members: [m.value for m in members],
        validate_strings=True,
    )


def created_at_column() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class AppSettings(Base):
    """Ustawienia aplikacji: jeden wiersz o id = 1."""

    __tablename__ = "app_settings"
    __table_args__ = (CheckConstraint("id = 1", name="single_row"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    start_date: Mapped[date | None] = mapped_column(Date)
    main_account_number: Mapped[str | None] = mapped_column(String(64))
    llm_model: Mapped[str | None] = mapped_column(String(200))


class Account(Base):
    __tablename__ = "account"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True)
    name: Mapped[str] = mapped_column(String(100))
    kind: Mapped[AccountKind] = mapped_column(str_enum(AccountKind, "account_kind"))
    opening_balance: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0")
    opening_date: Mapped[date | None] = mapped_column(Date)

    def __str__(self) -> str:
        return self.name


class Category(Base):
    __tablename__ = "category"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))
    is_system: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    sort_order: Mapped[int] = mapped_column(Integer, default=100, server_default="100")

    def __str__(self) -> str:
        return self.name


class Debtor(Base):
    __tablename__ = "debtor"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    # Dodatkowe nazwy kontrahenta w banku (po jednej w linii), np. pełne imię i nazwisko z przelewu.
    aliases: Mapped[str | None] = mapped_column(Text)
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = created_at_column()

    def __str__(self) -> str:
        return self.name


class Envelope(Base):
    __tablename__ = "envelope"
    __table_args__ = (
        # Dokładnie jedna koperta może być Życiem.
        Index("uq_envelope_single_life", "is_life", unique=True, postgresql_where=text("is_life")),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True)
    name: Mapped[str] = mapped_column(String(50), unique=True)
    target_account: Mapped[str | None] = mapped_column(String(64))
    is_life: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    sort_order: Mapped[int] = mapped_column(Integer, default=100, server_default="100")

    def __str__(self) -> str:
        return self.name


class AllocationPlan(Base):
    __tablename__ = "allocation_plan"

    id: Mapped[int] = mapped_column(primary_key=True)
    effective_from: Mapped[date] = mapped_column(Date, unique=True)
    created_at: Mapped[datetime] = created_at_column()

    shares: Mapped[list[AllocationShare]] = relationship(
        back_populates="plan", cascade="all, delete-orphan", order_by="AllocationShare.envelope_id"
    )

    def __str__(self) -> str:
        return f"od {self.effective_from.isoformat()}"


class AllocationShare(Base):
    __tablename__ = "allocation_share"
    __table_args__ = (CheckConstraint("basis_points BETWEEN 0 AND 10000", name="basis_points_range"),)

    plan_id: Mapped[int] = mapped_column(ForeignKey("allocation_plan.id", ondelete="CASCADE"), primary_key=True)
    envelope_id: Mapped[int] = mapped_column(ForeignKey("envelope.id"), primary_key=True)
    basis_points: Mapped[int] = mapped_column(Integer)

    plan: Mapped[AllocationPlan] = relationship(back_populates="shares")
    envelope: Mapped[Envelope] = relationship()


class Rule(Base):
    __tablename__ = "rule"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    priority: Mapped[int] = mapped_column(Integer, default=100, server_default="100")
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))
    conditions: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default=text("'{}'::jsonb"))
    result_type: Mapped[TxType] = mapped_column(str_enum(TxType, "rule_result_type"))
    result_category_id: Mapped[int | None] = mapped_column(ForeignKey("category.id"))
    result_debtor_id: Mapped[int | None] = mapped_column(ForeignKey("debtor.id"))
    result_transfer_kind: Mapped[TransferKind | None] = mapped_column(
        str_enum(TransferKind, "rule_result_transfer_kind")
    )
    created_at: Mapped[datetime] = created_at_column()

    result_category: Mapped[Category | None] = relationship()
    result_debtor: Mapped[Debtor | None] = relationship()

    def __str__(self) -> str:
        return self.name


class ImportBatch(Base):
    __tablename__ = "import_batch"

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("account.id"))
    filename: Mapped[str | None] = mapped_column(String(255))
    date_from: Mapped[date] = mapped_column(Date)
    date_to: Mapped[date] = mapped_column(Date)
    new_count: Mapped[int] = mapped_column(Integer)
    existing_count: Mapped[int] = mapped_column(Integer)
    skipped_count: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = created_at_column()


class Transaction(Base):
    __tablename__ = "transaction"
    __table_args__ = (
        # Odcisk importu (D5). Wiersze spoza importu mają NULL w saldzie i numerze wystąpienia,
        # więc ograniczenie ich nie dotyczy.
        UniqueConstraint(
            "account_id", "booking_date", "amount", "balance_after", "occurrence", name="uq_transaction_fingerprint"
        ),
        CheckConstraint("amount <> 0", name="amount_not_zero"),
        Index("ix_transaction_transaction_date", "transaction_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int | None] = mapped_column(ForeignKey("account.id"))
    source: Mapped[TxSource] = mapped_column(str_enum(TxSource, "tx_source"))
    transaction_date: Mapped[date] = mapped_column(Date)
    booking_date: Mapped[date | None] = mapped_column(Date)
    amount: Mapped[int] = mapped_column(BigInteger)
    balance_after: Mapped[int | None] = mapped_column(BigInteger)
    occurrence: Mapped[int | None] = mapped_column(Integer)
    bank_type: Mapped[str | None] = mapped_column(String(200))
    raw_description: Mapped[str | None] = mapped_column(Text)
    counterparty_name: Mapped[str | None] = mapped_column(String(300))
    counterparty_account: Mapped[str | None] = mapped_column(String(64))
    counterparty_address: Mapped[str | None] = mapped_column(String(300))
    title: Mapped[str | None] = mapped_column(Text)
    merchant: Mapped[str | None] = mapped_column(String(300))
    city: Mapped[str | None] = mapped_column(String(100))
    country: Mapped[str | None] = mapped_column(String(100))
    reference_number: Mapped[str | None] = mapped_column(String(100))
    # Pozostałe pola opisu (np. numer telefonu, oryginalna kwota) i identyfikator operacji kartowej.
    extra: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default=text("'{}'::jsonb"))
    note: Mapped[str | None] = mapped_column(Text)
    import_batch_id: Mapped[int | None] = mapped_column(ForeignKey("import_batch.id"))
    created_at: Mapped[datetime] = created_at_column()

    account: Mapped[Account | None] = relationship()
    classification: Mapped[Classification | None] = relationship(
        back_populates="transaction", uselist=False, cascade="all, delete-orphan"
    )


class Classification(Base):
    __tablename__ = "classification"
    __table_args__ = (
        CheckConstraint("NOT confirmed OR type IS NOT NULL", name="confirmed_has_type"),
        Index("ix_classification_settlement_week", "settlement_week"),
    )

    transaction_id: Mapped[int] = mapped_column(
        ForeignKey("transaction.id", ondelete="CASCADE"), primary_key=True
    )
    type: Mapped[TxType | None] = mapped_column(str_enum(TxType, "classification_type"))
    category_id: Mapped[int | None] = mapped_column(ForeignKey("category.id"))
    debtor_id: Mapped[int | None] = mapped_column(ForeignKey("debtor.id"))
    transfer_kind: Mapped[TransferKind | None] = mapped_column(
        str_enum(TransferKind, "classification_transfer_kind")
    )
    envelope_id: Mapped[int | None] = mapped_column(ForeignKey("envelope.id"))
    source: Mapped[ProposalSource | None] = mapped_column(str_enum(ProposalSource, "proposal_source"))
    rule_id: Mapped[int | None] = mapped_column(ForeignKey("rule.id", ondelete="SET NULL"))
    reason: Mapped[str | None] = mapped_column(Text)
    confirmed: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Dla dochodów: poniedziałek tygodnia, w którego rozliczeniu dochód jest dzielony (D7).
    settlement_week: Mapped[date | None] = mapped_column(Date)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    transaction: Mapped[Transaction] = relationship(back_populates="classification")
    category: Mapped[Category | None] = relationship()
    debtor: Mapped[Debtor | None] = relationship()


class Settlement(Base):
    __tablename__ = "settlement"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Poniedziałek tygodnia ISO; rok i numer tygodnia wynikają z tej daty.
    week_start: Mapped[date] = mapped_column(Date, unique=True)
    status: Mapped[SettlementStatus] = mapped_column(
        str_enum(SettlementStatus, "settlement_status"), default=SettlementStatus.OPEN
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    lines: Mapped[list[SettlementLine]] = relationship(
        back_populates="settlement", cascade="all, delete-orphan", order_by="SettlementLine.envelope_id"
    )


class SettlementLine(Base):
    __tablename__ = "settlement_line"
    __table_args__ = (UniqueConstraint("settlement_id", "envelope_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    settlement_id: Mapped[int] = mapped_column(ForeignKey("settlement.id", ondelete="CASCADE"))
    envelope_id: Mapped[int] = mapped_column(ForeignKey("envelope.id"))
    due: Mapped[int] = mapped_column(BigInteger)
    corrections: Mapped[int] = mapped_column(BigInteger)
    carryover: Mapped[int] = mapped_column(BigInteger)
    to_transfer: Mapped[int] = mapped_column(BigInteger)

    settlement: Mapped[Settlement] = relationship(back_populates="lines")
    envelope: Mapped[Envelope] = relationship()


class SettlementAdjustment(Base):
    """Ujemna korekta po wycofaniu dochodu z zamkniętego tygodnia (D7)."""

    __tablename__ = "settlement_adjustment"

    id: Mapped[int] = mapped_column(primary_key=True)
    week_start: Mapped[date] = mapped_column(Date, index=True)
    transaction_id: Mapped[int] = mapped_column(ForeignKey("transaction.id", ondelete="CASCADE"))
    amount: Mapped[int] = mapped_column(BigInteger)
    # Data dochodu wyznacza plan podziału korekty.
    income_date: Mapped[date] = mapped_column(Date)
    created_at: Mapped[datetime] = created_at_column()


class SettlementPayment(Base):
    """Przypisanie przelewu ODKŁADANIE do linii rozliczenia."""

    __tablename__ = "settlement_payment"

    id: Mapped[int] = mapped_column(primary_key=True)
    settlement_line_id: Mapped[int] = mapped_column(ForeignKey("settlement_line.id", ondelete="CASCADE"))
    transaction_id: Mapped[int] = mapped_column(ForeignKey("transaction.id", ondelete="CASCADE"), unique=True)
    amount: Mapped[int] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = created_at_column()


class WalletInventory(Base):
    __tablename__ = "wallet_inventory"

    id: Mapped[int] = mapped_column(primary_key=True)
    inventory_date: Mapped[date] = mapped_column(Date, index=True)
    actual: Mapped[int] = mapped_column(BigInteger)
    expected: Mapped[int] = mapped_column(BigInteger)
    transaction_id: Mapped[int | None] = mapped_column(ForeignKey("transaction.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = created_at_column()


class LlmJob(Base):
    __tablename__ = "llm_job"

    id: Mapped[int] = mapped_column(primary_key=True)
    transaction_id: Mapped[int] = mapped_column(ForeignKey("transaction.id", ondelete="CASCADE"), unique=True)
    status: Mapped[LlmJobStatus] = mapped_column(
        str_enum(LlmJobStatus, "llm_job_status"), default=LlmJobStatus.PENDING
    )
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    last_error: Mapped[str | None] = mapped_column(Text)
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

"""Modele SQLAlchemy (D2). Kwoty w groszach, udziały planu w punktach bazowych."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    MetaData,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from finbro.domain.envelopes import NET_WORTH_ACCOUNTS, TRANSFER_ENVELOPES, Envelope

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def one_of(column: str, values: tuple[Envelope, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v.value) for v in values)})"


class AllocationPlan(Base):
    """Plan podziału obowiązujący od ``effective_from`` do dnia przed następnym planem."""

    __tablename__ = "allocation_plan"
    __table_args__ = (
        CheckConstraint("pko + wakacje + xtb + obligacje = 10000", name="shares_sum_100"),
        CheckConstraint("pko >= 0 AND wakacje >= 0 AND xtb >= 0 AND obligacje >= 0", name="shares_non_negative"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    effective_from: Mapped[date] = mapped_column(Date, unique=True)
    pko: Mapped[int] = mapped_column(Integer)
    wakacje: Mapped[int] = mapped_column(Integer)
    xtb: Mapped[int] = mapped_column(Integer)
    obligacje: Mapped[int] = mapped_column(Integer)


class Settlement(Base):
    __tablename__ = "settlement"

    id: Mapped[int] = mapped_column(primary_key=True)
    date: Mapped[date] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SettlementLine(Base):
    __tablename__ = "settlement_line"
    __table_args__ = (
        CheckConstraint(one_of("envelope", TRANSFER_ENVELOPES), name="envelope"),
        CheckConstraint("amount > 0", name="amount_positive"),
    )

    settlement_id: Mapped[int] = mapped_column(ForeignKey("settlement.id", ondelete="CASCADE"), primary_key=True)
    envelope: Mapped[str] = mapped_column(String(20), primary_key=True)
    amount: Mapped[int] = mapped_column(BigInteger)


class Income(Base):
    __tablename__ = "income"
    __table_args__ = (
        CheckConstraint("amount > 0", name="amount_positive"),
        CheckConstraint("length(trim(source)) > 0", name="source_not_empty"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    date: Mapped[date] = mapped_column(Date, index=True)
    source: Mapped[str] = mapped_column(String(200))
    amount: Mapped[int] = mapped_column(BigInteger)
    settlement_id: Mapped[int | None] = mapped_column(ForeignKey("settlement.id", ondelete="SET NULL"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class IncomeShare(Base):
    """Podział dochodu zamrożony w chwili rozliczenia; znika razem z cofniętym rozliczeniem."""

    __tablename__ = "income_share"
    __table_args__ = (CheckConstraint(one_of("envelope", tuple(Envelope)), name="envelope"),)

    income_id: Mapped[int] = mapped_column(ForeignKey("income.id", ondelete="CASCADE"), primary_key=True)
    envelope: Mapped[str] = mapped_column(String(20), primary_key=True)
    settlement_id: Mapped[int] = mapped_column(ForeignKey("settlement.id", ondelete="CASCADE"), index=True)
    amount: Mapped[int] = mapped_column(BigInteger)


class EnvelopeAccount(Base):
    """Rachunek docelowy koperty przelewanej poza konto główne."""

    __tablename__ = "envelope_account"
    __table_args__ = (CheckConstraint(one_of("envelope", TRANSFER_ENVELOPES), name="envelope"),)

    envelope: Mapped[str] = mapped_column(String(20), primary_key=True)
    target_account: Mapped[str] = mapped_column(String(64))


class BalanceEntry(Base):
    """Saldo faktyczne konta na dany dzień."""

    __tablename__ = "balance_entry"
    __table_args__ = (
        UniqueConstraint("account", "date"),
        CheckConstraint(one_of("account", NET_WORTH_ACCOUNTS), name="account"),
        CheckConstraint("amount >= 0", name="amount_non_negative"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    account: Mapped[str] = mapped_column(String(20))
    date: Mapped[date] = mapped_column(Date)
    amount: Mapped[int] = mapped_column(BigInteger)

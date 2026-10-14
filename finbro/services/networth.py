"""Majątek: wpisy sald faktycznych i odczyt sald, różnic i osi czasu z bazy."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from finbro.db.models import BalanceEntry as BalanceRow
from finbro.db.models import Settlement, SettlementLine
from finbro.domain.envelopes import Envelope
from finbro.domain.money import Money
from finbro.domain.networth import (
    FED_ENVELOPES,
    Account,
    BalanceEntry,
    Contribution,
    Snapshot,
    difference,
    snapshot,
    timeline,
)


class NetWorthError(ValueError):
    """Niepoprawny wpis salda (komunikat dla użytkownika)."""


@dataclass(frozen=True)
class EntryView:
    entry: BalanceEntry
    difference: Money | None  # tylko XTB i Obligacje (konta wyliczane)


@dataclass(frozen=True)
class Overview:
    current: Snapshot
    last_update: date | None
    timeline: list[Snapshot]
    entries: list[EntryView]  # od najnowszych

    @property
    def is_empty(self) -> bool:
        return self.last_update is None


class NetWorthService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def entries(self) -> list[BalanceEntry]:
        rows = self.session.scalars(select(BalanceRow).order_by(BalanceRow.date, BalanceRow.account))
        return [BalanceEntry(Account(r.account), r.date, Money(r.amount)) for r in rows]

    def contributions(self) -> list[Contribution]:
        rows = self.session.execute(
            select(SettlementLine.envelope, Settlement.date, SettlementLine.amount).join(
                Settlement, Settlement.id == SettlementLine.settlement_id
            )
        ).all()
        return [Contribution(Envelope(envelope), day, Money(amount)) for envelope, day, amount in rows]

    def record(self, account: Account, day: date, amount: Money) -> EntryView:
        """Zapisuje saldo faktyczne; wpis z tego samego dnia zastępuje poprzedni."""
        if amount.is_negative:
            raise NetWorthError("Saldo nie może być ujemne.")
        row = self.session.scalar(select(BalanceRow).where(BalanceRow.account == account.value, BalanceRow.date == day))
        if row is None:
            self.session.add(BalanceRow(account=account.value, date=day, amount=amount.grosze))
        else:
            row.amount = amount.grosze
        self.session.commit()
        entry = BalanceEntry(account, day, amount)
        return EntryView(entry, difference(entry, self.entries(), self.contributions()))

    def overview(self, day: date) -> Overview:
        """Przegląd majątku; saldo bieżące na ``day`` albo na dzień najpóźniejszego wpisu, jeśli późniejszy."""
        entries, contributions = self.entries(), self.contributions()
        relevant = [c for c in contributions if c.envelope in FED_ENVELOPES]
        last_update = max([e.date for e in entries] + [c.date for c in relevant], default=None)
        return Overview(
            current=snapshot(entries, contributions, max(day, last_update) if last_update else day),
            last_update=last_update,
            timeline=timeline(entries, contributions),
            entries=[EntryView(e, difference(e, entries, contributions)) for e in reversed(entries)],
        )

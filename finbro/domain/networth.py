"""Majątek (D7): salda kont PKO, Gotówka, XTB i Obligacje z sald faktycznych i rozliczonych przelewów.

XTB i Obligacje: ostatnie saldo faktyczne z danego dnia lub wcześniejsze plus rozliczenia
z datą późniejszą niż to saldo, a nie późniejszą niż dany dzień. PKO i Gotówka: tylko saldo
faktyczne, bo zmieniają je wydatki, których aplikacja nie zna. Wakacje nie wchodzą do majątku.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date
from enum import StrEnum

from finbro.domain.envelopes import Envelope
from finbro.domain.money import Money


class Account(StrEnum):
    PKO = "PKO"
    GOTOWKA = "GOTOWKA"
    XTB = "XTB"
    OBLIGACJE = "OBLIGACJE"

    @property
    def label(self) -> str:
        return {"PKO": "PKO", "GOTOWKA": "Gotówka", "XTB": "XTB", "OBLIGACJE": "Obligacje"}[self.value]

    @property
    def envelope(self) -> Envelope | None:
        """Koperta, której rozliczenia zwiększają saldo; ``None`` dla kont tylko ręcznych."""
        return {Account.XTB: Envelope.XTB, Account.OBLIGACJE: Envelope.OBLIGACJE}.get(self)

    @property
    def manual_only(self) -> bool:
        return self.envelope is None


FED_ENVELOPES = frozenset(a.envelope for a in Account if a.envelope is not None)


@dataclass(frozen=True)
class BalanceEntry:
    """Saldo faktyczne konta na dzień."""

    account: Account
    date: date
    amount: Money


@dataclass(frozen=True)
class Contribution:
    """Rozliczony przelew na kopertę."""

    envelope: Envelope
    date: date
    amount: Money


def balance(
    account: Account, entries: Iterable[BalanceEntry], contributions: Iterable[Contribution], day: date
) -> Money | None:
    """Saldo konta na dzień; ``None``, gdy nic o nim nie wiadomo."""
    own = [e for e in entries if e.account is account and e.date <= day]
    last = max(own, key=lambda e: e.date, default=None)
    if account.manual_only:
        return last.amount if last else None
    after = [c for c in contributions if c.envelope is account.envelope and c.date <= day and (last is None or c.date > last.date)]
    if last is None and not after:
        return None
    base = last.amount if last else Money.zero()
    return base + sum((c.amount for c in after), Money.zero())


def difference(
    entry: BalanceEntry, entries: Iterable[BalanceEntry], contributions: Iterable[Contribution]
) -> Money | None:
    """Saldo faktyczne minus saldo wyliczone na jego dzień bez niego (zysk > 0, strata < 0).

    Dla kont tylko ręcznych różnicy nie ma (``None``).
    """
    if entry.account.manual_only:
        return None
    others = [e for e in entries if not (e.account is entry.account and e.date == entry.date)]
    computed = balance(entry.account, others, contributions, entry.date)
    return None if computed is None else entry.amount - computed


@dataclass(frozen=True)
class Snapshot:
    day: date
    balances: dict[Account, Money | None]

    @property
    def total(self) -> Money:
        return sum((b for b in self.balances.values() if b is not None), Money.zero())


def snapshot(entries: Sequence[BalanceEntry], contributions: Sequence[Contribution], day: date) -> Snapshot:
    return Snapshot(day, {a: balance(a, entries, contributions, day) for a in Account})


def timeline(entries: Sequence[BalanceEntry], contributions: Sequence[Contribution]) -> list[Snapshot]:
    """Majątek w dniach wpisów sald i rozliczeń (punkty wykresu), od najstarszego."""
    days = sorted({e.date for e in entries} | {c.date for c in contributions if c.envelope in FED_ENVELOPES})
    return [snapshot(entries, contributions, d) for d in days]

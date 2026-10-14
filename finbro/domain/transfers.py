"""Przelewy na koperty dla nierozliczonych dochodów (zbiorczo, jedna lista)."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date

from finbro.domain.allocation import Split, total
from finbro.domain.envelopes import TRANSFER_ENVELOPES, Envelope
from finbro.domain.money import Money


@dataclass(frozen=True)
class Transfer:
    envelope: Envelope
    amount: Money
    title: str


def transfer_title(envelope: Envelope, day: date) -> str:
    return f"FinBro {envelope.label} {day.isoformat()}"


def transfers(splits: Iterable[Split], day: date) -> list[Transfer]:
    """Przelewy na Wakacje, XTB i Obligacje; PKO zostaje na koncie głównym, zera pomijamy."""
    sums = total(splits)
    return [
        Transfer(envelope, sums[envelope], transfer_title(envelope, day))
        for envelope in TRANSFER_ENVELOPES
        if sums[envelope].is_positive
    ]

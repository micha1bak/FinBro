"""Stałe koperty (D3): PKO (Życie), Wakacje, XTB i Obligacje."""

from __future__ import annotations

from enum import StrEnum


class Envelope(StrEnum):
    PKO = "PKO"
    WAKACJE = "WAKACJE"
    XTB = "XTB"
    OBLIGACJE = "OBLIGACJE"

    @property
    def label(self) -> str:
        return LABELS[self]

    @property
    def is_transfer(self) -> bool:
        """Czy część dochodu jest przelewana na inny rachunek (PKO zostaje na koncie głównym)."""
        return self is not Envelope.PKO


LABELS = {
    Envelope.PKO: "PKO",
    Envelope.WAKACJE: "Wakacje",
    Envelope.XTB: "XTB",
    Envelope.OBLIGACJE: "Obligacje",
}

TRANSFER_ENVELOPES = tuple(e for e in Envelope if e.is_transfer)

"""Wyliczenia wspólne dla domeny i bazy (w bazie jako VARCHAR + CHECK)."""

from __future__ import annotations

from enum import StrEnum


class TxType(StrEnum):
    """Typ transakcji. Wartości bez polskich znaków, etykiety z nimi."""

    DOCHOD = "DOCHOD"
    WYDATEK = "WYDATEK"
    ODKLADANIE = "ODKLADANIE"
    TRANSFER = "TRANSFER"
    ZWROT = "ZWROT"
    ROZLICZENIE = "ROZLICZENIE"
    POZYCZKA = "POZYCZKA"
    SPLATA = "SPLATA"

    @property
    def label(self) -> str:
        return _TX_TYPE_LABELS[self]


_TX_TYPE_LABELS = {
    TxType.DOCHOD: "DOCHÓD",
    TxType.WYDATEK: "WYDATEK",
    TxType.ODKLADANIE: "ODKŁADANIE",
    TxType.TRANSFER: "TRANSFER",
    TxType.ZWROT: "ZWROT",
    TxType.ROZLICZENIE: "ROZLICZENIE",
    TxType.POZYCZKA: "POŻYCZKA",
    TxType.SPLATA: "SPŁATA",
}


class TransferKind(StrEnum):
    """Rodzaj transferu własnego."""

    WALLET = "WALLET"  # wypłata z bankomatu / wpłata gotówki: zmienia stan Portfela
    FAMILY = "FAMILY"  # budżet rodzinny (doładowania Revoluta, refundacje)
    OTHER = "OTHER"  # inny transfer neutralny, np. korekta stanu Portfela

    @property
    def label(self) -> str:
        return {"WALLET": "Portfel", "FAMILY": "budżet rodzinny", "OTHER": "inny / korekta"}[self.value]


class ProposalSource(StrEnum):
    RULE = "RULE"
    HISTORY = "HISTORY"
    LLM = "LLM"
    USER = "USER"
    SYSTEM = "SYSTEM"  # wpisy tworzone przez FinBro: inwentaryzacja, darowanie, przelewy FinBro

    @property
    def label(self) -> str:
        return {
            "RULE": "reguła",
            "HISTORY": "historia",
            "LLM": "model językowy",
            "USER": "użytkownik",
            "SYSTEM": "FinBro",
        }[self.value]


class TxSource(StrEnum):
    """Pochodzenie transakcji."""

    IMPORT = "IMPORT"
    MANUAL = "MANUAL"
    INVENTORY = "INVENTORY"
    FORGIVENESS = "FORGIVENESS"


class AccountKind(StrEnum):
    BANK = "BANK"
    CASH = "CASH"


class SettlementStatus(StrEnum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"
    SETTLED = "SETTLED"

    @property
    def label(self) -> str:
        return {"OPEN": "otwarte", "CLOSED": "zamknięte", "SETTLED": "rozliczone"}[self.value]


class LlmJobStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    DONE = "DONE"
    FAILED = "FAILED"

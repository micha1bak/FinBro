"""Ustawienia: rachunki docelowe kopert przelewanych poza konto główne."""

from __future__ import annotations

from collections.abc import Mapping

from sqlalchemy import select
from sqlalchemy.orm import Session

from finbro.db.models import EnvelopeAccount
from finbro.domain.envelopes import TRANSFER_ENVELOPES, Envelope

MAX_ACCOUNT_LENGTH = 64


class SettingsError(ValueError):
    """Niepoprawne ustawienie (komunikat dla użytkownika)."""


class SettingsService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def accounts(self) -> dict[Envelope, str]:
        return {Envelope(r.envelope): r.target_account for r in self.session.scalars(select(EnvelopeAccount))}

    def save_accounts(self, accounts: Mapping[Envelope, str]) -> None:
        """Zapisuje rachunki; puste pole usuwa rachunek koperty."""
        cleaned = {}
        for envelope, text in accounts.items():
            if envelope not in TRANSFER_ENVELOPES:
                raise SettingsError(f"Koperta {envelope.label} nie ma rachunku docelowego.")
            value = " ".join(text.split())
            if len(value) > MAX_ACCOUNT_LENGTH:
                raise SettingsError(f"Rachunek {envelope.label} może mieć najwyżej {MAX_ACCOUNT_LENGTH} znaki.")
            cleaned[envelope] = value
        for envelope, value in cleaned.items():
            row = self.session.get(EnvelopeAccount, envelope.value)
            if not value:
                if row is not None:
                    self.session.delete(row)
            elif row is None:
                self.session.add(EnvelopeAccount(envelope=envelope.value, target_account=value))
            else:
                row.target_account = value
        self.session.commit()

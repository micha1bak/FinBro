"""Widok transakcji dla modelu językowego z minimalizacją danych (D10).

Do modelu trafiają wyłącznie: typ operacji bankowej, kierunek, kwota, data, nazwa
kontrahenta lub sprzedawcy i tytuł. Nigdy numery rachunków, telefonów, kart ani salda.
Z tytułu i nazwy wycinamy ciągi cyfr wyglądające na takie numery.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass

from finbro.domain.transactions import Transaction

REDACTED = "[usunięto]"
# Ciąg cyfr (także z gwiazdkami maski), który może zawierać spacje, myślniki i prefiks kraju lub "+".
_NUMBER_RUN = re.compile(r"(?:\b[A-Z]{2}\s?)?\+?[\d*](?:[\d*]|[\s\-](?=[\d*]))*")
MIN_SENSITIVE_DIGITS = 9


def redact_numbers(text: str | None) -> str | None:
    """Usuwa ciągi co najmniej 9 cyfr (rachunki, karty, telefony, numery referencyjne)."""
    if not text:
        return text

    def replace(match: re.Match[str]) -> str:
        run = match.group(0)
        digits = sum(ch.isdigit() or ch == "*" for ch in run)
        return REDACTED if digits >= MIN_SENSITIVE_DIGITS else run

    return " ".join(_NUMBER_RUN.sub(replace, text).split())


@dataclass(frozen=True)
class TxView:
    bank_type: str | None
    direction: str
    amount: str
    date: str
    counterparty: str | None
    title: str | None

    def as_dict(self) -> dict[str, str | None]:
        return asdict(self)


def build_view(tx: Transaction) -> TxView:
    data = tx.data
    return TxView(
        bank_type=data.bank_type,
        direction=tx.direction.label,
        amount=abs(tx.amount).format(),
        date=tx.transaction_date.isoformat(),
        counterparty=redact_numbers(data.counterparty_name or data.merchant),
        title=redact_numbers(data.title),
    )

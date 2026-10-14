"""Plan podziału i podział dochodu na koperty (D4), jak w arkuszu „Kalk2”.

Wakacje, XTB i Obligacje: ``kwota × udział`` zaokrąglone do pełnych złotych, połówki w górę
(jak ``ROUND(x;0)`` w Excelu). PKO dostaje resztę, więc suma podziału równa się kwocie.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date

from finbro.domain.envelopes import TRANSFER_ENVELOPES, Envelope
from finbro.domain.money import Money

FULL = 10_000  # 100% w punktach bazowych
_PERCENT_RE = re.compile(r"^(?P<int>\d{1,3})(?:[.,](?P<frac>\d{1,2}))?$")

Split = dict[Envelope, Money]


class PlanError(ValueError):
    """Niepoprawny plan podziału."""


def parse_percent(text: str) -> int:
    """``"12,5"`` -> 1250 punktów bazowych."""
    match = _PERCENT_RE.match(text.strip().removesuffix("%").strip())
    if match is None:
        raise PlanError(f"Niepoprawny udział: {text!r}. Podaj procent, np. 12,5.")
    return int(match["int"]) * 100 + int((match["frac"] or "").ljust(2, "0") or "0")


def format_percent(basis_points: int) -> str:
    whole, frac = divmod(basis_points, 100)
    return f"{whole}%" if frac == 0 else f"{whole},{frac:02d}".rstrip("0") + "%"


@dataclass(frozen=True)
class Plan:
    effective_from: date
    shares: Mapping[Envelope, int]  # punkty bazowe

    def __post_init__(self) -> None:
        if set(self.shares) != set(Envelope):
            raise PlanError("Plan musi mieć udział każdej koperty.")
        if any(bp < 0 for bp in self.shares.values()):
            raise PlanError("Udziały nie mogą być ujemne.")
        total = sum(self.shares.values())
        if total != FULL:
            raise PlanError(f"Udziały sumują się do {format_percent(total)}, a muszą do 100%.")


def plan_for(plans: Iterable[Plan], day: date) -> Plan:
    """Plan obowiązujący w danym dniu: najpóźniejszy z datą obowiązywania nie późniejszą niż dzień."""
    candidates = [p for p in plans if p.effective_from <= day]
    if not candidates:
        raise PlanError(f"Brak planu podziału obowiązującego {day.isoformat()}.")
    return max(candidates, key=lambda p: p.effective_from)


def round_to_zloty(amount: Money, basis_points: int) -> Money:
    """``amount × udział`` zaokrąglone do pełnych złotych, połówki w górę (dla kwot dodatnich)."""
    scaled = amount.grosze * basis_points  # grosze × 10 000
    zloty = (scaled + FULL * 100 // 2) // (FULL * 100)
    return Money(zloty * 100)


def split(amount: Money, plan: Plan) -> Split:
    """Podział dochodu na koperty w kolejności kopert; PKO dostaje resztę."""
    if not amount.is_positive:
        raise ValueError("Dzielić można tylko dodatnią kwotę.")
    parts = {e: round_to_zloty(amount, plan.shares[e]) for e in TRANSFER_ENVELOPES}
    pko = amount - sum(parts.values(), Money.zero())
    return {Envelope.PKO: pko, **parts}


def total(splits: Iterable[Split]) -> Split:
    """Suma podziałów kopertami (np. miesiąc albo lista nierozliczonych dochodów)."""
    result: Split = {e: Money.zero() for e in Envelope}
    for parts in splits:
        for envelope, value in parts.items():
            result[envelope] = result[envelope] + value
    return result

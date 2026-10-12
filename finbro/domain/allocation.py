"""Podział kwot na koperty według udziałów w punktach bazowych."""

from __future__ import annotations

from collections.abc import Hashable, Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date

from finbro.domain.money import Money

FULL_SHARE_BP = 10_000  # 100% w punktach bazowych


class AllocationError(ValueError):
    """Niepoprawny zestaw udziałów."""


def format_basis_points(bp: int) -> str:
    """1250 -> ``12,5%``, 5000 -> ``50%``."""
    whole, frac = divmod(bp, 100)
    if frac == 0:
        return f"{whole}%"
    return f"{whole},{frac:02d}".rstrip("0") + "%"


def parse_percent(text: str) -> int:
    """``12,5`` / ``12.5`` / ``50`` / ``50%`` -> punkty bazowe (1250 / 1250 / 5000 / 5000)."""
    cleaned = text.strip().removesuffix("%").strip().replace(",", ".")
    whole, _, frac = cleaned.partition(".")
    if not whole.isdigit() or (frac and (not frac.isdigit() or len(frac) > 2)):
        raise AllocationError(f"Niepoprawny udział procentowy: {text!r}")
    return int(whole) * 100 + int(frac.ljust(2, "0") or "0")


def validate_shares[K: Hashable](shares: Mapping[K, int], life: K) -> None:
    if life not in shares:
        raise AllocationError("Zestaw udziałów musi zawierać kopertę Życie.")
    if any(bp < 0 for bp in shares.values()):
        raise AllocationError("Udział koperty nie może być ujemny.")
    total = sum(shares.values())
    if total != FULL_SHARE_BP:
        raise AllocationError(
            f"Suma udziałów musi wynosić 100%, a wynosi {format_basis_points(total)}."
        )


def split_amount[K: Hashable](total: Money, shares: Mapping[K, int], life: K) -> dict[K, Money]:
    """Dzieli kwotę na koperty.

    Każda koperta poza Życiem dostaje swój udział zaokrąglony w dół do pełnego grosza
    (dzielenie całkowite), a Życie dostaje resztę, więc suma kopert równa się kwocie
    wejściowej. Kwota ujemna (korekta) jest dzielona symetrycznie do dodatniej:
    ``split(-x) == -split(x)``, dzięki czemu wycofanie dochodu dokładnie znosi jego podział.
    """
    validate_shares(shares, life)
    sign = -1 if total.grosze < 0 else 1
    magnitude = abs(total.grosze)
    result: dict[K, Money] = {}
    allocated = 0
    for key, bp in shares.items():
        if key == life:
            continue
        part = magnitude * bp // FULL_SHARE_BP
        result[key] = Money(sign * part)
        allocated += part
    result[life] = Money(sign * (magnitude - allocated))
    return result


@dataclass(frozen=True)
class AllocationPlan[K: Hashable]:
    """Zestaw udziałów obowiązujący od wskazanej daty."""

    effective_from: date
    shares: Mapping[K, int]
    life: K
    id: int | None = field(default=None, compare=False)

    def __post_init__(self) -> None:
        validate_shares(self.shares, self.life)

    def split(self, total: Money) -> dict[K, Money]:
        return split_amount(total, self.shares, self.life)


def plan_for_date[K: Hashable](plans: Iterable[AllocationPlan[K]], day: date) -> AllocationPlan[K]:
    """Plan obowiązujący w danym dniu: ostatni z datą obowiązywania nie późniejszą niż ``day``."""
    candidates = [p for p in plans if p.effective_from <= day]
    if not candidates:
        raise AllocationError(f"Brak planu podziału obowiązującego w dniu {day.isoformat()}.")
    return max(candidates, key=lambda p: p.effective_from)

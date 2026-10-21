"""Przelewy na koperty liczone od sumy nierozliczonych dochodów (D13) i rozdział ich kwot na dochody."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

from finbro.domain.allocation import FULL, Plan, Split, split, total
from finbro.domain.envelopes import TRANSFER_ENVELOPES, Envelope
from finbro.domain.money import Money

ZLOTY = 100 * FULL  # jeden złoty w jednostkach ``grosze × punkty bazowe``


@dataclass(frozen=True)
class PlannedIncome:
    """Kwota nierozliczonego dochodu i plan obowiązujący w jego dniu."""

    amount: Money
    plan: Plan


@dataclass(frozen=True)
class Transfer:
    envelope: Envelope
    amount: Money
    title: str


def transfer_title(envelope: Envelope, day: date) -> str:
    return f"FinBro {envelope.label} {day.isoformat()}"


def _groups(incomes: Sequence[PlannedIncome]) -> list[list[int]]:
    """Indeksy dochodów pogrupowane według planu (data obowiązywania jest unikalna), w kolejności dochodów."""
    groups: dict[date, list[int]] = defaultdict(list)
    for i, income in enumerate(incomes):
        groups[income.plan.effective_from].append(i)
    return list(groups.values())


def _group_split(incomes: Sequence[PlannedIncome], group: list[int]) -> Split:
    return split(sum((incomes[i].amount for i in group), Money.zero()), incomes[group[0]].plan)


def pooled(incomes: Sequence[PlannedIncome]) -> Split:
    """Podział sumy dochodów osobno dla każdego planu, zsumowany kopertami."""
    return total(_group_split(incomes, group) for group in _groups(incomes))


def _largest_remainders(exact: Sequence[int], target: int) -> list[int]:
    """Pełne złote z dokładnych części (``grosze × punkty bazowe``) sumujące się do ``target`` złotych.

    Brakujące złote dostają części o największej reszcie; przy remisie wcześniejsza na liście.
    """
    zloty = [part // ZLOTY for part in exact]
    by_remainder = sorted(range(len(exact)), key=lambda i: exact[i] % ZLOTY, reverse=True)  # stabilne
    for i in by_remainder[: target - sum(zloty)]:
        zloty[i] += 1
    return zloty


def distribute(incomes: Sequence[PlannedIncome]) -> list[Split]:
    """Podział każdego dochodu tak, żeby koperty sumowały się do ``pooled``; PKO dostaje resztę dochodu.

    Kolejność dochodów rozstrzyga remisy, więc podawaj je według daty, a potem kolejności wpisu.
    """
    parts: list[Split] = [{} for _ in incomes]
    for group in _groups(incomes):
        plan, target = incomes[group[0]].plan, _group_split(incomes, group)
        for envelope in TRANSFER_ENVELOPES:
            exact = [incomes[i].amount.grosze * plan.shares[envelope] for i in group]
            for i, zloty in zip(group, _largest_remainders(exact, target[envelope].grosze // 100), strict=True):
                parts[i][envelope] = Money(zloty * 100)
    return [
        {Envelope.PKO: income.amount - sum(p.values(), Money.zero()), **p}
        for income, p in zip(incomes, parts, strict=True)
    ]


def transfers(incomes: Sequence[PlannedIncome], day: date) -> list[Transfer]:
    """Przelewy na Wakacje, XTB i Obligacje; PKO zostaje na koncie głównym, zera pomijamy."""
    sums = pooled(incomes)
    return [
        Transfer(envelope, sums[envelope], transfer_title(envelope, day))
        for envelope in TRANSFER_ENVELOPES
        if sums[envelope].is_positive
    ]

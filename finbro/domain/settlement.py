"""Rozliczenia tygodniowe: obiekty domenowe."""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import StrEnum

from finbro.domain.allocation import AllocationPlan, plan_for_date
from finbro.domain.enums import SettlementStatus
from finbro.domain.money import Money
from finbro.domain.periods import IsoWeek
from finbro.domain.text import fold


@dataclass(frozen=True)
class SettlementLine:
    """Linia rozliczenia dla jednej koperty. Po zamknięciu kwoty są niezmienne."""

    envelope_id: int
    due: Money
    corrections: Money
    carryover: Money
    id: int | None = None

    @property
    def to_transfer(self) -> Money:
        return self.due + self.corrections + self.carryover


@dataclass(frozen=True)
class Settlement:
    week: IsoWeek
    status: SettlementStatus
    lines: tuple[SettlementLine, ...] = ()
    closed_at: datetime | None = None
    id: int | None = None

    def line_for(self, envelope_id: int) -> SettlementLine | None:
        return next((line for line in self.lines if line.envelope_id == envelope_id), None)


@dataclass(frozen=True)
class SettlementPayment:
    """Przelew ODKŁADANIE zaliczony na linię rozliczenia."""

    settlement_line_id: int
    transaction_id: int
    amount: Money
    id: int | None = field(default=None, compare=False)


@dataclass(frozen=True)
class SettlementAdjustment:
    """Ujemna korekta po wycofaniu dochodu z zamkniętego tygodnia."""

    week: IsoWeek
    transaction_id: int
    amount: Money
    income_date: date
    id: int | None = field(default=None, compare=False)


CLOSED_STATUSES = frozenset({SettlementStatus.CLOSED, SettlementStatus.SETTLED})


def nearest_open_week(week: IsoWeek, closed: Collection[IsoWeek]) -> IsoWeek:
    """Pierwszy tydzień od ``week`` (włącznie), którego rozliczenie nie jest zamknięte."""
    while week in closed:
        week = week.next()
    return week


# Tytuł przelewu (D8), dopasowywany na tekście po ``fold``: bez wielkości liter, polskich znaków i nadmiarowych spacji.
_TITLE_RE = re.compile(r"finbro (\d{4}) ?- ?t ?(\d{1,2}) (\S+)")


def transfer_title(week: IsoWeek, envelope_name: str) -> str:
    return f"FinBro {week.label} {envelope_name}"


def parse_transfer_title(title: str | None) -> tuple[IsoWeek, str] | None:
    """``FinBro 2026-T41 Wakacje`` -> (2026-T41, "wakacje")."""
    match = _TITLE_RE.search(fold(title))
    if match is None:
        return None
    try:
        week = IsoWeek(int(match.group(1)), int(match.group(2)))
    except ValueError:
        return None
    return week, match.group(3)


def envelope_word_matches(word: str, envelope_name: str) -> bool:
    folded = fold(envelope_name).split()
    return bool(folded) and folded[0] == word


def is_settled_income_date(income_date: date, start_date: date | None) -> bool:
    """Dochody sprzed daty startu nie podlegają podziałowi (D7, spec "Data startu")."""
    return start_date is None or income_date >= start_date


@dataclass(frozen=True)
class IncomeContribution:
    """Kwota wchodząca do rozliczenia: dochód tygodnia albo korekta (dodatnia lub ujemna)."""

    amount: Money
    income_date: date
    correction: bool = False


def compute_lines(
    contributions: Iterable[IncomeContribution],
    plans: Sequence[AllocationPlan[int]],
    envelope_ids: Sequence[int],
    life_envelope_id: int,
    carryover: Mapping[int, Money],
) -> tuple[SettlementLine, ...]:
    """Wylicza linie rozliczenia.

    Dochody tygodnia (należność) i korekty są grupowane według planu obowiązującego w dniu
    dochodu. Każda grupa jest dzielona i zaokrąglana osobno, reszta trafia do Życia, więc suma
    kopert jest dokładnie równa sumie dochodów i korekt (D7).
    """
    groups: dict[tuple[bool, date], Money] = defaultdict(Money.zero)
    plan_by_date: dict[date, AllocationPlan[int]] = {}
    for c in contributions:
        plan = plan_for_date(plans, c.income_date)
        plan_by_date[plan.effective_from] = plan
        groups[(c.correction, plan.effective_from)] += c.amount

    due: dict[int, Money] = defaultdict(Money.zero)
    corrections: dict[int, Money] = defaultdict(Money.zero)
    for (is_correction, effective_from), total in groups.items():
        target = corrections if is_correction else due
        for envelope_id, part in plan_by_date[effective_from].split(total).items():
            target[envelope_id] += part

    return tuple(
        SettlementLine(
            envelope_id=env,
            due=due[env],
            corrections=corrections[env],
            carryover=Money.zero() if env == life_envelope_id else carryover.get(env, Money.zero()),
        )
        for env in envelope_ids
    )


def carryover_before(
    closed_before: Iterable[Settlement], paid_by_line: Mapping[int, Money], life_envelope_id: int
) -> dict[int, Money]:
    """Przeniesienie na kolejne rozliczenie dla każdej koperty poza Życiem.

    Liczone kumulatywnie: należności i korekty wszystkich wcześniejszych zamkniętych rozliczeń
    minus wszystkie przelewy do nich przypisane. W zwykłym przypadku to dokładnie
    ``kwota_do_przelania(N-1) - suma_płatności(N-1)`` z D7, a dodatkowo poprawnie obejmuje
    przelew zaliczony na starszy tydzień już po zamknięciu kolejnego.
    """
    carry: dict[int, Money] = defaultdict(Money.zero)
    for settlement in closed_before:
        for line in settlement.lines:
            if line.envelope_id == life_envelope_id:
                continue
            paid = paid_by_line.get(line.id, Money.zero()) if line.id is not None else Money.zero()
            carry[line.envelope_id] += line.due + line.corrections - paid
    return dict(carry)


class LineState(StrEnum):
    NO_TRANSFER = "NO_TRANSFER"  # kwota zerowa lub ujemna: brak przelewu, ujemna kwota przechodzi dalej
    PAID = "PAID"
    CARRIED = "CARRIED"  # niedopłata przeszła do późniejszego zamkniętego rozliczenia
    PENDING = "PENDING"

    @property
    def label(self) -> str:
        return {
            "NO_TRANSFER": "bez przelewu",
            "PAID": "wykonany",
            "CARRIED": "niedopłata przeniesiona",
            "PENDING": "do wykonania",
        }[self.value]


def line_state(line: SettlementLine, paid: Money, carried_forward: bool) -> LineState:
    if not line.to_transfer.is_positive:
        return LineState.NO_TRANSFER
    if paid >= line.to_transfer:
        return LineState.PAID
    return LineState.CARRIED if carried_forward else LineState.PENDING


def settlement_status(
    settlement: Settlement, paid_by_line: Mapping[int, Money], carried_forward: bool, life_envelope_id: int
) -> SettlementStatus:
    """Rozliczone, gdy każdy przelew z listy jest pokryty przelewami (albo jego niedopłata przeszła dalej)."""
    if settlement.status is SettlementStatus.OPEN:
        return SettlementStatus.OPEN
    states = [
        line_state(line, paid_by_line.get(line.id, Money.zero()), carried_forward)
        for line in settlement.lines
        if line.envelope_id != life_envelope_id and line.id is not None
    ]
    return SettlementStatus.SETTLED if LineState.PENDING not in states else SettlementStatus.CLOSED

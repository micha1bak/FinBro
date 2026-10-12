"""Okresy: tygodnie ISO 8601 (pon–nd), miesiące i lata kalendarzowe."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta
from enum import StrEnum

MONTH_NAMES_PL = (
    "styczeń", "luty", "marzec", "kwiecień", "maj", "czerwiec",
    "lipiec", "sierpień", "wrzesień", "październik", "listopad", "grudzień",
)

_WEEK_LABEL_RE = re.compile(r"^(\d{4})-T(\d{1,2})$", re.IGNORECASE)
_MONTH_LABEL_RE = re.compile(r"^(\d{4})-(\d{2})$")
_YEAR_LABEL_RE = re.compile(r"^(\d{4})$")


class PeriodKind(StrEnum):
    WEEK = "week"
    MONTH = "month"
    YEAR = "year"


@dataclass(frozen=True, order=True, slots=True)
class IsoWeek:
    """Tydzień ISO 8601: od poniedziałku do niedzieli, etykieta ``2026-T41``."""

    year: int
    week: int

    def __post_init__(self) -> None:
        # Walidacja przez konstrukcję daty poniedziałku: niepoprawny numer tygodnia rzuca ValueError.
        date.fromisocalendar(self.year, self.week, 1)

    @classmethod
    def of(cls, day: date) -> IsoWeek:
        iso = day.isocalendar()
        return cls(iso.year, iso.week)

    @classmethod
    def parse(cls, label: str) -> IsoWeek:
        match = _WEEK_LABEL_RE.match(label.strip())
        if match is None:
            raise ValueError(f"Niepoprawna etykieta tygodnia: {label!r}")
        return cls(int(match[1]), int(match[2]))

    @property
    def kind(self) -> PeriodKind:
        return PeriodKind.WEEK

    @property
    def start(self) -> date:
        return date.fromisocalendar(self.year, self.week, 1)

    @property
    def end(self) -> date:
        return date.fromisocalendar(self.year, self.week, 7)

    @property
    def label(self) -> str:
        return f"{self.year}-T{self.week:02d}"

    @property
    def title(self) -> str:
        return f"{self.label} ({self.start.isoformat()} – {self.end.isoformat()})"

    def prev(self) -> IsoWeek:
        return IsoWeek.of(self.start - timedelta(days=7))

    def next(self) -> IsoWeek:
        return IsoWeek.of(self.start + timedelta(days=7))

    def contains(self, day: date) -> bool:
        return self.start <= day <= self.end

    def __str__(self) -> str:
        return self.label


@dataclass(frozen=True, order=True, slots=True)
class Month:
    year: int
    month: int

    def __post_init__(self) -> None:
        if not 1 <= self.month <= 12:
            raise ValueError(f"Niepoprawny miesiąc: {self.month}")

    @classmethod
    def of(cls, day: date) -> Month:
        return cls(day.year, day.month)

    @classmethod
    def parse(cls, label: str) -> Month:
        match = _MONTH_LABEL_RE.match(label.strip())
        if match is None:
            raise ValueError(f"Niepoprawna etykieta miesiąca: {label!r}")
        return cls(int(match[1]), int(match[2]))

    @property
    def kind(self) -> PeriodKind:
        return PeriodKind.MONTH

    @property
    def start(self) -> date:
        return date(self.year, self.month, 1)

    @property
    def end(self) -> date:
        return self.next().start - timedelta(days=1)

    @property
    def label(self) -> str:
        return f"{self.year}-{self.month:02d}"

    @property
    def title(self) -> str:
        return f"{MONTH_NAMES_PL[self.month - 1]} {self.year}"

    def prev(self) -> Month:
        return Month(self.year - 1, 12) if self.month == 1 else Month(self.year, self.month - 1)

    def next(self) -> Month:
        return Month(self.year + 1, 1) if self.month == 12 else Month(self.year, self.month + 1)

    def contains(self, day: date) -> bool:
        return (day.year, day.month) == (self.year, self.month)

    def __str__(self) -> str:
        return self.label


@dataclass(frozen=True, order=True, slots=True)
class Year:
    year: int

    @classmethod
    def of(cls, day: date) -> Year:
        return cls(day.year)

    @classmethod
    def parse(cls, label: str) -> Year:
        match = _YEAR_LABEL_RE.match(label.strip())
        if match is None:
            raise ValueError(f"Niepoprawna etykieta roku: {label!r}")
        return cls(int(match[1]))

    @property
    def kind(self) -> PeriodKind:
        return PeriodKind.YEAR

    @property
    def start(self) -> date:
        return date(self.year, 1, 1)

    @property
    def end(self) -> date:
        return date(self.year, 12, 31)

    @property
    def label(self) -> str:
        return str(self.year)

    @property
    def title(self) -> str:
        return f"rok {self.year}"

    def prev(self) -> Year:
        return Year(self.year - 1)

    def next(self) -> Year:
        return Year(self.year + 1)

    def contains(self, day: date) -> bool:
        return day.year == self.year

    def __str__(self) -> str:
        return self.label


Period = IsoWeek | Month | Year

_PERIOD_CLASSES: dict[PeriodKind, type[IsoWeek] | type[Month] | type[Year]] = {
    PeriodKind.WEEK: IsoWeek,
    PeriodKind.MONTH: Month,
    PeriodKind.YEAR: Year,
}


def period_of(kind: PeriodKind, day: date) -> Period:
    return _PERIOD_CLASSES[kind].of(day)


def parse_period(kind: PeriodKind, label: str) -> Period:
    return _PERIOD_CLASSES[kind].parse(label)


def periods_ending_at(period: Period, count: int) -> list[Period]:
    """Kolejne okresy tego samego rodzaju kończące się na ``period`` (od najstarszego)."""
    result: list[Period] = [period]
    while len(result) < count:
        result.append(result[-1].prev())
    return list(reversed(result))

"""Pokrycie okresów importami wyciągów."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, timedelta

ONE_DAY = timedelta(days=1)


@dataclass(frozen=True, order=True)
class DateRange:
    start: date
    end: date

    def __post_init__(self) -> None:
        if self.end < self.start:
            raise ValueError(f"Koniec zakresu {self.end} jest przed początkiem {self.start}")

    @property
    def days(self) -> int:
        return (self.end - self.start).days + 1

    def label(self) -> str:
        if self.start == self.end:
            return self.start.isoformat()
        return f"{self.start.isoformat()} – {self.end.isoformat()}"


def merge_ranges(ranges: Iterable[DateRange]) -> list[DateRange]:
    """Scala zakresy nachodzące lub stykające się (dzień po dniu)."""
    merged: list[DateRange] = []
    for r in sorted(ranges):
        if merged and r.start <= merged[-1].end + ONE_DAY:
            if r.end > merged[-1].end:
                merged[-1] = DateRange(merged[-1].start, r.end)
        else:
            merged.append(r)
    return merged


def uncovered(ranges: Iterable[DateRange], within: DateRange) -> list[DateRange]:
    """Dni z ``within`` nieobjęte żadnym zakresem."""
    gaps: list[DateRange] = []
    cursor = within.start
    for r in merge_ranges(ranges):
        if r.end < cursor:
            continue
        if r.start > within.end:
            break
        if r.start > cursor:
            gaps.append(DateRange(cursor, min(r.start - ONE_DAY, within.end)))
        cursor = max(cursor, r.end + ONE_DAY)
        if cursor > within.end:
            break
    if cursor <= within.end:
        gaps.append(DateRange(cursor, within.end))
    return gaps


def coverage_gaps(ranges: Iterable[DateRange], start_date: date | None) -> list[DateRange]:
    """Luki w importach między datą startu a końcem ostatniego importu."""
    ranges = list(ranges)
    if start_date is None or not ranges:
        return []
    last = max(r.end for r in ranges)
    if last < start_date:
        return []
    return uncovered(ranges, DateRange(start_date, last))

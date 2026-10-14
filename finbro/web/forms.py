"""Parsowanie pól formularzy z komunikatami dla użytkownika."""

from __future__ import annotations

from datetime import date

from finbro.domain.incomes import IncomeForm
from finbro.domain.money import Money, MoneyParseError

MONTHS = ["styczeń", "luty", "marzec", "kwiecień", "maj", "czerwiec", "lipiec",
          "sierpień", "wrzesień", "październik", "listopad", "grudzień"]


class FormError(ValueError):
    """Niepoprawna wartość pola formularza."""


def parse_date(text: str | None, field: str = "Data") -> date:
    try:
        return date.fromisoformat((text or "").strip())
    except ValueError as exc:
        raise FormError(f"{field}: podaj datę w formacie RRRR-MM-DD.") from exc


def parse_money(text: str | None, field: str = "Kwota") -> Money:
    try:
        return Money.parse(text or "")
    except MoneyParseError as exc:
        raise FormError(f"{field}: podaj kwotę, np. 174,00.") from exc


def parse_form(text: str | None) -> IncomeForm:
    try:
        return IncomeForm(text or "")
    except ValueError as exc:
        raise FormError("Forma: wybierz PKO albo gotówkę.") from exc


def parse_month(text: str | None, default: date) -> tuple[int, int]:
    """``"2026-10"`` -> (2026, 10); niepoprawna wartość -> miesiąc z ``default``."""
    try:
        year, month = (int(part) for part in (text or "").split("-"))
        date(year, month, 1)
        return year, month
    except ValueError:
        return default.year, default.month


def month_label(year: int, month: int) -> str:
    return f"{MONTHS[month - 1]} {year}"


def shift_month(year: int, month: int, delta: int) -> str:
    index = year * 12 + (month - 1) + delta
    return f"{index // 12}-{index % 12 + 1:02d}"

"""Parser wyciągów XML eksportowanych z iPKO (element główny ``account-history``).

Czysty Python: zamienia plik na listę operacji domenowych, bez dostępu do bazy.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import date

from finbro.domain.money import Money, MoneyParseError
from finbro.domain.transactions import Direction

ROOT_TAG = "account-history"


class ImportFormatError(ValueError):
    """Plik nie jest poprawnym wyciągiem XML z iPKO."""


# Znane etykiety opisu (D4). Dłuższe etykiety muszą wygrywać z krótszymi ("Adres nadawcy" przed "Adres").
KNOWN_LABELS = (
    "Rachunek nadawcy",
    "Rachunek odbiorcy",
    "Nazwa nadawcy",
    "Nazwa odbiorcy",
    "Adres nadawcy",
    "Adres odbiorcy",
    "Tytuł",
    "Lokalizacja",
    "Adres",
    "Miasto",
    "Kraj",
    "Numer referencyjny",
    "Numer telefonu",
    "Numer karty",
    "Data wykonania operacji",
    "Oryginalna kwota operacji",
)
_LABEL_RE = re.compile(
    r"(?<!\w)(" + "|".join(re.escape(label) for label in sorted(KNOWN_LABELS, key=len, reverse=True)) + r")\s*:"
)

# Pola trafiające do kolumn transakcji; pozostałe etykiety lądują w ``extra``.
_FIELD_FOR_LABEL = {
    "Rachunek nadawcy": "counterparty_account",
    "Rachunek odbiorcy": "counterparty_account",
    "Nazwa nadawcy": "counterparty_name",
    "Nazwa odbiorcy": "counterparty_name",
    "Adres nadawcy": "counterparty_address",
    "Adres odbiorcy": "counterparty_address",
    "Tytuł": "title",
    "Adres": "merchant",
    "Miasto": "city",
    "Kraj": "country",
    "Numer referencyjny": "reference_number",
}
OPERATION_ID_KEY = "Identyfikator operacji"


@dataclass(frozen=True)
class DescriptionFields:
    counterparty_account: str | None = None
    counterparty_name: str | None = None
    counterparty_address: str | None = None
    title: str | None = None
    merchant: str | None = None
    city: str | None = None
    country: str | None = None
    reference_number: str | None = None
    extra: dict[str, str] = field(default_factory=dict)


def parse_description(text: str) -> DescriptionFields:
    """Rozbija opis ``Etykieta : wartość ...`` po znanych etykietach.

    Wartość to tekst do następnej znanej etykiety. Tekst przed pierwszą etykietą
    to identyfikator operacji kartowej. Nieznane etykiety zostają w wartości
    poprzedniego pola, a pełny opis jest zawsze zapisywany osobno.
    """
    text = " ".join(text.split())
    matches = list(_LABEL_RE.finditer(text))
    values: dict[str, str] = {}
    extra: dict[str, str] = {}

    prefix = text[: matches[0].start()] if matches else text
    if prefix.strip():
        extra[OPERATION_ID_KEY] = prefix.strip()

    for i, match in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        label, value = match.group(1), text[match.end() : end].strip()
        if not value:
            continue  # np. "Lokalizacja :" bez wartości, przed "Adres :"
        target = _FIELD_FOR_LABEL.get(label)
        if target is None:
            extra[label] = value
        elif target not in values:
            values[target] = value
    return DescriptionFields(**values, extra=extra)


@dataclass(frozen=True)
class ParsedOperation:
    order_date: date
    exec_date: date | None
    bank_type: str
    description: str
    amount: Money
    ending_balance: Money | None
    fields: DescriptionFields

    @property
    def is_booked(self) -> bool:
        return self.exec_date is not None

    @property
    def direction(self) -> Direction:
        return Direction.of(self.amount)


@dataclass(frozen=True)
class ParsedStatement:
    account_number: str
    date_from: date
    date_to: date
    operations: tuple[ParsedOperation, ...]

    @property
    def booked(self) -> list[ParsedOperation]:
        return [op for op in self.operations if op.is_booked]

    @property
    def pending(self) -> list[ParsedOperation]:
        return [op for op in self.operations if not op.is_booked]


def _text(element: ET.Element | None) -> str:
    return (element.text or "").strip() if element is not None else ""


def _date(value: str, what: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ImportFormatError(f"Niepoprawna data w polu {what}: {value!r}") from exc


def _money(value: str, what: str) -> Money:
    try:
        return Money.parse(value)
    except MoneyParseError as exc:
        raise ImportFormatError(f"Niepoprawna kwota w polu {what}: {value!r}") from exc


def _parse_operation(element: ET.Element, index: int) -> ParsedOperation:
    def required(tag: str) -> str:
        value = _text(element.find(tag))
        if not value:
            raise ImportFormatError(f"Operacja nr {index}: brak wymaganego pola {tag}")
        return value

    exec_raw = _text(element.find("exec-date"))
    exec_date = _date(exec_raw, "exec-date") if exec_raw else None
    balance_raw = _text(element.find("ending-balance"))
    if exec_date is not None and not balance_raw:
        raise ImportFormatError(f"Operacja nr {index}: brak salda po operacji")
    description = _text(element.find("description"))
    amount = _money(required("amount"), "amount")
    if amount.is_zero:
        raise ImportFormatError(f"Operacja nr {index}: kwota zerowa")
    return ParsedOperation(
        order_date=_date(required("order-date"), "order-date"),
        exec_date=exec_date,
        bank_type=required("type"),
        description=description,
        amount=amount,
        ending_balance=_money(balance_raw, "ending-balance") if balance_raw else None,
        fields=parse_description(description),
    )


def parse_statement(content: bytes) -> ParsedStatement:
    """Parsuje wyciąg. Błąd formatu przerywa cały import (atomowość)."""
    if b"<!DOCTYPE" in content[:2048].upper():
        raise ImportFormatError("Plik zawiera deklarację DOCTYPE, której wyciąg iPKO nie używa.")
    try:
        root = ET.fromstring(content)
    except ET.ParseError as exc:
        raise ImportFormatError(f"Plik nie jest poprawnym XML-em ({exc}).") from exc
    if root.tag != ROOT_TAG:
        raise ImportFormatError("Plik nie jest wyciągiem XML z iPKO (brak elementu account-history).")

    search = root.find("search")
    account = _text(search.find("account")) if search is not None else ""
    date_el = search.find("date") if search is not None else None
    if not account or date_el is None or not date_el.get("since") or not date_el.get("to"):
        raise ImportFormatError("Brak numeru rachunku lub zakresu dat w sekcji search wyciągu.")

    operations_el = root.find("operations")
    elements = list(operations_el.findall("operation")) if operations_el is not None else []
    # iPKO podaje operacje od najnowszej; odwracamy do kolejności chronologicznej.
    operations = tuple(_parse_operation(el, i) for i, el in reversed(list(enumerate(elements, start=1))))
    return ParsedStatement(
        account_number=account,
        date_from=_date(date_el.get("since", ""), "date since"),
        date_to=_date(date_el.get("to", ""), "date to"),
        operations=operations,
    )

"""Kwoty pieniężne jako liczby całkowite w groszach."""

from __future__ import annotations

import re
from dataclasses import dataclass

NBSP = " "
_AMOUNT_RE = re.compile(r"^(?P<sign>[+-])?(?P<int>\d+)(?:[.,](?P<frac>\d{1,2}))?$")


class MoneyParseError(ValueError):
    """Tekst nie jest poprawną kwotą z dokładnością do grosza."""


@dataclass(frozen=True, order=True, slots=True)
class Money:
    """Kwota w groszach. Arytmetyka wyłącznie na liczbach całkowitych, nigdy na float."""

    grosze: int

    def __post_init__(self) -> None:
        if not isinstance(self.grosze, int) or isinstance(self.grosze, bool):
            raise TypeError(f"Money wymaga liczby całkowitej groszy, otrzymano {self.grosze!r}")

    @classmethod
    def zero(cls) -> Money:
        return cls(0)

    @classmethod
    def parse(cls, text: str) -> Money:
        """Parsuje kwoty w postaci ``-645.00``, ``+2753,36``, ``1 234,56`` lub ``12,5``."""
        cleaned = text.strip().replace(NBSP, "").replace(" ", "")
        match = _AMOUNT_RE.match(cleaned)
        if match is None:
            raise MoneyParseError(f"Niepoprawna kwota: {text!r}")
        frac = (match["frac"] or "").ljust(2, "0")
        grosze = int(match["int"]) * 100 + int(frac or "0")
        return cls(-grosze if match["sign"] == "-" else grosze)

    @property
    def is_negative(self) -> bool:
        return self.grosze < 0

    @property
    def is_positive(self) -> bool:
        return self.grosze > 0

    @property
    def is_zero(self) -> bool:
        return self.grosze == 0

    def __abs__(self) -> Money:
        return Money(abs(self.grosze))

    def __neg__(self) -> Money:
        return Money(-self.grosze)

    def __add__(self, other: Money) -> Money:
        if not isinstance(other, Money):
            return NotImplemented
        return Money(self.grosze + other.grosze)

    def __radd__(self, other: object) -> Money:
        # Pozwala używać wbudowanego sum() ze startem 0.
        if other == 0:
            return self
        return NotImplemented

    def __sub__(self, other: Money) -> Money:
        if not isinstance(other, Money):
            return NotImplemented
        return Money(self.grosze - other.grosze)

    def __mul__(self, factor: int) -> Money:
        if not isinstance(factor, int) or isinstance(factor, bool):
            return NotImplemented
        return Money(self.grosze * factor)

    __rmul__ = __mul__

    def __bool__(self) -> bool:
        return self.grosze != 0

    def to_plain(self) -> str:
        """Format techniczny: ``-645.00`` (np. do pól formularzy)."""
        sign = "-" if self.grosze < 0 else ""
        whole, frac = divmod(abs(self.grosze), 100)
        return f"{sign}{whole}.{frac:02d}"

    def format(self, currency: bool = True, plus: bool = False) -> str:
        """Format polski: ``4950,03 zł``, ``12 345,67 zł``, ``-645,00 zł``.

        Liczby czterocyfrowe zapisujemy bez separatora tysięcy, większe grupujemy
        twardą spacją, zgodnie z polską konwencją.
        """
        whole, frac = divmod(abs(self.grosze), 100)
        digits = str(whole)
        if whole >= 10_000:
            groups = []
            while digits:
                groups.append(digits[-3:])
                digits = digits[:-3]
            digits = NBSP.join(reversed(groups))
        sign = "-" if self.grosze < 0 else ("+" if plus and self.grosze > 0 else "")
        text = f"{sign}{digits},{frac:02d}"
        return f"{text}{NBSP}zł" if currency else text

    def __str__(self) -> str:
        return self.format()

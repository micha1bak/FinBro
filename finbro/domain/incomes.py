"""Forma dochodu: wpływ na konto PKO albo gotówka. Nie zmienia podziału ani przelewów."""

from __future__ import annotations

from enum import StrEnum


class IncomeForm(StrEnum):
    PKO = "PKO"
    GOTOWKA = "GOTOWKA"

    @property
    def label(self) -> str:
        return "PKO" if self is IncomeForm.PKO else "gotówka"

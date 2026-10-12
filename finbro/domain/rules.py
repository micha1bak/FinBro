"""Silnik reguł klasyfikacji: warunki, priorytet, pierwsza pasująca reguła wygrywa."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

from finbro.domain.accounts import same_account
from finbro.domain.classification import ClassificationError, check_type
from finbro.domain.enums import ProposalSource, TransferKind, TxType
from finbro.domain.money import Money, MoneyParseError
from finbro.domain.text import fold
from finbro.domain.transactions import Classification, Direction, TransactionData


class RuleError(ValueError):
    """Niepoprawna definicja reguły."""


TEXT_FIELDS = ("bank_type", "counterparty_name", "title", "merchant")
CONDITION_KEYS = ("direction", *TEXT_FIELDS, "counterparty_account", "amount_min", "amount_max")

CONDITION_HELP = (
    "Dozwolone klucze: direction (IN/OUT), bank_type, counterparty_name, counterparty_account, "
    "title, merchant (tekst albo lista tekstów, wystarczy jeden), amount_min, amount_max (kwota bez znaku, np. \"100.00\")."
)


def _as_tuple(key: str, value: Any) -> tuple[str, ...]:
    if isinstance(value, str):
        values = [value]
    elif isinstance(value, list) and all(isinstance(v, str) for v in value):
        values = value
    else:
        raise RuleError(f"Warunek {key} musi być tekstem albo listą tekstów.")
    cleaned = tuple(v.strip() for v in values if v.strip())
    if not cleaned:
        raise RuleError(f"Warunek {key} jest pusty.")
    return cleaned


def _amount(key: str, value: Any) -> Money:
    try:
        money = Money.parse(str(value))
    except MoneyParseError as exc:
        raise RuleError(f"Warunek {key} musi być kwotą, np. \"100.00\".") from exc
    if money.is_negative:
        raise RuleError(f"Warunek {key} podaje kwotę bez znaku; kierunek określa direction.")
    return money


@dataclass(frozen=True)
class RuleConditions:
    direction: Direction | None = None
    bank_type: tuple[str, ...] = ()
    counterparty_name: tuple[str, ...] = ()
    counterparty_account: tuple[str, ...] = ()
    title: tuple[str, ...] = ()
    merchant: tuple[str, ...] = ()
    amount_min: Money | None = None
    amount_max: Money | None = None

    @classmethod
    def from_json(cls, data: Mapping[str, Any] | None) -> RuleConditions:
        if not isinstance(data, Mapping):
            raise RuleError("Warunki reguły muszą być obiektem JSON. " + CONDITION_HELP)
        unknown = set(data) - set(CONDITION_KEYS)
        if unknown:
            raise RuleError(f"Nieznane warunki: {', '.join(sorted(unknown))}. " + CONDITION_HELP)
        values: dict[str, Any] = {}
        if data.get("direction") is not None:
            try:
                values["direction"] = Direction(str(data["direction"]).upper())
            except ValueError as exc:
                raise RuleError("Warunek direction przyjmuje wartości IN albo OUT.") from exc
        for key in (*TEXT_FIELDS, "counterparty_account"):
            if data.get(key) is not None:
                values[key] = _as_tuple(key, data[key])
        for key in ("amount_min", "amount_max"):
            if data.get(key) is not None:
                values[key] = _amount(key, data[key])
        conditions = cls(**values)
        if conditions.is_empty:
            raise RuleError("Reguła musi mieć co najmniej jeden warunek poza kierunkiem. " + CONDITION_HELP)
        if conditions.amount_min and conditions.amount_max and conditions.amount_min > conditions.amount_max:
            raise RuleError("amount_min jest większe niż amount_max.")
        return conditions

    def to_json(self) -> dict[str, Any]:
        data: dict[str, Any] = {}
        if self.direction is not None:
            data["direction"] = self.direction.value
        for key in (*TEXT_FIELDS, "counterparty_account"):
            values = getattr(self, key)
            if values:
                data[key] = values[0] if len(values) == 1 else list(values)
        for key in ("amount_min", "amount_max"):
            money = getattr(self, key)
            if money is not None:
                data[key] = money.to_plain()
        return data

    @property
    def is_empty(self) -> bool:
        return not any(
            (*(getattr(self, k) for k in (*TEXT_FIELDS, "counterparty_account")), self.amount_min, self.amount_max)
        )

    def matches(self, tx: TransactionData) -> bool:
        if self.direction is not None and tx.direction is not self.direction:
            return False
        for key in TEXT_FIELDS:
            needles = getattr(self, key)
            if needles:
                haystack = fold(getattr(tx, key))
                if not any(fold(n) in haystack for n in needles):
                    return False
        if self.counterparty_account:
            if not any(same_account(tx.counterparty_account, a) for a in self.counterparty_account):
                return False
        magnitude = abs(tx.amount)
        if self.amount_min is not None and magnitude < self.amount_min:
            return False
        if self.amount_max is not None and magnitude > self.amount_max:
            return False
        return True


@dataclass(frozen=True)
class RuleResult:
    type: TxType
    category_id: int | None = None
    debtor_id: int | None = None
    transfer_kind: TransferKind | None = None


@dataclass(frozen=True)
class Rule:
    name: str
    conditions: RuleConditions
    result: RuleResult
    priority: int = 100
    active: bool = True
    id: int | None = field(default=None)

    def proposal(self) -> Classification:
        return Classification(
            type=self.result.type,
            category_id=self.result.category_id,
            debtor_id=self.result.debtor_id,
            transfer_kind=self.result.transfer_kind,
            source=ProposalSource.RULE,
            rule_id=self.id,
            reason=f"Reguła: {self.name}",
        )


def validate_rule(conditions: RuleConditions, result: RuleResult) -> None:
    """Wynik reguły musi spełniać wymagania typu; kierunek warunków musi pasować do typu."""
    directions = [conditions.direction] if conditions.direction else list(Direction)
    errors = []
    for direction in directions:
        try:
            check_type(direction, result.type, category_id=result.category_id, debtor_id=result.debtor_id)
        except ClassificationError as exc:
            errors.append(str(exc))
    if len(errors) == len(directions):
        raise RuleError(errors[0])


def first_match(rules: Iterable[Rule], tx: TransactionData) -> Rule | None:
    """Pierwsza aktywna reguła według priorytetu (mniejsza liczba = ważniejsza), potem id."""
    ordered = sorted((r for r in rules if r.active), key=lambda r: (r.priority, r.id if r.id is not None else 0))
    for rule in ordered:
        if rule.conditions.matches(tx) and _direction_fits(rule, tx):
            return rule
    return None


def _direction_fits(rule: Rule, tx: TransactionData) -> bool:
    # Reguła bez kierunku nie może nadać typu sprzecznego z kierunkiem transakcji.
    try:
        check_type(tx.direction, rule.result.type, category_id=rule.result.category_id, debtor_id=rule.result.debtor_id)
    except ClassificationError:
        return False
    return True

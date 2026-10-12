"""Decyzje użytkownika o klasyfikacji: skrzynka, poprawki i reguły z decyzji."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime

from finbro.domain.classification import (
    REQUIRES_DEBTOR,
    ClassificationError,
    check_category_choice,
    check_classification,
    normalized,
)
from finbro.domain.enums import ProposalSource, TransferKind, TxSource, TxType
from finbro.domain.history import CounterpartyKey
from finbro.domain.rules import Rule, RuleConditions, RuleResult
from finbro.domain.transactions import Classification, Transaction
from finbro.services.receivables import ReceivablesService
from finbro.services.uow import UnitOfWork

USER_RULE_PRIORITY = 50


@dataclass(frozen=True)
class Decision:
    """Wybór użytkownika w skrzynce albo na liście transakcji."""

    type: TxType
    category_id: int | None = None
    debtor_id: int | None = None
    transfer_kind: TransferKind | None = None
    envelope_id: int | None = None
    new_debtor_name: str | None = None
    remember: bool = False


def rule_from_decision(tx: Transaction, decision: Decision) -> Rule:
    """Reguła dla kontrahenta: po rachunku, a gdy go brak, po nazwie kontrahenta lub sprzedawcy."""
    key = CounterpartyKey.of(tx.data)
    conditions: dict[str, object] = {"direction": tx.direction.value}
    if tx.data.counterparty_account:
        conditions["counterparty_account"] = tx.data.counterparty_account
    elif tx.data.counterparty_name:
        conditions["counterparty_name"] = tx.data.counterparty_name
    elif tx.data.merchant:
        conditions["merchant"] = tx.data.merchant
    else:
        raise ClassificationError("Transakcja nie ma kontrahenta ani sprzedawcy, więc nie da się utworzyć reguły.")
    assert key.usable
    return Rule(
        name=f"{tx.counterparty or tx.data.counterparty_account} → {decision.type.label}",
        priority=USER_RULE_PRIORITY,
        conditions=RuleConditions.from_json(conditions),
        result=RuleResult(
            type=decision.type,
            category_id=decision.category_id,
            debtor_id=decision.debtor_id,
            transfer_kind=decision.transfer_kind,
        ),
    )


class ClassificationService:
    """Jedyne miejsce, w którym klasyfikacja staje się ostateczna (zatwierdzona)."""

    def __init__(self, uow: UnitOfWork, now: datetime | None = None) -> None:
        self.uow = uow
        self._now = now

    def now(self) -> datetime:
        return self._now or datetime.now(UTC)

    def _validate(self, tx: Transaction, classification: Classification, chosen_by_user: bool) -> Classification:
        classification = normalized(classification, keep_debtor=tx.data.source is TxSource.FORGIVENESS)
        check_classification(tx.direction, classification)
        if classification.category_id is not None and classification.type in (TxType.WYDATEK, TxType.ZWROT, TxType.ROZLICZENIE):
            category = next((c for c in self.uow.reference.categories() if c.id == classification.category_id), None)
            if category is None:
                raise ClassificationError("Wybrana kategoria nie istnieje.")
            previous = tx.classification
            unchanged = previous.confirmed and previous.category_id == category.id
            if not unchanged:
                check_category_choice(category, chosen_by_user=chosen_by_user)
        return classification

    def confirm(self, tx: Transaction, classification: Classification, chosen_by_user: bool = True) -> Transaction:
        """Zatwierdza klasyfikację transakcji po walidacji."""
        if classification.type is None:
            raise ClassificationError("Wybierz typ transakcji.")
        final = self._validate(tx, classification, chosen_by_user)
        final = replace(final, confirmed=True, confirmed_at=self.now())
        self.before_confirm(tx, final)
        updated = self.uow.transactions.set_classification(tx.id, final)
        self.uow.llm_jobs.cancel(tx.id)
        return updated

    def before_confirm(self, tx: Transaction, final: Classification) -> None:
        """Kontrole i skutki zatwierdzenia w tej samej transakcji bazodanowej."""
        ReceivablesService(self.uow).check_change(tx, final)

    def accept_proposal(self, transaction_id: int) -> Transaction:
        tx = self.uow.transactions.get(transaction_id)
        if tx.classification.type is None:
            raise ClassificationError("Ta pozycja nie ma propozycji do przyjęcia; wybierz typ ręcznie.")
        updated = self.confirm(tx, tx.classification, chosen_by_user=False)
        self.uow.commit()
        return updated

    def decide(self, transaction_id: int, decision: Decision) -> Transaction:
        tx = self.uow.transactions.get(transaction_id)
        if decision.type in REQUIRES_DEBTOR and decision.debtor_id is None and decision.new_debtor_name:
            debtor = self.uow.reference.debtor_by_name(decision.new_debtor_name)
            if debtor is None:
                debtor = self.uow.reference.add_debtor(decision.new_debtor_name)
            decision = replace(decision, debtor_id=debtor.id)
        classification = Classification(
            type=decision.type,
            category_id=decision.category_id,
            debtor_id=decision.debtor_id,
            transfer_kind=decision.transfer_kind,
            envelope_id=decision.envelope_id,
            source=ProposalSource.USER,
        )
        rule = rule_from_decision(tx, decision) if decision.remember else None
        try:
            updated = self.confirm(tx, classification)
            if rule is not None:
                self.uow.rules.add(rule)
        except Exception:
            self.uow.rollback()
            raise
        self.uow.commit()
        return updated

    def approve_rule_incomes(self) -> int:
        """Zbiorcze zatwierdzenie propozycji DOCHODU pochodzących z reguł."""
        count = 0
        for tx in self.uow.transactions.unconfirmed():
            c = tx.classification
            if c.type is TxType.DOCHOD and c.source is ProposalSource.RULE:
                self.confirm(tx, c, chosen_by_user=False)
                count += 1
        self.uow.commit()
        return count

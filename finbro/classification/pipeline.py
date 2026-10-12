"""Potok klasyfikacji nowych transakcji: reguły -> historia kontrahenta -> kolejka LLM (D9)."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, replace
from datetime import UTC, datetime

from finbro.domain.classification import ClassificationError, is_auto_accepted, normalized
from finbro.domain.history import CounterpartyKey, history_proposal
from finbro.domain.rules import Rule, first_match
from finbro.domain.transactions import Classification, Transaction
from finbro.services.receivables import ReceivablesService
from finbro.services.uow import UnitOfWork


@dataclass(frozen=True)
class PipelineStats:
    by_rule: int = 0
    by_history: int = 0
    queued_for_llm: int = 0
    auto_accepted: int = 0


def accept_if_allowed(tx: Transaction, proposal: Classification, now: datetime | None = None) -> Classification:
    proposal = normalized(proposal)
    if is_auto_accepted(tx.direction, proposal):
        return replace(proposal, confirmed=True, confirmed_at=now or datetime.now(UTC))
    return replace(proposal, confirmed=False, confirmed_at=None)


class ClassificationPipeline:
    def __init__(self, uow: UnitOfWork) -> None:
        self.uow = uow

    def propose(self, tx: Transaction, rules: list[Rule]) -> Classification | None:
        rule = first_match(rules, tx.data)
        if rule is not None:
            return rule.proposal()
        key = CounterpartyKey.of(tx.data)
        if key.usable:
            previous = self.uow.transactions.last_confirmed_like(key, exclude_id=tx.id)
            if previous is not None:
                return history_proposal(previous)
        return None

    def classify(self, transaction_ids: Iterable[int]) -> PipelineStats:
        """Klasyfikuje transakcje synchronicznie regułami i historią; resztę kolejkuje dla LLM."""
        rules = self.uow.rules.active()
        by_rule = by_history = accepted = 0
        to_queue: list[int] = []
        for tx in self.uow.transactions.get_many(list(transaction_ids)):
            proposal = self.propose(tx, rules)
            if proposal is None:
                self.uow.transactions.set_classification(tx.id, Classification())
                to_queue.append(tx.id)
                continue
            if proposal.rule_id is not None:
                by_rule += 1
            else:
                by_history += 1
            final = accept_if_allowed(tx, proposal)
            if final.confirmed and final.debtor_id is not None:
                try:
                    ReceivablesService(self.uow).check_change(tx, final)
                except ClassificationError:
                    final = replace(final, confirmed=False, confirmed_at=None)
            accepted += final.confirmed
            self.uow.transactions.set_classification(tx.id, final)
        self.uow.llm_jobs.enqueue(to_queue)
        return PipelineStats(by_rule=by_rule, by_history=by_history, queued_for_llm=len(to_queue), auto_accepted=accepted)

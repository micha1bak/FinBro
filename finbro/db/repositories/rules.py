"""Repozytorium reguł klasyfikacji."""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from finbro.db import models
from finbro.domain.rules import Rule, RuleConditions, RuleError, RuleResult

log = logging.getLogger(__name__)


def _rule(row: models.Rule) -> Rule:
    return Rule(
        id=row.id,
        name=row.name,
        priority=row.priority,
        active=row.active,
        conditions=RuleConditions.from_json(row.conditions),
        result=RuleResult(
            type=row.result_type,
            category_id=row.result_category_id,
            debtor_id=row.result_debtor_id,
            transfer_kind=row.result_transfer_kind,
        ),
    )


class RuleRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def active(self) -> list[Rule]:
        rows = self.session.scalars(
            select(models.Rule).where(models.Rule.active).order_by(models.Rule.priority, models.Rule.id)
        )
        rules = []
        for row in rows:
            try:
                rules.append(_rule(row))
            except RuleError:
                log.warning("Pominięto regułę %s z niepoprawnymi warunkami", row.id)
        return rules

    def add(self, rule: Rule) -> Rule:
        row = models.Rule(
            name=rule.name,
            priority=rule.priority,
            active=rule.active,
            conditions=rule.conditions.to_json(),
            result_type=rule.result.type,
            result_category_id=rule.result.category_id,
            result_debtor_id=rule.result.debtor_id,
            result_transfer_kind=rule.result.transfer_kind,
        )
        self.session.add(row)
        self.session.flush()
        return _rule(row)

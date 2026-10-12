from datetime import date

import pytest
from sqlalchemy import select

from finbro.db import models
from finbro.domain.classification import is_auto_accepted
from finbro.domain.enums import ProposalSource, TransferKind, TxType
from finbro.domain.money import Money
from finbro.domain.rules import Rule, RuleConditions, RuleResult
from finbro.domain.transactions import Classification, Direction
from finbro.services.importing import ImportService
from tests.helpers import OVERLAP, WEEK41, fixture_bytes


def all_transactions(uow):
    return {t.id: t for t in uow.transactions.list_between(date(2026, 1, 1), date(2026, 12, 31))}


def by(txs, **criteria):
    [match] = [t for t in txs.values() if all(getattr(t.data, k) == v for k, v in criteria.items())]
    return match


def test_import_classifies_with_rules_and_queues_the_rest(uow):
    result = ImportService(uow).import_pko_xml(fixture_bytes(WEEK41))
    txs = all_transactions(uow)
    queued = uow.llm_jobs.queued_transaction_ids()

    rule_matched = {
        by(txs, bank_type="Wypłata w bankomacie").id: TransferKind.WALLET,
        by(txs, bank_type="Wpłata gotówki we wpłatomacie").id: TransferKind.WALLET,
        by(txs, bank_type="Przelew z karty").id: TransferKind.FAMILY,
    }
    for tx_id, kind in rule_matched.items():
        c = txs[tx_id].classification
        assert (c.type, c.transfer_kind, c.source, c.confirmed) == (TxType.TRANSFER, kind, ProposalSource.RULE, True)
        assert c.confirmed_at is not None
        assert tx_id not in queued

    rest = set(result.new_transaction_ids) - set(rule_matched)
    assert queued == rest
    for tx_id in rest:
        c = txs[tx_id].classification
        assert (c.type, c.source, c.confirmed) == (None, None, False)


def test_history_proposals_follow_acceptance_rules(uow, db_session):
    service = ImportService(uow)
    service.import_pko_xml(fixture_bytes(WEEK41))
    txs = all_transactions(uow)
    groceries = db_session.scalar(select(models.Category.id).where(models.Category.name == "Spożywcze"))
    uow.transactions.set_classification(
        by(txs, merchant="JMP S.A. BIEDRONKA 2422").id,
        Classification(type=TxType.WYDATEK, category_id=groceries, source=ProposalSource.USER, confirmed=True),
    )
    uow.transactions.set_classification(
        by(txs, amount=Money.parse("4250.00")).id,
        Classification(type=TxType.DOCHOD, source=ProposalSource.USER, confirmed=True),
    )
    uow.commit()

    result = service.import_pko_xml(fixture_bytes(OVERLAP))
    txs = all_transactions(uow)
    queued = uow.llm_jobs.queued_transaction_ids()

    # Wydatek z historii: przyjęty automatycznie.
    groceries_tx = [t for t in txs.values() if t.data.merchant == "JMP S.A. BIEDRONKA 2422" and t.id in result.new_transaction_ids]
    [g] = groceries_tx
    assert (g.classification.type, g.classification.category_id, g.classification.source, g.classification.confirmed) == (
        TxType.WYDATEK, groceries, ProposalSource.HISTORY, True)
    assert g.id not in queued

    # Wpływ z historii jako DOCHÓD: propozycja w skrzynce, niezatwierdzona i bez kolejki LLM.
    income = by(txs, amount=Money.parse("3100.00"))
    assert (income.classification.type, income.classification.source, income.classification.confirmed) == (
        TxType.DOCHOD, ProposalSource.HISTORY, False)
    assert income.id not in queued

    # Przelewy z tytułem FinBro: ODKŁADANIE z reguły, przyjęte automatycznie.
    for title in ("FinBro 2026-T41 Wakacje", "finbro 2026-t41 xtb"):
        c = by(txs, title=title).classification
        assert (c.type, c.source, c.confirmed) == (TxType.ODKLADANIE, ProposalSource.RULE, True)


def test_income_rule_never_auto_confirms(uow):
    uow.rules.add(
        Rule(
            name="Kancelaria = dochód",
            priority=50,
            conditions=RuleConditions.from_json({"direction": "IN", "counterparty_name": "KANCELARIA PRAWNA"}),
            result=RuleResult(type=TxType.DOCHOD),
        )
    )
    uow.commit()
    ImportService(uow).import_pko_xml(fixture_bytes(WEEK41))
    c = by(all_transactions(uow), amount=Money.parse("4250.00")).classification
    assert (c.type, c.source, c.confirmed) == (TxType.DOCHOD, ProposalSource.RULE, False)


@pytest.mark.parametrize(
    ("direction", "proposal", "expected"),
    [
        (Direction.OUT, Classification(type=TxType.WYDATEK, category_id=1, source=ProposalSource.LLM), True),
        (Direction.OUT, Classification(type=TxType.WYDATEK, source=ProposalSource.LLM), False),  # brak kategorii
        (Direction.IN, Classification(type=TxType.DOCHOD, source=ProposalSource.RULE), False),
        (Direction.IN, Classification(type=TxType.TRANSFER, source=ProposalSource.RULE), True),
        (Direction.IN, Classification(type=TxType.TRANSFER, source=ProposalSource.HISTORY), False),
        (Direction.IN, Classification(type=TxType.ZWROT, category_id=1, source=ProposalSource.LLM), False),
        (Direction.OUT, Classification(type=TxType.DOCHOD, source=ProposalSource.RULE), False),
        (Direction.OUT, Classification(), False),
    ],
)
def test_acceptance_rules(direction, proposal, expected):
    assert is_auto_accepted(direction, proposal) is expected

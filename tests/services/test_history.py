from datetime import date

from sqlalchemy import select

from finbro.db import models
from finbro.domain.enums import ProposalSource, TxSource, TxType
from finbro.domain.history import CounterpartyKey, history_proposal
from finbro.domain.money import Money
from finbro.domain.transactions import Classification, Direction, TransactionData
from finbro.services.importing import ImportService
from tests.helpers import OVERLAP, WEEK41, fixture_bytes


def category_id(db_session, name: str) -> int:
    return db_session.scalar(select(models.Category.id).where(models.Category.name == name))


def find(uow, **criteria):
    txs = uow.transactions.list_between(date(2026, 1, 1), date(2026, 12, 31))
    return [t for t in txs if all(getattr(t.data, k) == v for k, v in criteria.items())]


def test_second_payment_at_same_merchant_gets_category_from_first(uow, db_session):
    service = ImportService(uow)
    service.import_pko_xml(fixture_bytes(WEEK41))
    [first] = find(uow, merchant="JMP S.A. BIEDRONKA 2422")
    groceries = category_id(db_session, "Spożywcze")
    uow.transactions.set_classification(
        first.id, Classification(type=TxType.WYDATEK, category_id=groceries, source=ProposalSource.USER, confirmed=True)
    )
    service.import_pko_xml(fixture_bytes(OVERLAP))
    [second] = [t for t in find(uow, merchant="JMP S.A. BIEDRONKA 2422") if t.id != first.id]

    previous = uow.transactions.last_confirmed_like(CounterpartyKey.of(second.data), exclude_id=second.id)
    assert previous is not None and previous.id == first.id
    proposal = history_proposal(previous)
    assert proposal.type is TxType.WYDATEK
    assert proposal.category_id == groceries
    assert proposal.source is ProposalSource.HISTORY
    assert not proposal.confirmed
    assert "2026-10-05" in proposal.reason


def test_counterparty_account_has_priority_and_direction_must_match(uow):
    service = ImportService(uow)
    service.import_pko_xml(fixture_bytes(WEEK41))
    [income] = find(uow, amount=Money.parse("4250.00"))
    uow.transactions.set_classification(income.id, Classification(type=TxType.DOCHOD, confirmed=True))

    service.import_pko_xml(fixture_bytes(OVERLAP))
    [later] = find(uow, amount=Money.parse("3100.00"))
    key = CounterpartyKey.of(later.data)
    assert key.account == "12114020040000310212345678"
    assert uow.transactions.last_confirmed_like(key, exclude_id=later.id).id == income.id

    # Ten sam kontrahent, ale wydatek: historia wpływów nie jest brana pod uwagę.
    outgoing = TransactionData(
        source=TxSource.MANUAL,
        transaction_date=date(2026, 10, 20),
        amount=Money.parse("-10.00"),
        counterparty_account="12 1140 2004 0000 3102 1234 5678",
    )
    assert CounterpartyKey.of(outgoing).direction is Direction.OUT
    assert uow.transactions.last_confirmed_like(CounterpartyKey.of(outgoing)) is None


def test_name_match_ignores_case_and_polish_characters(uow):
    first = uow.transactions.add(
        TransactionData(source=TxSource.MANUAL, transaction_date=date(2026, 10, 6), amount=Money.parse("-20.00"),
                        merchant="Kawiarnia  Żółw"),
        Classification(type=TxType.WYDATEK, category_id=None, confirmed=True),
    )
    later = TransactionData(source=TxSource.MANUAL, transaction_date=date(2026, 10, 13), amount=Money.parse("-18.00"),
                            merchant="KAWIARNIA ZOLW")
    assert uow.transactions.last_confirmed_like(CounterpartyKey.of(later)).id == first.id


def test_unconfirmed_transactions_are_not_history(uow):
    uow.transactions.add(
        TransactionData(source=TxSource.MANUAL, transaction_date=date(2026, 10, 6), amount=Money.parse("-20.00"),
                        merchant="SKLEP X"),
        Classification(type=TxType.WYDATEK, source=ProposalSource.LLM, confirmed=False),
    )
    later = TransactionData(source=TxSource.MANUAL, transaction_date=date(2026, 10, 13), amount=Money.parse("-18.00"),
                            merchant="SKLEP X")
    assert uow.transactions.last_confirmed_like(CounterpartyKey.of(later)) is None

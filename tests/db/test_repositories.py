from datetime import date, datetime, timezone

import pytest
from sqlalchemy.exc import IntegrityError

from finbro.domain.enums import ProposalSource, SettlementStatus, TxSource, TxType
from finbro.domain.money import Money
from finbro.domain.periods import IsoWeek
from finbro.domain.settlement import Settlement, SettlementLine
from finbro.domain.transactions import Classification, Direction, TransactionData
from finbro.services.uow import UnitOfWork


@pytest.fixture
def uow(db_session):
    return UnitOfWork(db_session)


def sample_data(**overrides):
    values = dict(
        source=TxSource.IMPORT,
        transaction_date=date(2026, 10, 10),
        booking_date=date(2026, 10, 12),
        amount=Money.parse("-7.00"),
        balance_after=Money.parse("6351.56"),
        occurrence=1,
        bank_type="Płatność kartą",
        raw_description="Lokalizacja : Adres : SKLEP TESTOWY Miasto : WARSZAWA Kraj : POLSKA",
        merchant="SKLEP TESTOWY",
        city="WARSZAWA",
        country="POLSKA",
        extra={"Numer karty": "4246 **** **** 0000"},
    )
    values.update(overrides)
    return TransactionData(**values)


def test_transaction_roundtrip(uow):
    saved = uow.transactions.add(sample_data())
    loaded = uow.transactions.get(saved.id)
    assert loaded.data == sample_data()
    assert loaded.amount == Money(-700)
    assert loaded.direction is Direction.OUT
    assert loaded.classification == Classification()


def test_transaction_with_classification(uow):
    saved = uow.transactions.add(
        sample_data(),
        Classification(type=TxType.WYDATEK, source=ProposalSource.LLM, reason="sklep spożywczy", confirmed=True),
    )
    assert saved.classification.type is TxType.WYDATEK
    assert saved.classification.source is ProposalSource.LLM
    assert saved.classification.is_final

    confirmed_at = datetime(2026, 10, 12, 9, 0, tzinfo=timezone.utc)
    updated = uow.transactions.set_classification(
        saved.id,
        Classification(type=TxType.DOCHOD, confirmed=True, confirmed_at=confirmed_at, settlement_week=date(2026, 10, 5)),
    )
    assert updated.classification.type is TxType.DOCHOD
    assert updated.classification.settlement_week == date(2026, 10, 5)
    assert updated.classification.confirmed_at == confirmed_at


def test_list_between_filters_by_transaction_date(uow):
    inside = uow.transactions.add(sample_data(transaction_date=date(2026, 10, 11), occurrence=1))
    uow.transactions.add(sample_data(transaction_date=date(2026, 10, 12), occurrence=2))
    found = uow.transactions.list_between(date(2026, 10, 5), date(2026, 10, 11))
    assert [t.id for t in found] == [inside.id]


def test_fingerprint_is_unique(uow, db_session):
    from finbro.db import models
    from finbro.domain.enums import AccountKind

    account = models.Account(code="test", name="Konto testowe", kind=AccountKind.BANK)
    db_session.add(account)
    db_session.flush()
    uow.transactions.add(sample_data(account_id=account.id))
    # Inne saldo po operacji albo inny numer wystąpienia to inna transakcja.
    uow.transactions.add(sample_data(account_id=account.id, balance_after=Money.parse("6344.56")))
    uow.transactions.add(sample_data(account_id=account.id, occurrence=2))
    with pytest.raises(IntegrityError):
        uow.transactions.add(sample_data(account_id=account.id))


def test_confirmed_classification_requires_type(uow):
    saved = uow.transactions.add(sample_data())
    with pytest.raises(IntegrityError):
        uow.transactions.set_classification(saved.id, Classification(confirmed=True))


def test_settlement_roundtrip(uow, db_session):
    from finbro.db import models

    envelopes = [models.Envelope(code=f"k{i}", name=f"Koperta {i}") for i in range(2)]
    db_session.add_all(envelopes)
    db_session.flush()

    week = IsoWeek(2026, 41)
    assert uow.settlements.get(week) is None
    closed_at = datetime(2026, 10, 12, 8, 0, tzinfo=timezone.utc)
    saved = uow.settlements.save_closed(
        Settlement(
            week=week,
            status=SettlementStatus.CLOSED,
            closed_at=closed_at,
            lines=(
                SettlementLine(envelopes[0].id, Money(61875), Money(0), Money(3750)),
                SettlementLine(envelopes[1].id, Money(123750), Money(-5000), Money(0)),
            ),
        )
    )
    loaded = uow.settlements.get(week)
    assert loaded == saved
    assert loaded.status is SettlementStatus.CLOSED
    assert loaded.line_for(envelopes[0].id).to_transfer == Money(65625)
    assert loaded.line_for(envelopes[1].id).to_transfer == Money(118750)

    with pytest.raises(ValueError):
        uow.settlements.save_closed(loaded)

    uow.settlements.set_status(week, SettlementStatus.SETTLED)
    assert uow.settlements.get(week).status is SettlementStatus.SETTLED
    assert [s.week for s in uow.settlements.list_all()] == [week]

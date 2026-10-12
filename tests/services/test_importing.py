from datetime import date

import pytest
from sqlalchemy import func, select

from finbro.db import models
from finbro.domain.money import Money
from finbro.services.importing import ImportRejected, ImportService

from tests.helpers import OVERLAP, WEEK41, fixture_bytes


def count(db_session, model) -> int:
    return db_session.scalar(select(func.count()).select_from(model))


def test_first_import_saves_booked_operations(uow, db_session):
    result = ImportService(uow).import_pko_xml(fixture_bytes(WEEK41), "wyciag.xml")
    assert result.new_count == 14
    assert result.existing_count == 0
    assert result.skipped_count == 1
    assert (result.date_from, result.date_to) == (date(2026, 10, 5), date(2026, 10, 11))
    assert count(db_session, models.Transaction) == 14

    [batch] = uow.imports.batches()
    assert (batch.new_count, batch.existing_count, batch.skipped_count) == (14, 0, 1)
    assert batch.filename == "wyciag.xml"

    saved = uow.transactions.get(result.new_transaction_ids[0])
    assert saved.data.source.value == "IMPORT"
    assert saved.data.raw_description


def test_overlapping_import_does_not_duplicate(uow, db_session):
    service = ImportService(uow)
    service.import_pko_xml(fixture_bytes(WEEK41))
    second = service.import_pko_xml(fixture_bytes(OVERLAP))
    # 08–11.10: 8 operacji już było; nowe to zaksięgowana blokada i 5 operacji z 12–16.10.
    assert second.existing_count == 8
    assert second.new_count == 6
    assert second.skipped_count == 0
    assert count(db_session, models.Transaction) == 20

    again = service.import_pko_xml(fixture_bytes(OVERLAP))
    assert (again.new_count, again.existing_count) == (0, 14)
    assert count(db_session, models.Transaction) == 20


def test_two_identical_payments_are_both_saved(uow, db_session):
    ImportService(uow).import_pko_xml(fixture_bytes(WEEK41))
    balances = db_session.scalars(
        select(models.Transaction.balance_after).where(
            models.Transaction.merchant == "ZABKA Z8627 K.1", models.Transaction.amount == -700
        )
    ).all()
    assert sorted(balances) == [634456, 635156]


def test_same_fingerprint_within_file_uses_occurrence(uow, db_session):
    # +X, -X, +X tego samego dnia: pierwsza i trzecia operacja mają ten sam odcisk.
    ops = [("+100.00", "+1100.00"), ("-100.00", "+1000.00"), ("+100.00", "+1100.00")]
    body = "".join(
        f"<operation><exec-date>2026-10-07</exec-date><order-date>2026-10-07</order-date>"
        f"<type>Przelew na konto</type><description>Tytuł : test</description>"
        f'<amount curr="PLN">{amount}</amount><ending-balance curr="PLN">{balance}</ending-balance></operation>'
        for amount, balance in reversed(ops)
    )
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?><account-history><search>'
        "<account>27 1020 1026 0000 1234 5678 9012</account>"
        f'<date since="2026-10-07" to="2026-10-07"/></search><operations>{body}</operations></account-history>'
    ).encode()
    service = ImportService(uow)
    assert service.import_pko_xml(xml).new_count == 3
    assert service.import_pko_xml(xml).new_count == 0
    occurrences = db_session.scalars(
        select(models.Transaction.occurrence).where(models.Transaction.amount == 10000)
    ).all()
    assert sorted(occurrences) == [1, 2]


def test_statement_from_other_account_is_rejected(uow, db_session):
    with pytest.raises(ImportRejected, match="rachunku"):
        ImportService(uow).import_pko_xml(fixture_bytes("pko_inny_rachunek.xml"))
    assert count(db_session, models.Transaction) == 0
    assert count(db_session, models.ImportBatch) == 0


@pytest.mark.parametrize("name", ["pko_uszkodzony.xml", "nie_ipko.xml", "wyciag.csv"])
def test_broken_or_unsupported_file_saves_nothing(uow, db_session, name):
    with pytest.raises(ImportRejected):
        ImportService(uow).import_pko_xml(fixture_bytes(name))
    assert count(db_session, models.Transaction) == 0
    assert count(db_session, models.ImportBatch) == 0


def test_import_is_atomic_when_a_later_step_fails(uow, db_session, monkeypatch):
    service = ImportService(uow)

    def boom(result):
        raise RuntimeError("awaria po zapisie transakcji")

    monkeypatch.setattr(service, "after_import", boom)
    with pytest.raises(RuntimeError):
        service.import_pko_xml(fixture_bytes(WEEK41))
    assert count(db_session, models.Transaction) == 0
    assert count(db_session, models.ImportBatch) == 0


def test_missing_main_account_configuration(uow, db_session):
    uow.reference.update_config(main_account_number=None)
    uow.commit()
    with pytest.raises(ImportRejected, match="Ustawieniach"):
        ImportService(uow).import_pko_xml(fixture_bytes(WEEK41))


def test_amounts_are_exact(uow, db_session):
    ImportService(uow).import_pko_xml(fixture_bytes(WEEK41))
    total = db_session.scalar(select(func.sum(models.Transaction.amount)))
    # Saldo końcowe 8384,98 minus saldo początkowe 5000,00.
    assert Money(int(total)) == Money.parse("3384.98")

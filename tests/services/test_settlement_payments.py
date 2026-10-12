from datetime import date

import pytest
from sqlalchemy import update

from finbro.db import models
from finbro.domain.enums import SettlementStatus, TxSource, TxType
from finbro.domain.money import Money
from finbro.domain.periods import IsoWeek
from finbro.domain.settlement import parse_transfer_title, transfer_title
from finbro.domain.transactions import TransactionData
from finbro.services.classification import ClassificationService, Decision
from finbro.services.importing import ImportService
from finbro.services.settlement import SettlementService
from tests.helpers import OVERLAP, fixture_bytes

T41, T42 = IsoWeek(2026, 41), IsoWeek(2026, 42)
M = Money.parse
TARGETS = {
    "wakacje": "LT62 3250 0000 1111 2222",
    "xtb": "52 1050 0000 3333 4444 5555 6666",
    "obligacje": "71 1020 1097 0000 7777 8888 9999",
}


@pytest.fixture
def closed_t41(uow, db_session):
    """T41 zamknięte z dochodami 4950,03 zł: XTB 618,75, Obligacje 618,75, Wakacje 1237,50."""
    for code, account in TARGETS.items():
        db_session.execute(update(models.Envelope).where(models.Envelope.code == code).values(target_account=account))
    pko = uow.reference.account("pko")
    tx = uow.transactions.add(TransactionData(source=TxSource.MANUAL, account_id=pko.id, transaction_date=date(2026, 10, 7),
                                              amount=M("4950.03"), counterparty_name="KLIENT"))
    ClassificationService(uow).decide(tx.id, Decision(type=TxType.DOCHOD))
    return SettlementService(uow).close(T41, today=date(2026, 10, 12))


def lines(week_settlement):
    return {e.code: week_settlement.line(e) for e in week_settlement.envelopes}


def payment_tx(uow, title: str | None, account: str, amount: str, day=date(2026, 10, 19)):
    pko = uow.reference.account("pko")
    return uow.transactions.add(
        TransactionData(source=TxSource.IMPORT, account_id=pko.id, transaction_date=day, booking_date=day,
                        amount=-M(amount), title=title, counterparty_account=account, balance_after=M("1.00"),
                        occurrence=1)
    )


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("FinBro 2026-T41 Wakacje", (T41, "wakacje")),
        ("FinBro  2026-T41   Wakacje", (T41, "wakacje")),
        ("finbro 2026-t41 xtb", (T41, "xtb")),
        ("Przelew: FINBRO 2026-T7 OBLIGACJE za tydzień", (IsoWeek(2026, 7), "obligacje")),
        ("FinBro 2026-T41 Wakacje".replace("Wakacje", "Wakacjé"), (T41, "wakacje")),
        ("FinBro 2025-T53 XTB", None),  # 2025 nie ma tygodnia 53
        ("zakup obligacji", None),
        (None, None),
    ],
)
def test_parse_transfer_title(title, expected):
    assert parse_transfer_title(title) == expected


def test_transfer_title_format():
    assert transfer_title(T41, "Wakacje") == "FinBro 2026-T41 Wakacje"


def test_import_matches_transfers_and_carries_differences(uow, closed_t41):
    assert closed_t41.settlement.status is SettlementStatus.CLOSED
    ImportService(uow).import_pko_xml(fixture_bytes(OVERLAP))
    service = SettlementService(uow)
    t41 = service.compute(T41)
    t41_lines = lines(t41)

    # Tytuł z podwójną spacją: Wakacje 1200,00; tytuł małymi literami: XTB 700,00; bez tytułu na rachunek Obligacji.
    assert t41.paid(t41_lines["wakacje"]) == M("1200.00")
    assert t41.paid(t41_lines["xtb"]) == M("700.00")
    assert t41.paid(t41_lines["obligacje"]) == M("618.75")
    assert t41.settlement.status is SettlementStatus.CLOSED  # Wakacje niedopłacone

    txs = uow.transactions.list_between(date(2026, 10, 12), date(2026, 10, 13))
    savings = [t for t in txs if t.classification.type is TxType.ODKLADANIE]
    assert len(savings) == 3 and all(t.classification.confirmed and t.classification.envelope_id for t in savings)

    t42_lines = lines(service.compute(T42))
    assert t42_lines["wakacje"].carryover == M("37.50")
    assert t42_lines["xtb"].carryover == M("-81.25")
    assert t42_lines["obligacje"].carryover == Money.zero()


def test_payment_without_title_covers_oldest_shortfall_and_settles(uow, closed_t41):
    ImportService(uow).import_pko_xml(fixture_bytes(OVERLAP))
    topup = payment_tx(uow, None, TARGETS["wakacje"], "37.50")
    SettlementService(uow).recognize_transfers([topup.id])
    t41 = SettlementService(uow).compute(T41)
    assert t41.paid(lines(t41)["wakacje"]) == M("1237.50")
    assert t41.settlement.status is SettlementStatus.SETTLED


def test_all_transfers_with_titles_settle_the_week(uow, closed_t41):
    ids = [
        payment_tx(uow, "FinBro 2026-T41 Wakacje", TARGETS["wakacje"], "1237.50").id,
        payment_tx(uow, "FinBro 2026-T41 XTB", TARGETS["xtb"], "618.75", day=date(2026, 10, 20)).id,
        payment_tx(uow, "FinBro 2026-T41 Obligacje", "11 2222 3333 4444 5555 6666 7777", "618.75", day=date(2026, 10, 21)).id,
    ]
    service = SettlementService(uow)
    assert service.recognize_transfers(ids) == 3
    assert uow.settlements.get(T41).status is SettlementStatus.SETTLED


def test_manual_reclassification_as_savings_is_counted(uow, closed_t41, db_session):
    revolut_topup = payment_tx(uow, None, None, "1237.50")
    holiday = next(e for e in uow.reference.envelopes() if e.code == "wakacje")
    ClassificationService(uow).decide(revolut_topup.id, Decision(type=TxType.ODKLADANIE, envelope_id=holiday.id))
    t41 = SettlementService(uow).compute(T41)
    assert t41.paid(lines(t41)["wakacje"]) == M("1237.50")
    # Zmiana z ODKŁADANIA na inny typ usuwa przypisanie.
    ClassificationService(uow).decide(revolut_topup.id, Decision(type=TxType.TRANSFER))
    t41 = SettlementService(uow).compute(T41)
    assert t41.paid(lines(t41)["wakacje"]) == Money.zero()


def test_closing_next_week_settles_previous_shortfall(uow, closed_t41):
    ImportService(uow).import_pko_xml(fixture_bytes(OVERLAP))
    [income] = [t for t in uow.transactions.list_between(date(2026, 10, 16), date(2026, 10, 16)) if t.amount == M("3100.00")]
    ClassificationService(uow).decide(income.id, Decision(type=TxType.DOCHOD))
    service = SettlementService(uow)
    assert uow.settlements.get(T41).status is SettlementStatus.CLOSED
    service.close(T42, today=date(2026, 10, 19))
    assert uow.settlements.get(T41).status is SettlementStatus.SETTLED  # niedopłata przeszła do T42
    t42 = service.compute(T42)
    assert lines(t42)["wakacje"].to_transfer == M("37.50") + M("775.00")  # przeniesienie + 25% z 3100,00

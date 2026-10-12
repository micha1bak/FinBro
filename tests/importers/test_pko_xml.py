from datetime import date
from pathlib import Path

import pytest

from finbro.domain.money import Money
from finbro.domain.periods import IsoWeek
from finbro.domain.transactions import Direction
from finbro.importers.pko_xml import (
    OPERATION_ID_KEY,
    ImportFormatError,
    parse_description,
    parse_statement,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "pko"
WEEK41 = FIXTURES / "pko_2026-10-05_2026-10-11.xml"


@pytest.fixture(scope="module")
def statement():
    return parse_statement(WEEK41.read_bytes())


def find(statement, predicate):
    matches = [op for op in statement.operations if predicate(op)]
    assert len(matches) == 1, matches
    return matches[0]


def test_statement_header(statement):
    assert statement.account_number == "27 1020 1026 0000 1234 5678 9012"
    assert statement.date_from == date(2026, 10, 5)
    assert statement.date_to == date(2026, 10, 11)
    assert len(statement.operations) == 15
    assert len(statement.booked) == 14


def test_operations_in_chronological_booking_order(statement):
    booked = statement.booked
    assert booked[0].amount == Money.parse("4250.00")
    assert booked[-1].ending_balance == Money.parse("8384.98")


def test_card_payment_booked_later_keeps_transaction_date(statement):
    op = find(statement, lambda o: o.fields.merchant == "RESTAURACJA POD TESTEM")
    assert op.order_date == date(2026, 10, 10)
    assert op.exec_date == date(2026, 10, 12)
    week = IsoWeek.of(op.order_date)
    assert (week.start, week.end) == (date(2026, 10, 5), date(2026, 10, 11))


def test_pending_operation_without_exec_date(statement):
    [pending] = statement.pending
    assert pending.exec_date is None
    assert pending.ending_balance is None
    assert pending.fields.merchant == "ALLEGRO SP. Z O.O."


def test_misleading_type_direction_from_sign(statement):
    op = find(statement, lambda o: o.bank_type == "Przelew na telefon przychodz. zew.")
    assert op.amount == Money.parse("-645.00")
    assert op.direction is Direction.OUT
    assert abs(op.amount).format() == "645,00 zł"


def test_card_payment_location_fields(statement):
    op = find(statement, lambda o: o.fields.merchant == "JMP S.A. BIEDRONKA 2422")
    assert op.fields.city == "WARSZAWA"
    assert op.fields.country == "POLSKA"
    assert op.fields.extra[OPERATION_ID_KEY] == "000498849 74230786283"
    assert op.fields.extra["Numer karty"] == "425125******0042"
    assert op.fields.extra["Oryginalna kwota operacji"] == "54.30 PLN"


def test_incoming_transfer_fields(statement):
    op = find(statement, lambda o: o.amount == Money.parse("4250.00"))
    assert op.direction is Direction.IN
    assert op.fields.counterparty_account == "12 1140 2004 0000 3102 1234 5678"
    assert op.fields.counterparty_name == "KANCELARIA PRAWNA LEX SP. Z O.O."
    assert op.fields.counterparty_address == "UL. TESTOWA 1 00-001 WARSZAWA"
    assert op.fields.title == "zgodnie z umową zlecenie 09/2026"


def test_phone_transfer_fields(statement):
    op = find(statement, lambda o: o.bank_type.startswith("Przelew na telefon"))
    assert op.fields.counterparty_name == "MARTYNA TESTOWA"
    assert op.fields.title == "przelew na telefon"
    assert op.fields.reference_number == "99887766554"
    assert op.fields.extra["Numer telefonu"] == "+48 600 100 200"


def test_unknown_label_keeps_known_fields_and_raw_description(statement):
    op = find(statement, lambda o: "Kod MCC" in o.description)
    assert op.fields.merchant == "ORLEN STACJA NR 123"
    assert op.fields.city == "LOMIANKI"
    assert op.fields.country == "POLSKA"
    assert op.description.endswith("Kod MCC : 5541")


def test_two_identical_payments_have_different_balances(statement):
    ops = [o for o in statement.operations if o.fields.merchant == "ZABKA Z8627 K.1"]
    assert [o.amount for o in ops] == [Money(-700), Money(-700)]
    assert {o.ending_balance for o in ops} == {Money.parse("6351.56"), Money.parse("6344.56")}


def test_revolut_card_transfer(statement):
    op = find(statement, lambda o: o.bank_type == "Przelew z karty")
    assert op.fields.merchant == "Revolut**4321*"
    assert op.fields.country == "IRLANDIA"


def test_masked_account_in_overlapping_statement():
    statement = parse_statement((FIXTURES / "pko_2026-10-08_2026-10-18.xml").read_bytes())
    assert "*" in statement.account_number
    assert statement.date_from == date(2026, 10, 8)
    titles = [o.fields.title for o in statement.operations if o.fields.title]
    assert "FinBro 2026-T41 Wakacje" in titles  # wielokrotne spacje są normalizowane


@pytest.mark.parametrize("name", ["wyciag.csv", "nie_ipko.xml", "pko_uszkodzony.xml"])
def test_unsupported_or_broken_files_are_rejected(name):
    with pytest.raises(ImportFormatError):
        parse_statement((FIXTURES / name).read_bytes())


def test_html_and_doctype_are_rejected():
    with pytest.raises(ImportFormatError):
        parse_statement(b"<html><body>wyciag</body></html>")
    with pytest.raises(ImportFormatError):
        parse_statement(b'<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "b">]><account-history/>')


def test_missing_balance_for_booked_operation_is_an_error():
    xml = WEEK41.read_text(encoding="utf-8").replace('<ending-balance curr="PLN">+9250.00</ending-balance>', "")
    with pytest.raises(ImportFormatError, match="salda"):
        parse_statement(xml.encode("utf-8"))


def test_parse_description_without_labels():
    fields = parse_description("  OPŁATA   ZA KARTĘ ")
    assert fields.extra == {OPERATION_ID_KEY: "OPŁATA ZA KARTĘ"}
    assert fields.title is None


def test_parse_description_prefers_longer_labels():
    fields = parse_description("Nazwa odbiorcy : JAN Adres odbiorcy : UL. X 1 Tytuł : czynsz")
    assert fields.counterparty_name == "JAN"
    assert fields.counterparty_address == "UL. X 1"
    assert fields.merchant is None
    assert fields.title == "czynsz"

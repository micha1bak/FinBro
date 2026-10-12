import json
import re
from datetime import date

import pytest

from finbro.domain.enums import TxSource
from finbro.domain.money import Money
from finbro.domain.transactions import Transaction, TransactionData
from finbro.importers.pko_xml import parse_description
from finbro.llm.view import REDACTED, build_view, redact_numbers

DESCRIPTION = (
    "Rachunek odbiorcy : 44 1090 0000 0000 0001 2345 6789 Nazwa odbiorcy : MARTYNA TESTOWA "
    "Tytuł : zwrot 600 100 200 za bilety, konto PL44109000000000000123456789 "
    "Numer telefonu : +48 600 100 200 Numer referencyjny : 99887766554"
)


def tx_from_description() -> Transaction:
    f = parse_description(DESCRIPTION)
    data = TransactionData(
        source=TxSource.IMPORT,
        transaction_date=date(2026, 10, 6),
        amount=Money.parse("-645.00"),
        balance_after=Money.parse("8550.70"),
        bank_type="Przelew na telefon przychodz. zew.",
        raw_description=DESCRIPTION,
        counterparty_name=f.counterparty_name,
        counterparty_account=f.counterparty_account,
        title=f.title,
        reference_number=f.reference_number,
        extra=f.extra,
    )
    return Transaction(id=1, data=data)


def test_view_contains_only_allowed_fields():
    view = build_view(tx_from_description())
    assert set(view.as_dict()) == {"bank_type", "direction", "amount", "date", "counterparty", "title"}
    assert view.direction == "wydatek"
    assert view.amount == "645,00 zł"
    assert view.counterparty == "MARTYNA TESTOWA"


def test_account_phone_card_and_balance_are_not_sent():
    payload = json.dumps(build_view(tx_from_description()).as_dict(), ensure_ascii=False)
    digits_only = re.sub(r"\D", "", payload)
    assert "44109000000000000123456789" not in digits_only
    assert "600100200" not in digits_only
    assert "99887766554" not in digits_only
    assert "8550" not in payload  # saldo
    assert "zwrot" in payload and "za bilety" in payload
    assert REDACTED in payload


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("faktura 15/10/2026", "faktura 15/10/2026"),
        ("zlecenie 09/2026 z dnia 2026-10-05", "zlecenie 09/2026 z dnia 2026-10-05"),
        ("ZABKA Z8627 K.1", "ZABKA Z8627 K.1"),
        ("karta 425125******0042", f"karta {REDACTED}"),
        ("tel. 600-100-200", f"tel. {REDACTED}"),
        ("na konto 27 1020 1026 0000 1234 5678 9012 dzięki", f"na konto {REDACTED} dzięki"),
        (None, None),
    ],
)
def test_redact_numbers(text, expected):
    assert redact_numbers(text) == expected

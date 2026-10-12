from datetime import date

import pytest

from finbro.domain.classification import ClassificationError
from finbro.domain.enums import TxType
from finbro.domain.money import Money
from finbro.services.classification import ClassificationService, Decision
from finbro.services.receivables import ReceivablesService
from finbro.services.uow import UnitOfWork
from finbro.services.wallet import WalletService
from tests.helpers import WEEK41
from tests.web.test_inbox import HTMX, tx_by


def debtor_id_of(session_factory, name: str) -> int:
    uow = UnitOfWork(session_factory())
    try:
        return uow.reference.debtor_by_name(name).id
    finally:
        uow.close()


def balance_of(session_factory, name: str) -> Money:
    uow = UnitOfWork(session_factory())
    try:
        debtor = uow.reference.debtor_by_name(name)
        return ReceivablesService(uow).of(debtor.id).balance
    finally:
        uow.close()


@pytest.fixture
def martyna_owes_1290(client, upload, session_factory):
    """BLIK 645,00 zł jako pożyczka dla Martyny i pożyczka gotówkowa 645,00 zł: saldo 1290,00 zł."""
    upload(WEEK41)
    blik = tx_by(session_factory, bank_type="Przelew na telefon przychodz. zew.")
    client.post(f"/inbox/{blik.id}/decide", data={"type": "POZYCZKA", "new_debtor_name": "Martyna"}, headers=HTMX)
    client.post("/wallet/receivable", data={"kind": "loan", "new_debtor_name": "Martyna", "date": "2026-10-08", "amount": "645"})
    assert balance_of(session_factory, "Martyna") == Money.parse("1290.00")


def test_inflow_from_debtor_shows_repayment_suggestion_with_balance(client, martyna_owes_1290, session_factory):
    repayment = tx_by(session_factory, amount=Money.parse("500.00"))
    html = client.get("/inbox").text
    row = html.split(f'id="tx-{repayment.id}"')[1].split("</tr>")[0]
    assert "Możliwa SPŁATA od <strong>Martyna</strong> (saldo 1290,00" in row
    # Inny wpływ (od kancelarii) nie dostaje tej podpowiedzi.
    other = tx_by(session_factory, amount=Money.parse("4250.00"))
    assert "Możliwa SPŁATA" not in html.split(f'id="tx-{other.id}"')[1].split("</tr>")[0]


def test_accepting_repayment_reduces_balance(client, martyna_owes_1290, session_factory):
    repayment = tx_by(session_factory, amount=Money.parse("500.00"))
    debtor_id = debtor_id_of(session_factory, "Martyna")
    response = client.post(f"/inbox/{repayment.id}/decide", data={"type": "SPLATA", "debtor_id": str(debtor_id)}, headers=HTMX)
    assert response.text == ""
    assert balance_of(session_factory, "Martyna") == Money.parse("790.00")
    c = tx_by(session_factory, amount=Money.parse("500.00")).classification
    assert (c.type, c.debtor_id, c.confirmed) == (TxType.SPLATA, debtor_id, True)


def test_repayment_greater_than_balance_is_rejected(uow):
    wallet = WalletService(uow)
    wallet.add_cash_loan(date(2026, 10, 6), Money.parse("200.00"), None, "Kuba")
    kuba = uow.reference.debtor_by_name("Kuba")
    wallet.add_cash_repayment(date(2026, 10, 7), Money.parse("50.00"), kuba.id)
    assert ReceivablesService(uow).of(kuba.id).balance == Money.parse("150.00")
    with pytest.raises(ClassificationError, match="Kuba ma saldo 150,00"):
        wallet.add_cash_repayment(date(2026, 10, 8), Money.parse("300.00"), kuba.id)
    assert ReceivablesService(uow).of(kuba.id).balance == Money.parse("150.00")


def test_removing_a_loan_cannot_make_balance_negative(uow):
    wallet = WalletService(uow)
    loan = wallet.add_cash_loan(date(2026, 10, 6), Money.parse("200.00"), None, "Kuba")
    kuba = uow.reference.debtor_by_name("Kuba")
    wallet.add_cash_repayment(date(2026, 10, 7), Money.parse("150.00"), kuba.id)
    with pytest.raises(ClassificationError, match="ujemne saldo"):
        ClassificationService(uow).decide(loan.id, Decision(type=TxType.WYDATEK, category_id=1))


def test_cash_loan_and_repayment_change_wallet(uow):
    wallet = WalletService(uow)
    wallet.set_opening_balance(Money.parse("500.00"), date(2026, 10, 5))
    wallet.add_cash_loan(date(2026, 10, 6), Money.parse("200.00"), None, "Kuba")
    assert wallet.expected(date(2026, 10, 11)) == Money.parse("300.00")
    wallet.add_cash_repayment(date(2026, 10, 9), Money.parse("50.00"), uow.reference.debtor_by_name("Kuba").id)
    assert wallet.expected(date(2026, 10, 11)) == Money.parse("350.00")

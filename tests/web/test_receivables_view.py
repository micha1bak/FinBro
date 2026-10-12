import re
from datetime import date

from finbro.domain.enums import TxSource, TxType
from finbro.domain.money import Money
from finbro.services.uow import UnitOfWork
from finbro.services.wallet import WalletService
from tests.web.test_inbox import category_id, tx_by


def setup_debts(session_factory):
    """Martyna ma saldo 1290,00 zł, a Kuba 150,00 zł."""
    uow = UnitOfWork(session_factory())
    wallet = WalletService(uow)
    wallet.add_cash_loan(date(2026, 10, 1), Money.parse("1290.00"), None, "Martyna")
    wallet.add_cash_loan(date(2026, 10, 6), Money.parse("200.00"), None, "Kuba")
    kuba = uow.reference.debtor_by_name("Kuba")
    wallet.add_cash_repayment(date(2026, 10, 8), Money.parse("50.00"), kuba.id)
    ids = {"Martyna": uow.reference.debtor_by_name("Martyna").id, "Kuba": kuba.id}
    uow.close()
    return ids


def money_in(html: str, element_id: str) -> Money:
    value = re.search(rf'id="{element_id}">([^<]+)<', html).group(1)
    return Money.parse(value.replace("zł", "").strip())


def test_list_with_balances_oldest_loan_and_total(client, configured, session_factory):
    setup_debts(session_factory)
    html = client.get("/receivables").text
    assert money_in(html, "receivables-total") == Money.parse("1440.00")
    martyna = html.split('data-debtor="Martyna"')[1].split("</tr>")[0]
    assert "1290,00" in martyna and "2026-10-01" in martyna
    kuba = html.split('data-debtor="Kuba"')[1].split("</tr>")[0]
    assert "150,00" in kuba and "2026-10-06" in kuba


def test_debtor_history(client, configured, session_factory):
    ids = setup_debts(session_factory)
    html = client.get(f"/receivables/{ids['Kuba']}").text
    assert money_in(html, "debtor-balance") == Money.parse("150.00")
    assert "pożyczka" in html and "spłata" in html


def test_forgive_remaining_debt(client, configured, session_factory, db_session):
    ids = setup_debts(session_factory)
    gifts = category_id(db_session, "Prezenty")
    response = client.post(
        f"/receivables/{ids['Kuba']}/forgive", data={"amount": "150,00", "category_id": str(gifts), "date": "2026-11-15"}
    )
    assert response.status_code == 200
    assert money_in(response.text, "debtor-balance") == Money.zero()
    assert money_in(client.get("/receivables").text, "receivables-total") == Money.parse("1290.00")
    assert 'data-debtor="Kuba"' not in client.get("/receivables").text

    expense = tx_by(session_factory, source=TxSource.FORGIVENESS)
    c = expense.classification
    assert (expense.amount, expense.transaction_date) == (Money.parse("-150.00"), date(2026, 11, 15))
    assert (c.type, c.category_id, c.debtor_id, c.confirmed) == (TxType.WYDATEK, gifts, ids["Kuba"], True)
    assert expense.data.account_id is None


def test_cannot_forgive_more_than_balance(client, configured, session_factory, db_session):
    ids = setup_debts(session_factory)
    gifts = category_id(db_session, "Prezenty")
    response = client.post(
        f"/receivables/{ids['Kuba']}/forgive", data={"amount": "200", "category_id": str(gifts), "date": "2026-11-15"}
    )
    assert response.status_code == 400
    assert "saldo 150,00" in response.text

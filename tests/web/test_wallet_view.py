import re
from datetime import date

from finbro.domain.enums import ProposalSource, TxType
from finbro.domain.money import Money
from tests.web.test_inbox import category_id, tx_by

AT = "2026-10-11"


def expected(client, at: str = AT) -> Money:
    html = client.get(f"/wallet?at={at}").text
    value = re.search(r'id="wallet-expected">([^<]+)<', html).group(1)
    return Money.parse(value.replace("zł", "").strip())


def test_opening_balance_is_neutral(client, configured):
    response = client.post("/wallet/opening", data={"date": "2026-10-05", "amount": "500,00"}, follow_redirects=False)
    assert response.status_code == 303
    assert expected(client) == Money.parse("500.00")


def test_cash_income_is_confirmed_income(client, configured, session_factory):
    client.post("/wallet/opening", data={"date": "2026-10-05", "amount": "500"})
    response = client.post("/wallet/income", data={"date": "2026-10-07", "amount": "800,00", "note": "gotówka od klienta"})
    assert response.status_code == 200 and "Zapisano dochód gotówkowy" in response.text
    assert expected(client) == Money.parse("1300.00")
    income = tx_by(session_factory, note="gotówka od klienta")
    c = income.classification
    assert (income.amount, c.type, c.confirmed, c.source) == (Money.parse("800.00"), TxType.DOCHOD, True, ProposalSource.USER)
    assert income.transaction_date == date(2026, 10, 7)
    # Nie trafia do skrzynki.
    assert f'id="tx-{income.id}"' not in client.get("/inbox").text


def test_cash_expense_with_category(client, configured, session_factory, db_session):
    client.post("/wallet/opening", data={"date": "2026-10-05", "amount": "500"})
    restaurants = category_id(db_session, "Restauracje i na mieście")
    client.post("/wallet/expense", data={"date": "2026-10-08", "amount": "120", "category_id": str(restaurants), "note": "kolacja"})
    assert expected(client) == Money.parse("380.00")
    expense = tx_by(session_factory, note="kolacja")
    assert (expense.amount, expense.classification.type, expense.classification.category_id) == (
        Money.parse("-120.00"), TxType.WYDATEK, restaurants)
    # Wpis jest widoczny tylko od swojej daty.
    assert expected(client, "2026-10-07") == Money.parse("500.00")


def test_invalid_entries_are_rejected(client, configured):
    assert client.post("/wallet/expense", data={"date": "2026-10-08", "amount": "120"}).status_code == 400
    assert client.post("/wallet/income", data={"date": "2026-10-08", "amount": "-5"}).status_code == 400
    assert client.post("/wallet/income", data={"date": "2026-10-08", "amount": "abc"}).status_code == 400
    assert client.post("/wallet/opening", data={"date": "2026-10-05", "amount": "-1"}).status_code == 400

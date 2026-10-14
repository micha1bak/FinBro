from datetime import date

from finbro.domain.money import Money
from finbro.services.incomes import IncomeService


def test_save_accounts_shows_on_transfer_list(client, db_session):
    response = client.post("/settings/accounts", data={"WAKACJE": "LT00 1111 2222", "XTB": " 52 1050  0000 ", "OBLIGACJE": ""},
                           follow_redirects=False)
    assert response.status_code == 303
    page = client.get("/settings?saved=accounts").text
    assert 'id="saved"' in page and 'value="52 1050 0000"' in page

    IncomeService(db_session).add(date(2026, 10, 14), "Zlecenie", Money.parse("174"))
    transfers = client.get("/settlement").text
    xtb = transfers.split('<tr data-envelope="XTB">')[1].split("</tr>")[0]
    assert "52 1050 0000" in xtb
    assert "missing-account" in transfers.split('<tr data-envelope="OBLIGACJE">')[1].split("</tr>")[0]

    client.post("/settings/accounts", data={"WAKACJE": "", "XTB": "52 1050 0000", "OBLIGACJE": ""})
    assert "LT00 1111 2222" not in client.get("/settings").text


def test_add_plan_and_list(client):
    page = client.get("/settings").text
    assert 'name="XTB" value="12,5"' in page
    response = client.post("/settings/plan", data={"effective_from": "2026-11-01", "PKO": "60", "WAKACJE": "20", "XTB": "10", "OBLIGACJE": "10"},
                           follow_redirects=False)
    assert response.status_code == 303
    plans = client.get("/settings").text.split('id="plans"')[1]
    assert plans.index("2026-11-01") < plans.index("2000-01-01")
    assert "60%" in plans and "12,5%" in plans


def test_plan_not_summing_to_100_is_rejected(client):
    response = client.post("/settings/plan", data={"effective_from": "2026-11-01", "PKO": "50", "WAKACJE": "20", "XTB": "12,5", "OBLIGACJE": "12,5"})
    assert response.status_code == 400
    assert "95%" in response.text and 'value="20"' in response.text
    response = client.post("/settings/plan", data={"effective_from": "2026-11-01", "PKO": "abc", "WAKACJE": "25", "XTB": "12,5", "OBLIGACJE": "12,5"})
    assert response.status_code == 400 and "Niepoprawny udział" in response.text

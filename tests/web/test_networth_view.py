import json
from datetime import date

from finbro.domain.envelopes import Envelope
from finbro.domain.money import NBSP, Money
from finbro.services.networth import NetWorthService
from tests.services.test_networth import settle_two_incomes


def value(html: str, element_id: str) -> str:
    return html.split(f'id="{element_id}">')[1].split("<")[0]


def test_empty_view_encourages_initial_balances(client):
    page = client.get("/networth").text
    assert 'id="start"' in page and 'id="networth-chart"' not in page


def test_record_balance_and_difference(client, db_session):
    NetWorthService(db_session).record(Envelope.XTB, date(2026, 10, 12), Money.parse("1200"))
    settle_two_incomes(db_session)
    response = client.post("/networth/balance", data={"account": "XTB", "date": "2026-11-01", "amount": "1560,00"},
                           follow_redirects=False)
    assert response.status_code == 303
    page = client.get(response.headers["location"]).text
    assert value(page, "difference") == f"+38,00{NBSP}zł"
    assert "zysk" in page
    assert value(page, "balance-XTB") == f"1560,00{NBSP}zł"
    assert value(page, "balance-PKO") == "–"


def test_totals_and_chart_data(client, db_session):
    networth = NetWorthService(db_session)
    networth.record(Envelope.PKO, date(2026, 10, 12), Money.parse("3000"))
    networth.record(Envelope.XTB, date(2026, 10, 12), Money.parse("1200"))
    networth.record(Envelope.OBLIGACJE, date(2026, 10, 12), Money.parse("1088,25"))
    settle_two_incomes(db_session)
    page = client.get("/networth").text
    assert value(page, "total") == f"5932,25{NBSP}zł"
    assert "Wakacje" not in page.split('class="cards"')[1].split("</form>")[0].split("<form")[0]
    chart = json.loads(page.split('id="chart-data">')[1].split("</script>")[0])
    assert chart == {"labels": ["2026-10-12", "2026-10-19"], "totals": [5288.25, 5932.25]}


def test_invalid_balance(client):
    response = client.post("/networth/balance", data={"account": "XTB", "date": "2026-11-01", "amount": "-5"})
    assert response.status_code == 400 and "ujemne" in response.text
    response = client.post("/networth/balance", data={"account": "WAKACJE", "date": "2026-11-01", "amount": "5"})
    assert response.status_code == 400 and "PKO, XTB i Obligacji" in response.text
    response = client.post("/networth/balance", data={"account": "XTB", "date": "", "amount": "5"})
    assert response.status_code == 400 and "RRRR-MM-DD" in response.text

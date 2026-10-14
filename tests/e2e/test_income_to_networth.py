"""Od dochodów do majątku wyłącznie przez widoki aplikacji.

Ustawienia -> saldo początkowe XTB -> dwa dochody -> lista przelewów -> rozliczenie ->
saldo XTB rośnie o 322 zł -> cofnięcie rozliczenia przywraca stan.
"""

import re

from finbro.domain.money import NBSP


def value(html: str, element_id: str) -> str:
    return html.split(f'id="{element_id}">')[1].split("<")[0]


def settle_form(html: str) -> dict[str, list[str]]:
    form = html.split('class="settle-form"')[1].split("</form>")[0]
    fields: dict[str, list[str]] = {}
    for name, field_value in re.findall(r'name="([^"]+)" value="([^"]*)"', form):
        fields.setdefault(name, []).append(field_value)
    return fields


def test_incomes_settlement_and_net_worth(client):
    client.post("/settings/accounts", data={"WAKACJE": "LT00 1111 2222", "XTB": "52 1050 0000", "OBLIGACJE": "71 1020 0000"})
    client.post("/networth/balance", data={"account": "XTB", "date": "2026-10-01", "amount": "1200,00"})
    assert value(client.get("/networth").text, "balance-XTB") == f"1200,00{NBSP}zł"

    client.post("/incomes", data={"date": "2026-10-05", "source": "Stypendium", "amount": "2401,30"})
    client.post("/incomes", data={"date": "2026-10-14", "source": "Zlecenie", "amount": "174,00"})
    assert value(client.get("/?month=2026-10").text, "total") == f"2575,30{NBSP}zł"

    page = client.get("/settlement").text
    xtb = page.split('<tr data-envelope="XTB">')[1].split("</tr>")[0]
    assert "322,00" in xtb and "52 1050 0000" in xtb
    response = client.post("/settlement", data=settle_form(page), follow_redirects=False)
    assert response.status_code == 303
    assert 'id="nothing"' in client.get("/settlement").text
    assert client.get("/?month=2026-10").text.count(">rozliczony<") == 2

    networth = client.get("/networth").text
    assert value(networth, "balance-XTB") == f"1522,00{NBSP}zł"
    assert value(networth, "balance-OBLIGACJE") == f"322,00{NBSP}zł"
    assert value(networth, "balance-PKO") == "–"

    settlement_id = re.search(r'id="settlement-(\d+)"', client.get("/settlement").text).group(1)
    client.post(f"/settlement/{settlement_id}/undo")
    assert value(client.get("/networth").text, "balance-XTB") == f"1200,00{NBSP}zł"
    assert client.get("/?month=2026-10").text.count(">do rozliczenia<") == 2

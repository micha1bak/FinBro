"""Poniedziałkowe rozliczenie od początku do końca, wyłącznie przez widoki aplikacji.

Import T41 -> decyzje w skrzynce -> gotówka i inwentaryzacja -> zamknięcie T41 ->
import kolejnego tygodnia z przelewami FinBro -> rozliczenie T41 ma status "rozliczone".
"""

import re

from sqlalchemy import select

from finbro.db import models
from finbro.domain.money import Money
from tests.helpers import WEEK41, fixture_bytes

HTMX = {"HX-Request": "true"}
NEXT_WEEK = "pko_2026-10-12_2026-10-18.xml"
TARGETS = {
    "xtb": "52 1050 0000 3333 4444 5555 6666",
    "obligacje": "71 1020 1097 0000 7777 8888 9999",
    "wakacje": "LT62 3250 0000 1111 2222",
}


def money_in(html: str, element_id: str) -> Money:
    value = re.search(rf'id="{element_id}">([^<]+)<', html).group(1)
    return Money.parse(value.replace("zł", "").strip())


def upload(client, name):
    response = client.post("/import", files={"file": (name, fixture_bytes(name), "application/xml")})
    assert response.status_code == 200, response.text
    return response


def inbox_row(html: str, text: str) -> tuple[int, str]:
    """Id i kod HTML wiersza skrzynki, który zawiera podany tekst."""
    for chunk in html.split('<tr id="tx-')[1:]:
        row = chunk.split("</tr>")[0]
        if text in row:
            return int(row.split('"')[0]), row
    raise AssertionError(f"Brak w skrzynce: {text}")


def row_id(html: str, text: str) -> int:
    return inbox_row(html, text)[0]


def test_monday_settlement_end_to_end(client, db_session):
    # Pierwsza konfiguracja w panelu ustawień.
    response = client.post(
        "/admin/app-settings/edit/1",
        data={"start_date": "2026-10-05", "main_account_number": "27 1020 1026 0000 1234 5678 9012", "llm_model": "", "save": "Save"},
        follow_redirects=False,
    )
    assert response.status_code == 302
    for code, account in TARGETS.items():
        envelope = db_session.scalar(select(models.Envelope).where(models.Envelope.code == code))
        response = client.post(
            f"/admin/envelope/edit/{envelope.id}",
            data={"name": envelope.name, "target_account": account, "save": "Save"},
            follow_redirects=False,
        )
        assert response.status_code == 302

    # Import tygodnia T41.
    summary = upload(client, WEEK41).text
    assert 'data-count="new">14<' in summary

    # Decyzje w skrzynce.
    inbox = client.get("/inbox").text
    decisions = [
        ("KANCELARIA PRAWNA LEX", {"type": "DOCHOD", "remember": "on"}),
        ("STUDIO GRAFICZNE PIKSEL", {"type": "DOCHOD"}),
        ("ANNA KOWALSKA-TESTOWA", {"type": "TRANSFER", "transfer_kind": "FAMILY", "remember": "on"}),
        ("przelew na telefon", {"type": "POZYCZKA", "new_debtor_name": "Martyna"}),
    ]
    for text, form in decisions:
        assert client.post(f"/inbox/{row_id(inbox, text)}/decide", data=form, headers=HTMX).text == ""
    groceries = db_session.scalar(select(models.Category.id).where(models.Category.name == "Spożywcze"))
    client.post(f"/inbox/{row_id(inbox, 'BIEDRONKA')}/decide", data={"type": "WYDATEK", "category_id": str(groceries)}, headers=HTMX)

    # Wpływ od Martyny: podpowiedź SPŁATY i przyjęcie jej jednym kliknięciem.
    inbox = client.get("/inbox").text
    repayment_id, repayment_row = inbox_row(inbox, "oddaję część")
    assert "Możliwa SPŁATA od <strong>Martyna</strong> (saldo 645,00" in repayment_row
    debtor_id = re.search(r'name="debtor_id" value="(\d+)"', repayment_row).group(1)
    decided = client.post(f"/inbox/{repayment_id}/decide", data={"type": "SPLATA", "debtor_id": debtor_id}, headers=HTMX)
    assert decided.text == ""

    # Gotówka: stan początkowy, dochód gotówkowy i inwentaryzacja na koniec tygodnia.
    client.post("/wallet/opening", data={"date": "2026-10-05", "amount": "500"})
    client.post("/wallet/income", data={"date": "2026-10-07", "amount": "800,00", "note": "gotówka od klienta"})
    wallet = client.get("/wallet?at=2026-10-11").text
    assert money_in(wallet, "wallet-expected") == Money.parse("2600.00")  # 500 + 800 + 2300 - 1000
    client.post("/wallet/inventory", data={"date": "2026-10-11", "amount": "2540,00"})

    # Zamknięcie T41 bez ostrzeżeń.
    page = client.get("/settlement?week=2026-T41").text
    assert 'id="close-warnings"' not in page
    closed = client.post("/settlement/close", data={"week": "2026-T41", "confirm": "1"}).text
    assert 'id="settlement-status">zamknięte' in closed
    transfers = closed.split('id="transfers"')[1].split("</table>")[0]
    for code, amount, title in [
        ("xtb", "719,48", "FinBro 2026-T41 XTB"),
        ("obligacje", "719,48", "FinBro 2026-T41 Obligacje"),
        ("wakacje", "1438,96", "FinBro 2026-T41 Wakacje"),
    ]:
        row = transfers.split(f'data-envelope="{code}"')[1].split("</tr>")[0]
        assert amount in row and title in row and TARGETS[code] in row

    # Import kolejnego tygodnia z wykonanymi przelewami: rozliczenie T41 jest rozliczone.
    upload(client, NEXT_WEEK)
    settled = client.get("/settlement?week=2026-T41").text
    assert 'id="settlement-status">rozliczone' in settled
    assert settled.count("wykonany") == 3
    # Wpływ od kancelarii w T42 dostał propozycję DOCHODU z reguły zapamiętanej w skrzynce.
    _, income_row = inbox_row(client.get("/inbox").text, "zlecenie 10/2026")
    assert "<strong>DOCHÓD</strong>" in income_row and "źródło: reguła" in income_row

    # Raport tygodniowy T41.
    report = client.get("/reports?kind=week&period=2026-T41").text
    assert money_in(report, "sum-income") == Money.parse("5755.87")  # 4250,00 + 705,87 + 800,00
    assert money_in(report, "sum-expenses") == Money.parse("114.30")  # Biedronka 54,30 + niedobór gotówki 60,00
    categories = report.split('id="categories"')[1].split("</table>")[0]
    assert "Gotówka (bez kategorii)" in categories and "Spożywcze" in categories

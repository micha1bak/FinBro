from datetime import date

from finbro.domain.money import NBSP

from finbro.db.models import Income
from finbro.domain.money import Money
from finbro.services.incomes import IncomeService
from tests.services.test_incomes import settle


def cell(html: str, row_id: str, envelope: str) -> str:
    row = html.split(f'id="{row_id}"')[1].split("</tr>")[0]
    return row.split(f'data-envelope="{envelope}">')[1].split("<")[0]


def test_add_income_and_month_summary(client):
    for day, source, amount in [("2026-10-05", "Stypendium", "2401,30"), ("2026-10-14", "Zlecenie", "174")]:
        response = client.post("/incomes", data={"date": day, "source": source, "amount": amount}, follow_redirects=False)
        assert response.status_code == 303
        assert response.headers["location"] == "/?month=2026-10"

    page = client.get("/?month=2026-10").text
    assert 'id="month">październik 2026<' in page
    assert page.index("Zlecenie") < page.index("Stypendium")  # od najnowszych
    assert f'id="total">2575,30{NBSP}zł<' in page
    totals = {e: cell(page, "month-total", e) for e in ["PKO", "WAKACJE", "XTB", "OBLIGACJE"]}
    assert totals == {"PKO": f"1287,30{NBSP}zł", "WAKACJE": f"644,00{NBSP}zł", "XTB": f"322,00{NBSP}zł", "OBLIGACJE": f"322,00{NBSP}zł"}
    assert "do rozliczenia" in page


def test_invalid_income_shows_error_and_keeps_input(client, db_session):
    response = client.post("/incomes", data={"date": "2026-10-14", "source": "Zlecenie", "amount": "0"})
    assert response.status_code == 400
    assert 'id="error">Kwota dochodu musi być większa od zera.<' in response.text
    assert 'value="Zlecenie"' in response.text
    response = client.post("/incomes", data={"date": "2026-10-14", "source": "Zlecenie", "amount": "abc"})
    assert response.status_code == 400 and "podaj kwotę" in response.text
    assert db_session.query(Income).count() == 0


def test_edit_and_delete_unsettled_income(client, db_session):
    view = IncomeService(db_session).add(date(2026, 10, 14), "Zlecenie", Money.parse("174"))
    form = client.get(f"/incomes/{view.id}/edit").text
    assert 'value="174,00"' in form
    client.post(f"/incomes/{view.id}", data={"date": "2026-10-14", "source": "Zlecenie", "amount": "210,00"})
    page = client.get("/?month=2026-10").text
    assert cell(page, f"income-{view.id}", "WAKACJE") == f"53,00{NBSP}zł"
    client.post(f"/incomes/{view.id}/delete")
    assert 'id="empty"' in client.get("/?month=2026-10").text


def test_settled_income_cannot_be_edited(client, db_session):
    service = IncomeService(db_session)
    view = service.add(date(2026, 10, 14), "Zlecenie", Money.parse("174"))
    settle(db_session, service, view.id)
    page = client.get("/?month=2026-10").text
    assert "rozliczony" in page and f"/incomes/{view.id}/edit" not in page
    response = client.post(f"/incomes/{view.id}", data={"date": "2026-10-14", "source": "Zlecenie", "amount": "200"})
    assert response.status_code == 400 and "najpierw cofnij rozliczenie" in response.text
    response = client.post(f"/incomes/{view.id}/delete")
    assert response.status_code == 400 and "najpierw cofnij rozliczenie" in response.text


def test_navigation_links(client):
    page = client.get("/?month=2026-01").text
    assert 'href="/?month=2025-12"' in page and 'href="/?month=2026-02"' in page
    for href in ["/settlement", "/networth", "/settings"]:
        assert f'href="{href}"' in page


def test_cash_income_and_sums_by_form(client):
    page = client.get("/").text
    assert 'value="PKO" checked' in page and 'value="GOTOWKA">' in page  # domyślnie PKO
    client.post("/incomes", data={"date": "2026-10-05", "source": "Stypendium", "amount": "2401,30"})
    client.post("/incomes", data={"date": "2026-10-14", "source": "Korepetycje", "amount": "174", "form": "GOTOWKA"})
    page = client.get("/?month=2026-10").text
    cash_row = page.split("Korepetycje")[1].split("</tr>")[0]
    assert 'data-form="GOTOWKA">gotówka<' in cash_row
    assert 'data-form="PKO">PKO<' in page.split("Stypendium")[1].split("</tr>")[0]
    by_form = page.split('id="by-form"')[1].split("</p>")[0]
    assert f"PKO: <strong>2401,30{NBSP}zł</strong>" in by_form
    assert f"gotówka: <strong>174,00{NBSP}zł</strong>" in by_form


def test_change_form_when_editing(client, db_session):
    view = IncomeService(db_session).add(date(2026, 10, 14), "Zlecenie", Money.parse("174"))
    assert 'value="PKO" checked' in client.get(f"/incomes/{view.id}/edit").text
    client.post(f"/incomes/{view.id}", data={"date": "2026-10-14", "source": "Zlecenie", "amount": "174", "form": "GOTOWKA"})
    assert 'value="GOTOWKA" checked' in client.get(f"/incomes/{view.id}/edit").text
    response = client.post(f"/incomes/{view.id}", data={"date": "2026-10-14", "source": "Zlecenie", "amount": "174", "form": "KARTA"})
    assert response.status_code == 400 and "wybierz PKO albo gotówkę" in response.text

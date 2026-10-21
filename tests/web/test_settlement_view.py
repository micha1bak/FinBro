import re
from datetime import date

from finbro.db.models import EnvelopeAccount
from finbro.domain.money import NBSP, Money
from finbro.services.incomes import IncomeService
from tests.web.test_incomes_view import cell

TODAY = date.today().isoformat()


def add_two_incomes(db_session):
    service = IncomeService(db_session)
    service.add(date(2026, 10, 5), "Stypendium", Money.parse("2401,30"))
    service.add(date(2026, 10, 14), "Zlecenie", Money.parse("174"))


def row(html: str, envelope: str) -> str:
    return html.split(f'<tr data-envelope="{envelope}">')[1].split("</tr>")[0]


def settle_form(html: str) -> dict[str, list[str]]:
    form = html.split('class="settle-form"')[1].split("</form>")[0]
    fields: dict[str, list[str]] = {}
    for name, value in re.findall(r'name="([^"]+)" value="([^"]*)"', form):
        fields.setdefault(name, []).append(value)
    return fields


def test_transfer_list_with_accounts_and_warning(client, db_session):
    add_two_incomes(db_session)
    db_session.add(EnvelopeAccount(envelope="XTB", target_account="52 1050 0000 1111 2222 3333 4444"))
    db_session.commit()
    page = client.get("/settlement").text
    xtb = row(page, "XTB")
    assert "322,00" in xtb and "52 1050 0000 1111 2222 3333 4444" in xtb and f"FinBro XTB {TODAY}" in xtb
    assert "644,00" in row(page, "WAKACJE") and "missing-account" in row(page, "WAKACJE")
    assert 'data-envelope="PKO"' not in page
    assert f"2575,30{NBSP}zł" in page


def test_nothing_to_transfer(client):
    page = client.get("/settlement").text
    assert 'id="nothing"' in page and 'id="settle"' not in page


def test_settle_and_undo(client, db_session):
    add_two_incomes(db_session)
    response = client.post("/settlement", data=settle_form(client.get("/settlement").text), follow_redirects=False)
    assert response.status_code == 303
    page = client.get(response.headers["location"]).text
    assert 'id="done"' in page and 'id="nothing"' in page
    history = page.split('id="history"')[1]
    assert "644,00" in history and "Cofnij" in history
    assert "rozliczony" in client.get("/?month=2026-10").text

    settlement_id = re.search(r'id="settlement-(\d+)"', history).group(1)
    client.post(f"/settlement/{settlement_id}/undo")
    page = client.get("/settlement").text
    assert 'id="settle"' in page and "Brak rozliczeń" in page


def test_stale_form_is_rejected(client, db_session):
    add_two_incomes(db_session)
    form = settle_form(client.get("/settlement").text)
    IncomeService(db_session).add(date(2026, 10, 15), "Nowy", Money.parse("100"))
    client.post("/settlement", data=form)  # rozlicza tylko wyświetlone dochody
    response = client.post("/settlement", data=form)
    assert response.status_code == 400 and "Odśwież widok" in response.text
    assert [i for i in client.get("/settlement").text.split("<li>")[1:] if "Nowy" in i]


def test_undo_of_older_settlement_is_refused(client, db_session):
    add_two_incomes(db_session)
    client.post("/settlement", data=settle_form(client.get("/settlement").text))
    IncomeService(db_session).add(date(2026, 10, 15), "Nowy", Money.parse("100"))
    client.post("/settlement", data=settle_form(client.get("/settlement").text))
    ids = re.findall(r'id="settlement-(\d+)"', client.get("/settlement").text)
    response = client.post(f"/settlement/{ids[-1]}/undo")
    assert response.status_code == 400 and "najnowsze" in response.text


def test_transfers_are_rounded_from_the_sum_of_incomes(client, db_session):
    service = IncomeService(db_session)
    earlier = service.add(date(2026, 10, 14), "Zlecenie", Money.parse("174"))
    later = service.add(date(2026, 10, 15), "Zlecenie", Money.parse("174"))
    page = client.get("/settlement").text
    assert "87,00" in row(page, "WAKACJE") and "44,00" in row(page, "XTB") and 'id="pooled"' in page

    client.post("/settlement", data=settle_form(page))
    incomes = client.get("/?month=2026-10").text
    assert cell(incomes, f"income-{earlier.id}", "WAKACJE") == f"44,00{NBSP}zł"
    assert cell(incomes, f"income-{later.id}", "WAKACJE") == f"43,00{NBSP}zł"
    assert cell(incomes, "month-total", "WAKACJE") == f"87,00{NBSP}zł"

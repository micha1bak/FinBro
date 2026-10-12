from datetime import date

from sqlalchemy import update

from finbro.db import models
from finbro.domain.periods import IsoWeek
from finbro.web.routes.settlement import default_week

REVOLUT = "LT62 3250 0000 1111 2222"


def test_default_week_on_monday_is_previous_week():
    assert default_week(date(2026, 10, 12)) == IsoWeek(2026, 41)
    assert default_week(date(2026, 10, 18)) == IsoWeek(2026, 41)


def setup_income(client, session_factory, db_session):
    db_session.execute(update(models.Envelope).where(models.Envelope.code == "wakacje").values(target_account=REVOLUT))
    db_session.commit()
    client.post("/wallet/income", data={"date": "2026-10-07", "amount": "4950,03", "note": "zlecenie"})


def test_close_t41_shows_three_transfers_with_titles(client, configured, session_factory, db_session):
    setup_income(client, session_factory, db_session)
    page = client.get("/settlement?week=2026-T41").text
    assert "otwarte" in page and "zamykam mimo ostrzeżeń" in page  # brak importu i inwentaryzacji

    rejected = client.post("/settlement/close", data={"week": "2026-T41"})
    assert rejected.status_code == 400 and "Potwierdź" in rejected.text

    response = client.post("/settlement/close", data={"week": "2026-T41", "confirm": "1"})
    assert response.status_code == 200
    html = response.text
    assert 'id="settlement-status">zamknięte' in html
    transfers = html.split('id="transfers"')[1].split("</table>")[0]
    assert transfers.count("<tr data-envelope=") == 3
    holiday = transfers.split('data-envelope="wakacje"')[1].split("</tr>")[0]
    assert "FinBro 2026-T41 Wakacje" in holiday
    assert "1237,50" in holiday and REVOLUT in holiday
    assert "FinBro 2026-T41 XTB" in transfers and "FinBro 2026-T41 Obligacje" in transfers
    assert "Ustawieniach" in transfers  # XTB i Obligacje bez rachunku docelowego


def test_running_week_cannot_be_closed_from_view(client, configured):
    week = IsoWeek.of(date.today())
    page = client.get(f"/settlement?week={week.label}").text
    assert "Tydzień jeszcze trwa" in page
    response = client.post("/settlement/close", data={"week": week.label, "confirm": "1"})
    assert response.status_code == 400 and "jeszcze trwa" in response.text

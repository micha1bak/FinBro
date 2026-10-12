from datetime import date

from finbro.domain.enums import TxType
from finbro.web.routes.transactions import filter_from_query
from tests.helpers import WEEK41
from tests.web.test_inbox import HTMX, category_id, tx_by

OCTOBER = "from=2026-10-01&to=2026-10-31"


def test_change_expense_category_visible_in_list(client, upload, session_factory, db_session):
    upload(WEEK41)
    payment = tx_by(session_factory, merchant="RESTAURACJA POD TESTEM")
    groceries = category_id(db_session, "Spożywcze")
    restaurants = category_id(db_session, "Restauracje i na mieście")
    client.post(f"/transactions/{payment.id}/classify", data={"type": "WYDATEK", "category_id": str(groceries)}, headers=HTMX)

    response = client.post(
        f"/transactions/{payment.id}/classify", data={"type": "WYDATEK", "category_id": str(restaurants)}, headers=HTMX
    )
    assert response.status_code == 200
    assert "Restauracje i na mieście" in response.text and "zatwierdzona" in response.text

    listing = client.get(f"/transactions?{OCTOBER}&q=RESTAURACJA")
    assert f'id="tx-{payment.id}"' in listing.text
    row = listing.text.split(f'id="tx-{payment.id}"')[1].split("</tr>")[0]
    assert "Restauracje i na mieście" in row
    c = tx_by(session_factory, merchant="RESTAURACJA POD TESTEM").classification
    assert (c.type, c.category_id, c.confirmed) == (TxType.WYDATEK, restaurants, True)


def test_filters(client, upload, session_factory):
    upload(WEEK41)
    all_rows = client.get(f"/transactions?{OCTOBER}").text
    assert all_rows.count('<tr id="tx-') == 14
    transfers = client.get(f"/transactions?{OCTOBER}&type=TRANSFER").text
    assert transfers.count('<tr id="tx-') == 3
    unconfirmed = client.get(f"/transactions?{OCTOBER}&unconfirmed=1").text
    assert unconfirmed.count('<tr id="tx-') == 11
    one_day = client.get("/transactions?from=2026-10-06&to=2026-10-06").text
    assert one_day.count('<tr id="tx-') == 2
    zabka = client.get(f"/transactions?{OCTOBER}&q=zabka").text
    assert zabka.count('<tr id="tx-') == 2


def test_invalid_change_reports_error(client, upload, session_factory):
    upload(WEEK41)
    atm = tx_by(session_factory, bank_type="Wypłata w bankomacie")
    response = client.post(f"/transactions/{atm.id}/classify", data={"type": "ZWROT"}, headers=HTMX)
    assert "nie pasuje do kierunku" in response.text
    assert tx_by(session_factory, bank_type="Wypłata w bankomacie").classification.type is TxType.TRANSFER


def test_default_filter_is_current_month():
    f = filter_from_query({}, today=date(2026, 10, 12))
    assert (f.date_from, f.date_to) == (date(2026, 10, 1), date(2026, 10, 31))
    f = filter_from_query({"type": "nonsense", "category_id": "x", "from": "zła data"}, today=date(2026, 10, 12))
    assert f.type is None and f.category_id is None and f.date_from == date(2026, 10, 1)

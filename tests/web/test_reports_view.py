import json
import re
from datetime import date

from finbro.domain.enums import TxSource
from finbro.domain.money import Money
from finbro.domain.transactions import TransactionData
from finbro.services.uow import UnitOfWork
from tests.helpers import WEEK41
from tests.web.test_inbox import HTMX, category_id, tx_by


def money_in(html: str, element_id: str) -> Money:
    value = re.search(rf'id="{element_id}">([^<]+)<', html).group(1)
    return Money.parse(value.replace("zł", "").strip())


def prepare(client, upload, session_factory, db_session):
    upload(WEEK41)
    groceries = category_id(db_session, "Spożywcze")
    restaurants = category_id(db_session, "Restauracje i na mieście")
    for amount in ("4250.00", "705.87"):
        tx = tx_by(session_factory, amount=Money.parse(amount))
        client.post(f"/inbox/{tx.id}/decide", data={"type": "DOCHOD"}, headers=HTMX)
    biedronka = tx_by(session_factory, merchant="JMP S.A. BIEDRONKA 2422")
    client.post(f"/inbox/{biedronka.id}/decide", data={"type": "WYDATEK", "category_id": str(groceries)}, headers=HTMX)
    restaurant = tx_by(session_factory, merchant="RESTAURACJA POD TESTEM")
    client.post(f"/inbox/{restaurant.id}/decide", data={"type": "WYDATEK", "category_id": str(restaurants)}, headers=HTMX)
    client.post("/wallet/expense", data={"date": "2026-10-09", "amount": "120", "category_id": str(restaurants), "note": "kolacja"})


def test_month_report_sums(client, upload, session_factory, db_session):
    prepare(client, upload, session_factory, db_session)
    html = client.get("/reports?kind=month&period=2026-10").text
    assert money_in(html, "sum-income") == Money.parse("4955.87")
    assert money_in(html, "sum-expenses") == Money.parse("294.75")  # 54,30 + 120,45 + 120,00
    assert money_in(html, "sum-balance") == Money.parse("4661.12")

    categories = html.split('id="categories"')[1].split("</table>")[0]
    assert categories.index("Restauracje i na mieście") < categories.index("Spożywcze")
    assert "81,58%" in categories and "18,42%" in categories

    ranking = html.split('id="counterparties"')[1].split("</table>")[0]
    assert ranking.index("RESTAURACJA POD TESTEM") < ranking.index("JMP S.A. BIEDRONKA 2422")

    # Nieskategoryzowane i niezatwierdzone pozycje są sygnalizowane.
    assert 'id="incomplete"' in html

    chart = json.loads(html.split('id="trend-data">')[1].split("</script>")[0])
    assert chart["labels"][-1] == "2026-10" and len(chart["labels"]) == 12
    assert chart["income"][-1] == 4955.87 and chart["expenses"][-1] == 294.75


def test_week_and_year_views(client, upload, session_factory, db_session):
    prepare(client, upload, session_factory, db_session)
    week = client.get("/reports?kind=week&period=2026-T41").text
    assert money_in(week, "sum-income") == Money.parse("4955.87")
    assert "2026-T40" in week and "2026-T42" in week  # nawigacja
    previous = client.get("/reports?kind=week&period=2026-T40").text
    assert money_in(previous, "sum-income") == Money.zero()
    year = client.get("/reports?kind=year&period=2026").text
    assert money_in(year, "sum-expenses") == Money.parse("294.75")
    assert client.get("/reports?kind=nonsense&period=x").status_code == 200


def test_incomplete_notice_with_single_unconfirmed_inflow(client, configured, session_factory):
    uow = UnitOfWork(session_factory())
    pko = uow.reference.account("pko")
    uow.transactions.add(TransactionData(source=TxSource.MANUAL, account_id=pko.id, transaction_date=date(2026, 10, 7),
                                         amount=Money.parse("477.08"), counterparty_name="ANNA"))
    uow.commit()
    uow.close()
    html = client.get("/reports?kind=week&period=2026-T41").text
    notice = html.split('id="incomplete"')[1].split("</div>")[0]
    assert "<strong>1</strong>" in notice and "477,08" in notice
    assert money_in(html, "sum-income") == Money.zero()

from finbro.domain.money import Money
from finbro.services.llm_jobs import LlmJobService
from finbro.services.uow import UnitOfWork
from tests.helpers import WEEK41
from tests.services.test_llm_worker import FakeClassifier
from tests.web.test_inbox import tx_by


def enable_llm(session_factory, model="atrapa"):
    uow = UnitOfWork(session_factory())
    uow.reference.update_config(llm_model=model)
    uow.commit()
    uow.close()


def test_inbox_works_without_llm(client, upload, session_factory):
    upload(WEEK41)
    response = client.get("/inbox")
    assert response.status_code == 200
    assert "model językowy wyłączony" in response.text
    assert "hx-trigger=\"every" not in response.text


def test_pending_rows_poll_until_proposal_arrives(client, upload, session_factory):
    enable_llm(session_factory)
    upload(WEEK41)
    income = tx_by(session_factory, amount=Money.parse("4250.00"))
    groceries = tx_by(session_factory, merchant="JMP S.A. BIEDRONKA 2422")

    page = client.get("/inbox").text
    assert 'id="llm-status"' in page
    row = page.split(f'id="tx-{income.id}"')[1].split("</tr>")[0]
    assert f'hx-get="/inbox/{income.id}/row"' in row and "czeka na propozycję" in row

    LlmJobService(session_factory, lambda _uow: FakeClassifier()).process_all()

    refreshed = client.get(f"/inbox/{income.id}/row").text
    assert "DOCHÓD" in refreshed and "model językowy" in refreshed
    assert "hx-trigger" not in refreshed  # odświeżanie się kończy
    # Wydatek z propozycją modelu jest przyjęty automatycznie i znika ze skrzynki.
    assert client.get(f"/inbox/{groceries.id}/row").text == ""
    assert 'id="llm-status"' not in client.get("/inbox").text

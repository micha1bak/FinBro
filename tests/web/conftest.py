from datetime import date

import pytest

from finbro.services.uow import UnitOfWork
from tests.helpers import MAIN_ACCOUNT, fixture_bytes


@pytest.fixture
def configured(session_factory):
    """Konto główne i data startu ustawione przed testem widoku."""
    uow = UnitOfWork(session_factory())
    uow.reference.update_config(main_account_number=MAIN_ACCOUNT, start_date=date(2026, 10, 5))
    uow.commit()
    uow.close()


@pytest.fixture
def upload(client, configured):
    def do(name: str):
        response = client.post("/import", files={"file": (name, fixture_bytes(name), "application/xml")})
        assert response.status_code == 200, response.text
        return response

    return do


HTMX = {"HX-Request": "true"}

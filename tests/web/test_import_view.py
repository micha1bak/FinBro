import re
from datetime import date

import pytest

from finbro.services.uow import UnitOfWork
from finbro.web.routes.imports import MAX_UPLOAD_BYTES
from tests.helpers import MAIN_ACCOUNT, OVERLAP, WEEK41, fixture_bytes


@pytest.fixture(autouse=True)
def configured(session_factory):
    uow = UnitOfWork(session_factory())
    uow.reference.update_config(main_account_number=MAIN_ACCOUNT, start_date=date(2026, 10, 5))
    uow.commit()
    uow.close()


def counts(html: str) -> dict[str, int]:
    return {k: int(v) for k, v in re.findall(r'data-count="(\w+)">(\d+)<', html)}


def upload(client, name: str):
    return client.post("/import", files={"file": (name, fixture_bytes(name), "application/xml")})


def test_import_form(client):
    response = client.get("/import")
    assert response.status_code == 200
    assert 'type="file"' in response.text


def test_upload_shows_summary(client):
    response = upload(client, WEEK41)
    assert response.status_code == 200
    assert counts(response.text) == {"new": 14, "existing": 0, "skipped": 1}
    assert "2026-10-05 – 2026-10-11" in response.text


def test_second_upload_shows_existing(client):
    upload(client, WEEK41)
    response = upload(client, OVERLAP)
    assert counts(response.text) == {"new": 6, "existing": 8, "skipped": 0}


def test_gap_is_listed(client):
    upload(client, WEEK41)
    late = (
        '<?xml version="1.0" encoding="UTF-8"?><account-history><search>'
        "<account>27 1020 1026 0000 1234 5678 9012</account>"
        '<date since="2026-10-19" to="2026-10-25"/></search><operations/></account-history>'
    ).encode()
    response = client.post("/import", files={"file": ("pozny.xml", late, "application/xml")})
    gaps = re.search(r'<ul id="coverage-gaps">(.*?)</ul>', response.text, re.S)
    assert gaps and "2026-10-12 – 2026-10-18" in gaps.group(1)


def test_rejected_upload_shows_error(client):
    response = upload(client, "pko_inny_rachunek.xml")
    assert response.status_code == 400
    assert "Import odrzucony" in response.text


def test_too_large_upload_is_rejected_before_parsing(client):
    response = client.post(
        "/import",
        content=b"x" * 10,
        headers={"content-type": "multipart/form-data; boundary=x", "content-length": str(MAX_UPLOAD_BYTES + 1)},
    )
    assert response.status_code == 413

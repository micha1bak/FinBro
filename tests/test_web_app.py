from fastapi.testclient import TestClient

from finbro.config import Settings
from finbro.web.app import create_app

UNREACHABLE_DATABASE_URL = "postgresql+psycopg://finbro:x@127.0.0.1:1/finbro"


def test_index_page(db_engine, test_database_url):
    client = TestClient(create_app(Settings(database_url=test_database_url)))
    response = client.get("/")
    assert response.status_code == 200
    assert "FinBro" in response.text


def test_health_ok_with_database(db_engine, test_database_url):
    client = TestClient(create_app(Settings(database_url=test_database_url)))
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}


def test_health_503_when_database_unreachable():
    client = TestClient(create_app(Settings(database_url=UNREACHABLE_DATABASE_URL)))
    response = client.get("/health")
    assert response.status_code == 503
    assert response.json()["database"] == "unavailable"

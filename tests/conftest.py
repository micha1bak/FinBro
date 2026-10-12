"""Wspólne fixture'y testów FinBro."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from finbro.config import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent

load_dotenv(PROJECT_ROOT / ".env")


@pytest.fixture(scope="session")
def test_database_url() -> str:
    url = os.environ.get("TEST_DATABASE_URL", "").strip()
    if not url:
        pytest.fail(
            "Brak zmiennej TEST_DATABASE_URL. Skopiuj .env.example do .env, "
            "ustaw hasło i uruchom bazę: docker compose up -d db",
            pytrace=False,
        )
    return url

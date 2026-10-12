"""Strażnik: fixture'y zawierają wyłącznie zmyślone numery rachunków."""

import re
from pathlib import Path

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"

# Wszystkie numery rachunków użyte w syntetycznych fixture'ach.
SYNTHETIC_ACCOUNTS = {
    "27102010260000123456789012",  # konto główne
    "83102055550000987654321098",  # inny rachunek
    "12114020040000310212345678",
    "44109000000000000123456789",
    "61114020040000350277770001",
    "33105014451000009011112222",
    "LT623250000011112222",
    "52105000003333444455556666",
    "71102010970000777788889999",
}

ACCOUNT_RE = re.compile(r"(?:[A-Z]{2})?\d{2}(?: ?\d{4}){4,6}")


def test_fixture_files_exist():
    names = {p.name for p in (FIXTURES / "pko").iterdir()}
    assert {"pko_2026-10-05_2026-10-11.xml", "pko_2026-10-08_2026-10-18.xml"} <= names


def test_fixtures_use_only_synthetic_account_numbers():
    found = set()
    for path in (FIXTURES / "pko").iterdir():
        text = path.read_text(encoding="utf-8")
        found |= {m.replace(" ", "") for m in ACCOUNT_RE.findall(text)}
    assert found, "nie znaleziono numerów rachunków w fixture'ach"
    assert found <= SYNTHETIC_ACCOUNTS

"""Pomocnicze stałe i funkcje testów."""

from pathlib import Path

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "pko"
MAIN_ACCOUNT = "27 1020 1026 0000 1234 5678 9012"
WEEK41 = "pko_2026-10-05_2026-10-11.xml"
OVERLAP = "pko_2026-10-08_2026-10-18.xml"


def fixture_bytes(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()

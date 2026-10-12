from datetime import date

from finbro.domain.coverage import DateRange
from finbro.services.importing import ImportService

from tests.helpers import WEEK41, fixture_bytes


def statement(since: str, to: str) -> bytes:
    return (
        '<?xml version="1.0" encoding="UTF-8"?><account-history><search>'
        "<account>27 1020 1026 0000 1234 5678 9012</account>"
        f'<date since="{since}" to="{to}"/></search><operations/></account-history>'
    ).encode()


def test_gap_between_imports(uow):
    service = ImportService(uow)
    service.import_pko_xml(fixture_bytes(WEEK41))
    service.import_pko_xml(statement("2026-10-19", "2026-10-25"))
    assert service.coverage_gaps() == [DateRange(date(2026, 10, 12), date(2026, 10, 18))]


def test_no_gaps_after_filling(uow):
    service = ImportService(uow)
    service.import_pko_xml(fixture_bytes(WEEK41))
    service.import_pko_xml(statement("2026-10-19", "2026-10-25"))
    service.import_pko_xml(statement("2026-10-12", "2026-10-18"))
    assert service.coverage_gaps() == []

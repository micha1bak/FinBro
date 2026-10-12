"""Import wyciągów XML z iPKO do konta głównego."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import date

from finbro.domain.accounts import account_matches
from finbro.domain.coverage import DateRange, coverage_gaps
from finbro.domain.enums import TxSource
from finbro.domain.transactions import TransactionData
from finbro.importers.pko_xml import ImportFormatError, ParsedOperation, ParsedStatement, parse_statement
from finbro.services.uow import UnitOfWork

MAIN_ACCOUNT_CODE = "pko"


class ImportRejected(ValueError):
    """Import odrzucony w całości (zły format, inny rachunek, brak konfiguracji)."""


@dataclass(frozen=True)
class ImportResult:
    batch_id: int
    new_transaction_ids: tuple[int, ...]
    existing_count: int
    skipped_count: int
    date_from: date
    date_to: date

    @property
    def new_count(self) -> int:
        return len(self.new_transaction_ids)


def operation_to_data(op: ParsedOperation, account_id: int, occurrence: int, batch_id: int) -> TransactionData:
    f = op.fields
    return TransactionData(
        source=TxSource.IMPORT,
        account_id=account_id,
        transaction_date=op.order_date,
        booking_date=op.exec_date,
        amount=op.amount,
        balance_after=op.ending_balance,
        occurrence=occurrence,
        bank_type=op.bank_type,
        raw_description=op.description,
        counterparty_name=f.counterparty_name,
        counterparty_account=f.counterparty_account,
        counterparty_address=f.counterparty_address,
        title=f.title,
        merchant=f.merchant,
        city=f.city,
        country=f.country,
        reference_number=f.reference_number,
        extra=f.extra,
        import_batch_id=batch_id,
    )


def with_occurrences(operations: list[ParsedOperation]) -> list[tuple[ParsedOperation, int]]:
    """Numer wystąpienia tego samego odcisku (data księgowania, kwota, saldo) w obrębie pliku."""
    seen: Counter[tuple] = Counter()
    result = []
    for op in operations:
        key = (op.exec_date, op.amount, op.ending_balance)
        seen[key] += 1
        result.append((op, seen[key]))
    return result


class ImportService:
    def __init__(self, uow: UnitOfWork) -> None:
        self.uow = uow

    def import_pko_xml(self, content: bytes, filename: str | None = None) -> ImportResult:
        """Importuje wyciąg atomowo: przy jakimkolwiek błędzie nic nie zostaje zapisane."""
        try:
            statement = parse_statement(content)
        except ImportFormatError as exc:
            raise ImportRejected(str(exc)) from exc
        try:
            result = self._store(statement, filename)
            self.after_import(result)
            self.uow.commit()
        except Exception:
            self.uow.rollback()
            raise
        return result

    def _store(self, statement: ParsedStatement, filename: str | None) -> ImportResult:
        config = self.uow.reference.config()
        if not config.main_account_number:
            raise ImportRejected("Ustaw numer konta głównego w Ustawieniach przed pierwszym importem.")
        if not account_matches(statement.account_number, config.main_account_number):
            raise ImportRejected(
                f"Wyciąg dotyczy rachunku {statement.account_number}, "
                f"a skonfigurowane konto główne to {config.main_account_number}."
            )

        account = self.uow.reference.account(MAIN_ACCOUNT_CODE)
        batch_id = self.uow.imports.create_batch(account.id, filename, statement.date_from, statement.date_to)
        booked = statement.booked
        rows = [operation_to_data(op, account.id, n, batch_id) for op, n in with_occurrences(booked)]
        new_ids = self.uow.imports.insert_new(rows)
        existing = len(rows) - len(new_ids)
        skipped = len(statement.pending)
        self.uow.imports.finish_batch(batch_id, len(new_ids), existing, skipped)
        return ImportResult(
            batch_id=batch_id,
            new_transaction_ids=tuple(sorted(new_ids)),
            existing_count=existing,
            skipped_count=skipped,
            date_from=statement.date_from,
            date_to=statement.date_to,
        )

    def after_import(self, result: ImportResult) -> None:
        """Miejsce na kroki po zapisie w tej samej transakcji (klasyfikacja nowych transakcji)."""

    def covered_ranges(self) -> list[DateRange]:
        account = self.uow.reference.account(MAIN_ACCOUNT_CODE)
        return [DateRange(b.date_from, b.date_to) for b in self.uow.imports.batches(account.id)]

    def coverage_gaps(self) -> list[DateRange]:
        """Okresy bez pokrycia importami między datą startu a ostatnim importem."""
        return coverage_gaps(self.covered_ranges(), self.uow.reference.config().start_date)

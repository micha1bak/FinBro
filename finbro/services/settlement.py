"""Rozliczenia tygodniowe: przypisanie dochodów do tygodni, korekty, wyliczenie i zamknięcie."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import UTC, date, datetime

from finbro.domain.coverage import DateRange, uncovered
from finbro.domain.accounts import same_account
from finbro.domain.enums import ProposalSource, SettlementStatus, TxType
from finbro.domain.money import Money
from finbro.domain.periods import IsoWeek
from finbro.domain.reference import Envelope
from finbro.domain.settlement import (
    CLOSED_STATUSES,
    IncomeContribution,
    LineState,
    Settlement,
    SettlementAdjustment,
    SettlementLine,
    carryover_before,
    compute_lines,
    envelope_word_matches,
    is_settled_income_date,
    line_state,
    parse_transfer_title,
    settlement_status,
)
from finbro.domain.transactions import Classification, Direction, Transaction
from finbro.services.uow import UnitOfWork


class SettlementError(ValueError):
    """Operacja na rozliczeniu niedozwolona w obecnym stanie."""


@dataclass(frozen=True)
class WeekSettlement:
    """Rozliczenie tygodnia do wyświetlenia: wyliczone na żywo (otwarte) albo zamrożone (zamknięte)."""

    settlement: Settlement
    envelopes: list[Envelope]
    incomes: list[Transaction] = field(default_factory=list)
    late_incomes: list[Transaction] = field(default_factory=list)
    adjustments: list[SettlementAdjustment] = field(default_factory=list)
    paid_by_line: dict[int, Money] = field(default_factory=dict)
    carried_forward: bool = False

    @property
    def week(self) -> IsoWeek:
        return self.settlement.week

    @property
    def is_closed(self) -> bool:
        return self.settlement.status in CLOSED_STATUSES

    @property
    def life(self) -> Envelope:
        return next(e for e in self.envelopes if e.is_life)

    @property
    def income_total(self) -> Money:
        return sum((t.amount for t in self.incomes), Money.zero())

    @property
    def correction_total(self) -> Money:
        late = sum((t.amount for t in self.late_incomes), Money.zero())
        return late + sum((a.amount for a in self.adjustments), Money.zero())

    def line(self, envelope: Envelope) -> SettlementLine:
        line = self.settlement.line_for(envelope.id)
        assert line is not None
        return line

    def paid(self, line: SettlementLine) -> Money:
        return self.paid_by_line.get(line.id, Money.zero()) if line.id is not None else Money.zero()

    def state(self, line: SettlementLine) -> LineState:
        return line_state(line, self.paid(line), self.carried_forward)


class SettlementService:
    def __init__(self, uow: UnitOfWork) -> None:
        self.uow = uow

    def _open_week_from(self, week: IsoWeek) -> IsoWeek:
        """Najbliższy niezamknięty tydzień od ``week``, z blokadą jego wiersza rozliczenia."""
        while self.uow.settlements.lock_week(week) in CLOSED_STATUSES:
            week = week.next()
        return week

    def on_income_change(self, tx: Transaction, new: Classification) -> Classification:
        """Ustala ``settlement_week`` zatwierdzanego dochodu i korekty po wycofaniu dochodu (D7).

        - Nowy dochód trafia do tygodnia swojej daty, a gdy ten jest już zamknięty, do najbliższego
          niezamkniętego tygodnia jako korekta.
        - Dochód, który był już zatwierdzony, zachowuje swój tydzień.
        - Wycofanie dochodu podzielonego w zamkniętym tygodniu tworzy ujemną korektę
          w najbliższym niezamkniętym tygodniu.
        - Dochody sprzed daty startu nie są dzielone.
        """
        old = tx.classification
        was_income = old.confirmed and old.type is TxType.DOCHOD
        is_income = new.type is TxType.DOCHOD

        if was_income and is_income:
            return replace(new, settlement_week=old.settlement_week)

        if was_income and old.settlement_week is not None:
            counted_in = IsoWeek.of(old.settlement_week)
            if self.uow.settlements.lock_week(counted_in) in CLOSED_STATUSES:
                target = self._open_week_from(counted_in.next())
                self.uow.settlements.add_adjustment(target, tx.id, -tx.amount, tx.transaction_date)

        if not is_income:
            return replace(new, settlement_week=None)

        start_date = self.uow.reference.config().start_date
        if not is_settled_income_date(tx.transaction_date, start_date):
            return replace(new, settlement_week=None)
        target = self._open_week_from(IsoWeek.of(tx.transaction_date))
        return replace(new, settlement_week=target.start)

    # --- wyliczenie ---

    def compute(self, week: IsoWeek) -> WeekSettlement:
        envelopes = self.uow.reference.envelopes()
        stored = self.uow.settlements.get(week)
        paid_by_line = self.uow.settlements.paid_by_line()
        all_settlements = self.uow.settlements.list_all()
        later_closed = any(s.week > week and s.status in CLOSED_STATUSES for s in all_settlements)
        start_date = self.uow.reference.config().start_date

        assigned = [
            t
            for t in self.uow.transactions.incomes_for_settlement_week(week.start)
            if is_settled_income_date(t.transaction_date, start_date)
        ]
        incomes = [t for t in assigned if week.contains(t.transaction_date)]
        late = [t for t in assigned if not week.contains(t.transaction_date)]
        adjustments = self.uow.settlements.adjustments(week)

        if stored is not None and stored.status in CLOSED_STATUSES:
            settlement = stored
        else:
            life = next(e for e in envelopes if e.is_life)
            contributions = [IncomeContribution(t.amount, t.transaction_date) for t in incomes]
            contributions += [IncomeContribution(t.amount, t.transaction_date, correction=True) for t in late]
            contributions += [IncomeContribution(a.amount, a.income_date, correction=True) for a in adjustments]
            closed_before = [s for s in all_settlements if s.week < week and s.status in CLOSED_STATUSES]
            carry = carryover_before(closed_before, paid_by_line, life.id)
            lines = compute_lines(contributions, self.uow.reference.plans(), [e.id for e in envelopes], life.id, carry)
            settlement = Settlement(week=week, status=SettlementStatus.OPEN, lines=lines)

        return WeekSettlement(
            settlement=settlement,
            envelopes=envelopes,
            incomes=incomes,
            late_incomes=late,
            adjustments=adjustments,
            paid_by_line=paid_by_line,
            carried_forward=later_closed,
        )

    # --- zamknięcie ---

    def warnings(self, week: IsoWeek) -> list[str]:
        """Ostrzeżenia przed zamknięciem (nie blokują zamknięcia)."""
        from finbro.services.importing import ImportService  # import lokalny: unika cyklu przez potok klasyfikacji

        result = []
        week_range = DateRange(week.start, week.end)
        gaps = uncovered(ImportService(self.uow).covered_ranges(), week_range)
        if gaps:
            result.append(
                "Tydzień nie jest w pełni pokryty importami konta głównego (brak: "
                + ", ".join(g.label() for g in gaps)
                + ")."
            )
        pending = [
            t
            for t in self.uow.transactions.unconfirmed()
            if t.direction is Direction.IN and week.contains(t.transaction_date)
        ]
        if pending:
            total = sum((t.amount for t in pending), Money.zero())
            result.append(
                f"W skrzynce są niezatwierdzone wpływy z tego tygodnia: {len(pending)} na {total.format()}."
            )
        if not self.uow.inventories.between(week.end, week.end):
            result.append(f"Nie wykonano inwentaryzacji Portfela na koniec tygodnia ({week.end.isoformat()}).")
        return result

    def close(self, week: IsoWeek, today: date | None = None) -> WeekSettlement:
        """Zamyka rozliczenie: zamraża linie w jednej transakcji z blokadą wiersza rozliczenia (D7)."""
        today = today or date.today()
        if today <= week.end:
            raise SettlementError(f"Tydzień {week.label} jeszcze trwa; rozliczenie będzie dostępne od {week.next().start.isoformat()}.")
        start_date = self.uow.reference.config().start_date
        if start_date is None:
            raise SettlementError("Ustaw datę startu rozliczeń w Ustawieniach.")
        if week.end < start_date:
            raise SettlementError(f"Tydzień {week.label} jest przed datą startu rozliczeń ({start_date.isoformat()}).")
        try:
            if self.uow.settlements.lock_week(week, exclusive=True) in CLOSED_STATUSES:
                raise SettlementError(f"Rozliczenie {week.label} jest już zamknięte.")
            computed = self.compute(week).settlement
            self.uow.settlements.save_closed(
                replace(computed, status=SettlementStatus.CLOSED, closed_at=datetime.now(UTC))
            )
            self.after_close(week)
        except Exception:
            self.uow.rollback()
            raise
        self.uow.commit()
        return self.compute(week)

    def after_close(self, week: IsoWeek) -> None:
        """Po zamknięciu: przypisanie wcześniej nieprzypisanych przelewów i odświeżenie statusów."""
        for tx in self.uow.transactions.unassigned_savings():
            self.sync_payment(tx, refresh=False)
        self.refresh_statuses()

    # --- przelewy na koperty ---

    def _savings_envelopes(self) -> list[Envelope]:
        return [e for e in self.uow.reference.envelopes() if not e.is_life]

    def detect_envelope(self, tx: Transaction) -> tuple[Envelope, str] | None:
        """Koperta przelewu: z tytułu FinBro albo z rachunku docelowego koperty (D8)."""
        if tx.direction is not Direction.OUT:
            return None
        envelopes = self._savings_envelopes()
        parsed = parse_transfer_title(tx.data.title)
        if parsed is not None:
            week, word = parsed
            env = next((e for e in envelopes if envelope_word_matches(word, e.name)), None)
            if env is not None:
                return env, f"Przelew FinBro: {week.label} {env.name}"
        env = next(
            (e for e in envelopes if e.target_account and same_account(tx.data.counterparty_account, e.target_account)),
            None,
        )
        if env is not None:
            return env, f"Przelew na rachunek koperty {env.name}"
        return None

    def _closed(self) -> list[Settlement]:
        return [s for s in self.uow.settlements.list_all() if s.status in CLOSED_STATUSES]

    def line_for_payment(self, tx: Transaction, envelope_id: int) -> SettlementLine | None:
        """Linia rozliczenia dla przelewu: wskazana tytułem, a bez tytułu najstarsza niedopłata koperty."""
        closed = self._closed()
        parsed = parse_transfer_title(tx.data.title)
        if parsed is not None:
            settlement = next((s for s in closed if s.week == parsed[0]), None)
            if settlement is not None and settlement.line_for(envelope_id) is not None:
                return settlement.line_for(envelope_id)
        paid = self.uow.settlements.paid_by_line()
        for i, settlement in enumerate(closed):
            line = settlement.line_for(envelope_id)
            later_closed = i < len(closed) - 1
            if line is not None and line_state(line, paid.get(line.id, Money.zero()), later_closed) is LineState.PENDING:
                return line
        # Brak niedopłat: przelew zaliczamy na ostatnie zamknięte rozliczenie (nadpłata przejdzie dalej).
        return closed[-1].line_for(envelope_id) if closed else None

    def sync_payment(self, tx: Transaction, refresh: bool = True) -> None:
        """Utrzymuje przypisanie przelewu ODKŁADANIE do linii rozliczenia zgodnie z klasyfikacją."""
        c = tx.classification
        current_line = self.uow.settlements.payment_line_for(tx.id)
        wanted = c.confirmed and c.type is TxType.ODKLADANIE and c.envelope_id is not None
        if current_line is not None:
            line_envelope = next((l.envelope_id for s in self._closed() for l in s.lines if l.id == current_line), None)
            if wanted and line_envelope == c.envelope_id:
                return
            self.uow.settlements.remove_payment(tx.id)
        if wanted:
            line = self.line_for_payment(tx, c.envelope_id)
            if line is not None and line.id is not None:
                self.uow.settlements.add_payment(line.id, tx.id, abs(tx.amount))
        if refresh:
            self.refresh_statuses()

    def recognize_transfers(self, transaction_ids: list[int]) -> int:
        """Rozpoznaje w nowych wydatkach przelewy na koperty i zalicza je na rozliczenia."""
        count = 0
        for tx in self.uow.transactions.get_many(transaction_ids):
            detected = self.detect_envelope(tx)
            if detected is None:
                continue
            envelope, reason = detected
            classified = self.uow.transactions.set_classification(
                tx.id,
                Classification(
                    type=TxType.ODKLADANIE,
                    envelope_id=envelope.id,
                    source=tx.classification.source or ProposalSource.SYSTEM,
                    rule_id=tx.classification.rule_id,
                    reason=reason,
                    confirmed=True,
                    confirmed_at=datetime.now(UTC),
                ),
            )
            self.uow.llm_jobs.cancel(tx.id)
            self.sync_payment(classified, refresh=False)
            count += 1
        self.refresh_statuses()
        return count

    def refresh_statuses(self) -> None:
        closed = self._closed()
        if not closed:
            return
        life = next(e for e in self.uow.reference.envelopes() if e.is_life)
        paid = self.uow.settlements.paid_by_line()
        for i, settlement in enumerate(closed):
            status = settlement_status(settlement, paid, i < len(closed) - 1, life.id)
            if status is not settlement.status:
                self.uow.settlements.set_status(settlement.week, status)

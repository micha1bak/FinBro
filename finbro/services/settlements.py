"""Zbiorcze rozliczenie przelewów na koperty (D5) i cofanie najnowszego rozliczenia (D6)."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from finbro.db.models import Income, IncomeShare, Settlement, SettlementLine
from finbro.domain.allocation import plan_for
from finbro.domain.envelopes import Envelope
from finbro.domain.money import Money
from finbro.domain.transfers import PlannedIncome, Transfer, distribute, transfers
from finbro.services.incomes import IncomeService, IncomeView
from finbro.services.settings import SettingsService


class SettlementError(ValueError):
    """Rozliczenia nie da się wykonać albo cofnąć (komunikat dla użytkownika)."""


@dataclass(frozen=True)
class PendingTransfer:
    transfer: Transfer
    target_account: str | None


@dataclass(frozen=True)
class Pending:
    incomes: list[IncomeView]
    transfers: list[PendingTransfer]

    @property
    def income_ids(self) -> list[int]:
        return [i.id for i in self.incomes]

    @property
    def expected(self) -> dict[Envelope, Money]:
        return {t.transfer.envelope: t.transfer.amount for t in self.transfers}


@dataclass(frozen=True)
class SettlementView:
    id: int
    date: date
    lines: dict[Envelope, Money]
    income_count: int
    is_latest: bool

    @property
    def total(self) -> Money:
        return sum(self.lines.values(), Money.zero())


class SettlementService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def pending(self, day: date) -> Pending:
        incomes = IncomeService(self.session).unsettled()
        accounts = SettingsService(self.session).accounts()
        return Pending(
            incomes=incomes,
            transfers=[PendingTransfer(t, accounts.get(t.envelope)) for t in transfers(self._planned(incomes), day)],
        )

    def settle(self, income_ids: Sequence[int], expected: Mapping[Envelope, Money], day: date) -> SettlementView:
        """Rozlicza dokładnie wskazane dochody, jeśli od wyświetlenia listy nic się nie zmieniło.

        Zamrożony podział dochodów to rozdział kwot przelewów (D13), więc sumuje się do linii rozliczenia.
        """
        ids = sorted(set(income_ids))
        if not ids:
            raise SettlementError("Brak dochodów do rozliczenia.")
        # Kolejność (data, id) rozstrzyga remisy przy rozdziale kwot kopert na dochody.
        locked = self.session.scalars(
            select(Income).where(Income.id.in_(ids)).order_by(Income.date, Income.id).with_for_update()
        ).all()
        if sorted(r.id for r in locked if r.settlement_id is None) != ids:
            raise SettlementError("Lista dochodów zmieniła się od wyświetlenia. Odśwież widok i sprawdź przelewy.")
        planned = self._planned(IncomeService(self.session).views(locked))
        current = transfers(planned, day)
        if {t.envelope: t.amount for t in current} != dict(expected):
            raise SettlementError("Kwoty przelewów zmieniły się od wyświetlenia. Odśwież widok i sprawdź przelewy.")

        settlement = Settlement(date=day)
        self.session.add(settlement)
        self.session.flush()
        for t in current:
            self.session.add(SettlementLine(settlement_id=settlement.id, envelope=t.envelope.value, amount=t.amount.grosze))
        for parts, row in zip(distribute(planned), locked, strict=True):
            for envelope, amount in parts.items():
                self.session.add(
                    IncomeShare(income_id=row.id, envelope=envelope.value, settlement_id=settlement.id, amount=amount.grosze)
                )
            row.settlement_id = settlement.id
        self.session.commit()
        return self.get(settlement.id)

    def history(self) -> list[SettlementView]:
        rows = self.session.scalars(select(Settlement).order_by(Settlement.id.desc())).all()
        if not rows:
            return []
        lines: dict[int, dict[Envelope, Money]] = {r.id: {} for r in rows}
        for line in self.session.scalars(select(SettlementLine).where(SettlementLine.settlement_id.in_(lines))):
            lines[line.settlement_id][Envelope(line.envelope)] = Money(line.amount)
        counts = Counter(
            dict(
                self.session.execute(
                    select(Income.settlement_id, func.count()).where(Income.settlement_id.in_(lines)).group_by(Income.settlement_id)
                ).all()
            )
        )
        latest = rows[0].id
        return [SettlementView(r.id, r.date, lines[r.id], counts[r.id], r.id == latest) for r in rows]

    def get(self, settlement_id: int) -> SettlementView:
        for view in self.history():
            if view.id == settlement_id:
                return view
        raise SettlementError("Nie ma takiego rozliczenia.")

    def _planned(self, incomes: Sequence[IncomeView]) -> list[PlannedIncome]:
        plans = IncomeService(self.session).plans()
        return [PlannedIncome(i.amount, plan_for(plans, i.date)) for i in incomes]

    def undo(self, settlement_id: int) -> None:
        """Cofa najnowsze rozliczenie: dochody wracają do rozliczenia, znika zamrożony podział."""
        latest = self.session.scalar(select(func.max(Settlement.id)))
        if latest is None or settlement_id != latest:
            raise SettlementError("Cofnąć można tylko najnowsze rozliczenie.")
        self.session.execute(delete(Settlement).where(Settlement.id == settlement_id))
        self.session.commit()
        self.session.expire_all()

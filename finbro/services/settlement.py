"""Rozliczenia tygodniowe: przypisanie dochodów do tygodni, korekty, wyliczenie i zamknięcie."""

from __future__ import annotations

from dataclasses import replace

from finbro.domain.enums import TxType
from finbro.domain.periods import IsoWeek
from finbro.domain.settlement import CLOSED_STATUSES, is_settled_income_date
from finbro.domain.transactions import Classification, Transaction
from finbro.services.uow import UnitOfWork


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

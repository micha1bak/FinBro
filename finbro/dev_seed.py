"""Zmyślone dane do bazy deweloperskiej: ``poe seed`` albo ``python -m finbro.dev_seed``.

Kasuje dane w bazie z ``DATABASE_URL`` i wpisuje kilka miesięcy przykładowych dochodów,
rozliczeń, sald i rachunków kopert. Korzysta z serwisów aplikacji, więc podział i przelewy
liczą się tak samo jak w aplikacji. Ostatnie dochody zostają nierozliczone, żeby widok
Rozliczenie miał listę przelewów. Działa tylko na bazie, której nazwa kończy się na ``_dev``.
"""

from __future__ import annotations

import argparse
import random
import sys
from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from finbro.config import ConfigError, Settings, load_dotenv
from finbro.db.models import AllocationPlan, EnvelopeAccount, Income, Settlement
from finbro.db.models import BalanceEntry as BalanceRow
from finbro.db.session import make_engine, make_session_factory, ping
from finbro.domain.envelopes import Envelope
from finbro.domain.incomes import IncomeForm
from finbro.domain.money import Money
from finbro.domain.networth import Account, balance
from finbro.services.incomes import IncomeService
from finbro.services.networth import NetWorthService
from finbro.services.settings import SettingsService
from finbro.services.settlements import SettlementService

DEV_DATABASE_SUFFIX = "_dev"
SALARY_DAY = 10
SETTLEMENT_DAY = 12
BALANCE_DAY = 28

SALARY_SOURCE = "Wynagrodzenie – Przykładowa Firma sp. z o.o."
SIDE_SOURCES = ("Zlecenie – strona internetowa", "Faktura – konsultacje", "Sprzedaż na OLX", "Zwrot za wspólny wyjazd")
CASH_SOURCES = ("Korepetycje", "Pomoc przy przeprowadzce", "Prezent", "Sprzedaż na giełdzie staroci")

ACCOUNTS = {
    Envelope.WAKACJE: "00 0000 0000 0000 0000 0000 0001",
    Envelope.XTB: "00 0000 0000 0000 0000 0000 0002",
    Envelope.OBLIGACJE: "00 0000 0000 0000 0000 0000 0003",
}
CHANGED_PLAN = {Envelope.PKO: 4500, Envelope.WAKACJE: 2000, Envelope.XTB: 1750, Envelope.OBLIGACJE: 1750}


@dataclass(frozen=True)
class SeedSummary:
    incomes: int
    unsettled: int
    settlements: int
    balances: int


def zl(rng: random.Random, low: int, high: int, step: int = 10) -> Money:
    """Losowa kwota w pełnych złotych z przedziału ``low``–``high``."""
    return Money(rng.randrange(low, high + 1, step) * 100)


def month_start(day: date, offset: int = 0) -> date:
    """Pierwszy dzień miesiąca przesuniętego o ``offset`` miesięcy względem ``day``."""
    index = day.year * 12 + day.month - 1 + offset
    return date(index // 12, index % 12 + 1, 1)


def incomes_by_day(rng: random.Random, first: date, today: date) -> dict[date, list[tuple[str, Money, IncomeForm]]]:
    result: dict[date, list[tuple[str, Money, IncomeForm]]] = {}
    month = first
    while month <= today:
        items = [(month.replace(day=SALARY_DAY), SALARY_SOURCE, Money(rng.randint(840_000, 890_000)), IncomeForm.PKO)]
        if month.month in (3, 6, 9, 12):
            items.append((month.replace(day=SALARY_DAY), "Premia kwartalna", zl(rng, 1500, 3000, 100), IncomeForm.PKO))
        if month.month == 4:
            items.append((month.replace(day=rng.randint(15, 28)), "Zwrot podatku PIT", zl(rng, 400, 1800), IncomeForm.PKO))
        if rng.random() < 0.5:
            items.append((month.replace(day=rng.randint(1, 28)), rng.choice(SIDE_SOURCES), zl(rng, 300, 2500), IncomeForm.PKO))
        if rng.random() < 0.4:
            items.append((month.replace(day=rng.randint(1, 28)), rng.choice(CASH_SOURCES), zl(rng, 50, 600), IncomeForm.GOTOWKA))
        for day, source, amount, form in items:
            if day <= today:
                result.setdefault(day, []).append((source, amount, form))
        month = month_start(month, 1)
    return result


def reset(session: Session) -> None:
    """Kasuje dane, zostawiając plan startowy z migracji (najwcześniejszy)."""
    first_plan = session.scalar(select(func.min(AllocationPlan.effective_from)))
    session.execute(delete(Income))
    session.execute(delete(Settlement))
    session.execute(delete(BalanceRow))
    session.execute(delete(EnvelopeAccount))
    session.execute(delete(AllocationPlan).where(AllocationPlan.effective_from > first_plan))
    session.commit()


def seed(session: Session, today: date, months: int = 12, rng: random.Random | None = None) -> SeedSummary:
    """Wypełnia bazę danymi z ``months`` ostatnich miesięcy (łącznie z bieżącym) do ``today``."""
    rng = rng or random.Random()
    reset(session)
    incomes, settlements, net_worth = IncomeService(session), SettlementService(session), NetWorthService(session)
    first = month_start(today, -(months - 1))
    planned = incomes_by_day(rng, first, today)

    SettingsService(session).save_accounts(ACCOUNTS)
    if months > 1:
        incomes.add_plan(month_start(first, months // 2), CHANGED_PLAN)

    start = first - timedelta(days=1)
    for account, amount in (
        (Account.PKO, zl(rng, 9000, 14000)),
        (Account.GOTOWKA, zl(rng, 300, 1200)),
        (Account.XTB, zl(rng, 12000, 18000, 100)),
        (Account.OBLIGACJE, zl(rng, 18000, 25000, 100)),
    ):
        net_worth.record(account, start, amount)

    day = first
    while day <= today:
        for source, amount, form in planned.get(day, []):
            incomes.add(day, source, amount, form)
        if day.day == SETTLEMENT_DAY and day < month_start(today):
            pending = settlements.pending(day)
            if pending.incomes:
                settlements.settle(pending.income_ids, pending.expected, day)
        if day.day == BALANCE_DAY:
            net_worth.record(Account.PKO, day, zl(rng, 8000, 20000))
            net_worth.record(Account.GOTOWKA, day, zl(rng, 200, 1500))
            if day.month % 3 == 0:
                # Saldo faktyczne inwestycji: wyliczone z wpłat razy zysk albo strata rynku.
                entries, contributions = net_worth.entries(), net_worth.contributions()
                for account in (Account.XTB, Account.OBLIGACJE):
                    computed = balance(account, entries, contributions, day) or Money.zero()
                    net_worth.record(account, day, Money(round(computed.grosze * rng.uniform(0.96, 1.07))))
        day += timedelta(days=1)

    return SeedSummary(
        incomes=session.scalar(select(func.count()).select_from(Income)),
        unsettled=len(incomes.unsettled()),
        settlements=len(settlements.history()),
        balances=len(net_worth.entries()),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Wypełnia bazę deweloperską zmyślonymi danymi (kasuje obecne).")
    parser.add_argument("--months", type=int, default=12, help="liczba miesięcy danych łącznie z bieżącym (domyślnie 12)")
    parser.add_argument("--seed", type=int, default=2026, help="ziarno losowania: te same dane przy tym samym dniu")
    args = parser.parse_args(argv)
    if args.months < 1:
        parser.error("--months musi być co najmniej 1")

    load_dotenv()
    try:
        settings = Settings.from_env()
    except ConfigError as exc:
        print(exc, file=sys.stderr)
        return 1
    url = make_url(settings.database_url)
    if not (url.database or "").endswith(DEV_DATABASE_SUFFIX):
        print(
            f"Odmowa: baza {url.database!r} nie jest deweloperska (nazwa musi kończyć się na "
            f"{DEV_DATABASE_SUFFIX!r}), a skrypt kasuje dane. Sprawdź DATABASE_URL w .env.",
            file=sys.stderr,
        )
        return 1
    engine = make_engine(settings.database_url)
    if not ping(engine):
        print(f"Baza {url.database} jest nieosiągalna. Uruchom ją poleceniem: poe db", file=sys.stderr)
        return 1

    with make_session_factory(engine)() as session:
        summary = seed(session, date.today(), args.months, random.Random(args.seed))
    engine.dispose()
    print(
        f"Baza {url.database}: dochody {summary.incomes} (nierozliczone {summary.unsettled}), "
        f"rozliczenia {summary.settlements}, salda faktyczne {summary.balances}."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

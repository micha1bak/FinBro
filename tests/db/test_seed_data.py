"""Dane początkowe tworzone migracją 0002."""

from datetime import date

from sqlalchemy import select

from finbro.db import models
from finbro.domain.allocation import AllocationPlan, FULL_SHARE_BP
from finbro.domain.enums import AccountKind, TransferKind, TxType

EXPECTED_CATEGORIES = [
    "Spożywcze",
    "Restauracje i na mieście",
    "Transport",
    "Mieszkanie",
    "Abonamenty i subskrypcje",
    "Zdrowie",
    "Ubrania",
    "Dom i wyposażenie",
    "Rozrywka i hobby",
    "Prezenty",
    "Edukacja",
    "Podróże",
    "Inne",
]


def test_accounts(db_session):
    accounts = {a.code: a for a in db_session.scalars(select(models.Account))}
    assert accounts["pko"].kind is AccountKind.BANK
    assert accounts["portfel"].kind is AccountKind.CASH
    assert accounts["portfel"].name == "Portfel"


def test_categories(db_session):
    rows = db_session.scalars(select(models.Category).order_by(models.Category.sort_order)).all()
    regular = [c.name for c in rows if not c.is_system]
    system = [c.name for c in rows if c.is_system]
    assert regular == EXPECTED_CATEGORIES
    assert system == ["Gotówka (bez kategorii)"]
    assert all(c.active for c in rows)


def test_envelopes_and_plan_sum_to_100_percent(db_session):
    envelopes = {e.code: e for e in db_session.scalars(select(models.Envelope))}
    assert {e.name for e in envelopes.values()} == {"Życie", "XTB", "Obligacje", "Wakacje"}
    assert [e.code for e in envelopes.values() if e.is_life] == ["zycie"]

    plans = db_session.scalars(select(models.AllocationPlan)).all()
    assert len(plans) == 1
    shares = {s.envelope.code: s.basis_points for s in plans[0].shares}
    assert shares == {"zycie": 5000, "xtb": 1250, "obligacje": 1250, "wakacje": 2500}
    assert sum(shares.values()) == FULL_SHARE_BP
    # Plan przechodzi walidację domenową i obowiązuje od dowolnej realnej daty startu.
    plan = AllocationPlan(plans[0].effective_from, shares, "zycie")
    assert plan.effective_from <= date(2026, 1, 1)


def test_starting_rules(db_session):
    rules = {r.name: r for r in db_session.scalars(select(models.Rule))}
    by_result = {(r.result_type, r.result_transfer_kind): r for r in rules.values()}
    assert all(r.active for r in rules.values())

    finbro = by_result[(TxType.ODKLADANIE, None)]
    assert finbro.conditions == {"direction": "OUT", "title": "FinBro"}

    wallet_rules = [r for r in rules.values() if r.result_transfer_kind is TransferKind.WALLET]
    assert {r.conditions["direction"] for r in wallet_rules} == {"IN", "OUT"}

    revolut = by_result[(TxType.TRANSFER, TransferKind.FAMILY)]
    assert revolut.conditions["merchant"] == "Revolut"
    assert revolut.conditions["bank_type"] == "Przelew z karty"
    assert len(rules) == 4


def test_settings_row_exists(db_session):
    settings = db_session.get(models.AppSettings, 1)
    assert settings is not None
    assert settings.start_date is None


def test_starting_rules_load_through_repository(db_session):
    from finbro.db.repositories.rules import RuleRepository

    rules = RuleRepository(db_session).active()
    assert len(rules) == 4
    assert [r.priority for r in rules] == sorted(r.priority for r in rules)

"""Ograniczenia schematu i plan startowy z migracji."""

from datetime import date

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from finbro.db.models import AllocationPlan, BalanceEntry, EnvelopeAccount, Income


def test_initial_plan(db_session):
    [plan] = db_session.scalars(select(AllocationPlan)).all()
    assert plan.effective_from == date(2000, 1, 1)
    assert (plan.pko, plan.wakacje, plan.xtb, plan.obligacje) == (5000, 2500, 1250, 1250)


def test_plan_shares_must_sum_to_100_percent(db_session):
    db_session.add(AllocationPlan(effective_from=date(2026, 11, 1), pko=5000, wakacje=2000, xtb=1250, obligacje=1250))
    with pytest.raises(IntegrityError, match="shares_sum_100"):
        db_session.flush()


def test_one_balance_per_account_and_day(db_session):
    db_session.add(BalanceEntry(account="XTB", date=date(2026, 10, 12), amount=120000))
    db_session.flush()
    db_session.add(BalanceEntry(account="XTB", date=date(2026, 10, 12), amount=130000))
    with pytest.raises(IntegrityError, match="uq_balance_entry_account_date"):
        db_session.flush()


@pytest.mark.parametrize(
    "row, constraint",
    [
        (BalanceEntry(account="WAKACJE", date=date(2026, 10, 12), amount=100), "ck_balance_entry_account"),
        (BalanceEntry(account="KARTA", date=date(2026, 10, 12), amount=100), "ck_balance_entry_account"),
        (BalanceEntry(account="XTB", date=date(2026, 10, 12), amount=-1), "ck_balance_entry_amount_non_negative"),
        (EnvelopeAccount(envelope="PKO", target_account="00 0000"), "ck_envelope_account_envelope"),
        (Income(date=date(2026, 10, 14), source="Zlecenie", amount=0), "ck_income_amount_positive"),
        (Income(date=date(2026, 10, 14), source="  ", amount=100), "ck_income_source_not_empty"),
        (Income(date=date(2026, 10, 14), source="Zlecenie", amount=100, form="KARTA"), "ck_income_form"),
    ],
)
def test_check_constraints(db_session, row, constraint):
    db_session.add(row)
    with pytest.raises(IntegrityError, match=constraint):
        db_session.flush()


def test_income_form_defaults_to_pko(db_session):
    income = Income(date=date(2026, 10, 14), source="Zlecenie", amount=100)
    db_session.add(income)
    db_session.flush()
    db_session.refresh(income)
    assert income.form == "PKO"


def test_cash_balance_is_allowed(db_session):
    db_session.add(BalanceEntry(account="GOTOWKA", date=date(2026, 10, 12), amount=25000))
    db_session.flush()

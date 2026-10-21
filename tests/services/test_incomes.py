from datetime import date

import pytest

from finbro.domain.envelopes import Envelope
from finbro.domain.incomes import IncomeForm
from finbro.domain.money import Money
from finbro.services.incomes import IncomeError, IncomeService
from finbro.services.settlements import SettlementService

P, W, X, O = Envelope.PKO, Envelope.WAKACJE, Envelope.XTB, Envelope.OBLIGACJE
OCT14 = date(2026, 10, 14)


def zl(text):
    return Money.parse(text)


@pytest.fixture
def incomes(db_session):
    return IncomeService(db_session)


def settle(db_session, incomes, income_id):
    """Rozlicza pojedynczy dochód serwisem rozliczeń (przelewy to jego własny podział)."""
    view = incomes.get(income_id)
    expected = {e: amount for e, amount in view.split.items() if e.is_transfer and amount.is_positive}
    SettlementService(db_session).settle([income_id], expected, OCT14)


def test_add_income_is_unsettled_with_split(incomes):
    view = incomes.add(OCT14, "  Zlecenie  ", zl("174,00"))
    assert (view.source, view.amount, view.settled) == ("Zlecenie", zl("174"), False)
    assert view.split == {P: zl("86"), W: zl("44"), X: zl("22"), O: zl("22")}


@pytest.mark.parametrize("source, amount", [("Zlecenie", Money.zero()), ("Zlecenie", zl("-5")), ("   ", zl("10")), ("x" * 201, zl("10"))])
def test_invalid_income_is_rejected(incomes, source, amount):
    with pytest.raises(IncomeError):
        incomes.add(OCT14, source, amount)
    assert incomes.month(2026, 10).incomes == []


def test_month_summary(incomes):
    incomes.add(date(2026, 10, 5), "Stypendium", zl("2401,30"))
    incomes.add(OCT14, "Zlecenie", zl("174,00"))
    incomes.add(date(2026, 11, 2), "Listopad", zl("100"))
    summary = incomes.month(2026, 10)
    assert [v.source for v in summary.incomes] == ["Zlecenie", "Stypendium"]  # od najnowszych
    assert summary.total == zl("2575,30")
    assert summary.totals == {P: zl("1287,30"), W: zl("644"), X: zl("322"), O: zl("322")}


def test_update_recomputes_split(incomes):
    view = incomes.add(OCT14, "Zlecenie", zl("174,00"))
    updated = incomes.update(view.id, OCT14, "Zlecenie", zl("210,00"))
    # 52,50 -> 53, 26,25 -> 26
    assert updated.split == {P: zl("105"), W: zl("53"), X: zl("26"), O: zl("26")}


def test_delete_unsettled(incomes):
    view = incomes.add(OCT14, "Zlecenie", zl("174,00"))
    incomes.delete(view.id)
    assert incomes.month(2026, 10).incomes == []


def test_settled_income_cannot_be_changed_or_deleted(db_session, incomes):
    view = incomes.add(OCT14, "Zlecenie", zl("174,00"))
    settle(db_session, incomes, view.id)
    with pytest.raises(IncomeError, match="cofnij rozliczenie"):
        incomes.update(view.id, OCT14, "Zlecenie", zl("200"))
    with pytest.raises(IncomeError, match="cofnij rozliczenie"):
        incomes.delete(view.id)
    assert incomes.get(view.id).amount == zl("174")


def test_new_plan_applies_from_its_date_to_unsettled_only(db_session, incomes):
    october = incomes.add(OCT14, "Październik", zl("174,00"))
    settled = incomes.add(date(2026, 11, 3), "Rozliczony", zl("100,00"))
    settle(db_session, incomes, settled.id)
    november = incomes.add(date(2026, 11, 5), "Listopad", zl("100,00"))

    incomes.add_plan(date(2026, 11, 1), {P: 6000, W: 2000, X: 1000, O: 1000})

    assert incomes.get(october.id).split == {P: zl("86"), W: zl("44"), X: zl("22"), O: zl("22")}
    assert incomes.get(november.id).split == {P: zl("60"), W: zl("20"), X: zl("10"), O: zl("10")}
    # Rozliczony dochód zachowuje podział z chwili rozliczenia (50/25/12,5/12,5; 12,50 -> 13).
    assert incomes.get(settled.id).split == {P: zl("49"), W: zl("25"), X: zl("13"), O: zl("13")}


def test_invalid_or_duplicate_plan(incomes):
    with pytest.raises(IncomeError, match="95%"):
        incomes.add_plan(date(2026, 11, 1), {P: 5000, W: 2000, X: 1250, O: 1250})
    with pytest.raises(IncomeError, match="już istnieje"):
        incomes.add_plan(date(2000, 1, 1), {P: 5000, W: 2500, X: 1250, O: 1250})


def test_unsettled_list(db_session, incomes):
    first = incomes.add(OCT14, "A", zl("10"))
    second = incomes.add(OCT14, "B", zl("20"))
    settle(db_session, incomes, first.id)
    assert [v.id for v in incomes.unsettled()] == [second.id]


def test_cash_income_has_same_split_and_default_form_is_pko(incomes):
    cash = incomes.add(OCT14, "Korepetycje", zl("174,00"), IncomeForm.GOTOWKA)
    bank = incomes.add(OCT14, "Zlecenie", zl("174,00"))
    assert (cash.form, bank.form) == (IncomeForm.GOTOWKA, IncomeForm.PKO)
    assert cash.split == bank.split


def test_form_can_be_changed_when_unsettled(incomes):
    view = incomes.add(OCT14, "Zlecenie", zl("174,00"))
    assert incomes.update(view.id, OCT14, "Zlecenie", zl("174,00"), IncomeForm.GOTOWKA).form is IncomeForm.GOTOWKA


def test_month_sums_by_form(incomes):
    incomes.add(date(2026, 10, 5), "Stypendium", zl("2401,30"))
    incomes.add(OCT14, "Korepetycje", zl("174,00"), IncomeForm.GOTOWKA)
    summary = incomes.month(2026, 10)
    assert summary.by_form == {IncomeForm.PKO: zl("2401,30"), IncomeForm.GOTOWKA: zl("174,00")}
    assert summary.total == zl("2575,30")

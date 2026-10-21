from datetime import date

import pytest
from sqlalchemy import select

from finbro.db.models import EnvelopeAccount, IncomeShare, SettlementLine
from finbro.domain.envelopes import Envelope
from finbro.domain.money import Money
from finbro.services.incomes import IncomeService
from finbro.services.settlements import SettlementError, SettlementService

P, W, X, O = Envelope.PKO, Envelope.WAKACJE, Envelope.XTB, Envelope.OBLIGACJE
DAY = date(2026, 10, 19)


def zl(text):
    return Money.parse(text)


@pytest.fixture
def incomes(db_session):
    return IncomeService(db_session)


@pytest.fixture
def settlements(db_session):
    return SettlementService(db_session)


@pytest.fixture
def two_incomes(incomes):
    return [incomes.add(date(2026, 10, 5), "Stypendium", zl("2401,30")), incomes.add(date(2026, 10, 14), "Zlecenie", zl("174"))]


def settle_pending(settlements, day=DAY):
    pending = settlements.pending(day)
    return settlements.settle(pending.income_ids, pending.expected, day)


def test_pending_transfers_with_accounts(db_session, settlements, two_incomes):
    db_session.add(EnvelopeAccount(envelope="XTB", target_account="52 1050 0000 1111 2222 3333 4444"))
    db_session.commit()
    pending = settlements.pending(DAY)
    assert pending.income_ids == [i.id for i in two_incomes]
    assert [(t.transfer.envelope, t.transfer.amount, t.target_account) for t in pending.transfers] == [
        (W, zl("644"), None),
        (X, zl("322"), "52 1050 0000 1111 2222 3333 4444"),
        (O, zl("322"), None),
    ]
    assert pending.transfers[1].transfer.title == "FinBro XTB 2026-10-19"


def test_settle_marks_incomes_and_records_history(db_session, incomes, settlements, two_incomes):
    view = settle_pending(settlements)
    assert view.lines == {W: zl("644"), X: zl("322"), O: zl("322")}
    assert (view.date, view.income_count, view.is_latest) == (DAY, 2, True)
    assert all(incomes.get(i.id).settled for i in two_incomes)
    assert settlements.pending(DAY).transfers == []
    # Zamrożony podział każdego dochodu (cztery koperty).
    assert len(db_session.scalars(select(IncomeShare)).all()) == 8


def test_income_added_meanwhile_stays_unsettled(incomes, settlements, two_incomes):
    pending = settlements.pending(DAY)
    later = incomes.add(date(2026, 10, 18), "Później", zl("100"))
    settlements.settle(pending.income_ids, pending.expected, DAY)
    assert not incomes.get(later.id).settled
    assert [i.id for i in settlements.pending(DAY).incomes] == [later.id]


def test_changed_amount_after_display_is_rejected(incomes, settlements, two_incomes):
    pending = settlements.pending(DAY)
    incomes.update(two_incomes[1].id, date(2026, 10, 14), "Zlecenie", zl("300"))
    with pytest.raises(SettlementError, match="Odśwież"):
        settlements.settle(pending.income_ids, pending.expected, DAY)
    assert not incomes.get(two_incomes[0].id).settled


def test_already_settled_or_empty_list_is_rejected(settlements, two_incomes):
    pending = settlements.pending(DAY)
    settlements.settle(pending.income_ids, pending.expected, DAY)
    with pytest.raises(SettlementError, match="zmieniła się"):
        settlements.settle(pending.income_ids, pending.expected, DAY)
    with pytest.raises(SettlementError, match="Brak dochodów"):
        settlements.settle([], {}, DAY)


def test_undo_latest_restores_pending(db_session, incomes, settlements, two_incomes):
    first = settle_pending(settlements, date(2026, 10, 12))
    incomes.add(date(2026, 10, 16), "Kolejny", zl("100"))
    second = settle_pending(settlements)

    with pytest.raises(SettlementError, match="najnowsze"):
        settlements.undo(first.id)

    settlements.undo(second.id)
    assert [s.id for s in settlements.history()] == [first.id]
    assert settlements.history()[0].is_latest
    pending = settlements.pending(DAY)
    assert [i.source for i in pending.incomes] == ["Kolejny"]
    assert db_session.scalars(select(SettlementLine).where(SettlementLine.settlement_id == second.id)).all() == []


def test_history_newest_first(incomes, settlements, two_incomes):
    first = settle_pending(settlements, date(2026, 10, 12))
    incomes.add(date(2026, 10, 16), "Kolejny", zl("100"))
    second = settle_pending(settlements)
    history = settlements.history()
    assert [(s.id, s.income_count, s.is_latest) for s in history] == [(second.id, 1, True), (first.id, 2, False)]
    assert history[0].lines == {W: zl("25"), X: zl("13"), O: zl("13")}
    assert history[0].total == zl("51")


@pytest.fixture
def equal_incomes(incomes):
    return [incomes.add(date(2026, 10, 15), "Później", zl("174")), incomes.add(date(2026, 10, 14), "Zlecenie", zl("174"))]



def test_pending_transfers_are_rounded_from_the_sum(settlements, equal_incomes):
    # 348 × 25% = 87 zł, a nie 44 + 44 z podziałów pojedynczych dochodów.
    pending = settlements.pending(DAY)
    assert pending.expected == {W: zl("87"), X: zl("44"), O: zl("44")}


def test_settle_freezes_split_distributed_from_transfers(db_session, incomes, settlements, equal_incomes):
    later, earlier = equal_incomes
    view = settle_pending(settlements)
    assert view.lines == {W: zl("87"), X: zl("44"), O: zl("44")}
    # Remis reszt (43,50 + 43,50): brakujący złoty Wakacji dostaje wcześniejszy dochód, choć wpisany później.
    assert incomes.get(earlier.id).split == {P: zl("86"), W: zl("44"), X: zl("22"), O: zl("22")}
    assert incomes.get(later.id).split == {P: zl("87"), W: zl("43"), X: zl("22"), O: zl("22")}
    assert incomes.month(2026, 10).totals == {P: zl("173"), W: zl("87"), X: zl("44"), O: zl("44")}


def test_settlement_lines_equal_frozen_shares(db_session, incomes, settlements, two_incomes, equal_incomes):
    incomes.add(date(2026, 10, 16), "Drobne", zl("1,98"))
    view = settle_pending(settlements)
    shares = db_session.scalars(select(IncomeShare).where(IncomeShare.settlement_id == view.id)).all()
    for envelope in (W, X, O):
        assert sum(s.amount for s in shares if s.envelope == envelope.value) == view.lines[envelope].grosze


def test_undo_restores_preview_split(incomes, settlements, equal_incomes):
    later, _ = equal_incomes
    settlements.undo(settle_pending(settlements).id)
    assert incomes.get(later.id).split == {P: zl("86"), W: zl("44"), X: zl("22"), O: zl("22")}

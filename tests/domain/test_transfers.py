from datetime import date

from finbro.domain.allocation import Plan, split
from finbro.domain.envelopes import Envelope
from finbro.domain.money import Money
from finbro.domain.transfers import Transfer, transfer_title, transfers

P, W, X, O = Envelope.PKO, Envelope.WAKACJE, Envelope.XTB, Envelope.OBLIGACJE
DEFAULT = Plan(date(2000, 1, 1), {P: 5000, W: 2500, X: 1250, O: 1250})
DAY = date(2026, 10, 19)


def zl(text):
    return Money.parse(text)


def test_two_incomes_give_three_transfers_without_pko():
    result = transfers([split(zl("2401,30"), DEFAULT), split(zl("174"), DEFAULT)], DAY)
    assert result == [
        Transfer(W, zl("644"), "FinBro Wakacje 2026-10-19"),
        Transfer(X, zl("322"), "FinBro XTB 2026-10-19"),
        Transfer(O, zl("322"), "FinBro Obligacje 2026-10-19"),
    ]


def test_envelope_with_zero_sum_is_skipped():
    # 1,98 zł: Wakacje, XTB i Obligacje zaokrąglają się do 0 zł.
    assert transfers([split(zl("1,98"), DEFAULT)], DAY) == []
    no_bonds = Plan(date(2000, 1, 1), {P: 5000, W: 2500, X: 2500, O: 0})
    assert [t.envelope for t in transfers([split(zl("100"), no_bonds)], DAY)] == [W, X]


def test_no_incomes_no_transfers():
    assert transfers([], DAY) == []


def test_title_format():
    assert transfer_title(O, date(2026, 1, 5)) == "FinBro Obligacje 2026-01-05"

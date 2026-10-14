from datetime import date

from finbro.domain.envelopes import Envelope
from finbro.domain.money import Money
from finbro.domain.networth import BalanceEntry, Contribution, balance, difference, snapshot, timeline

P, W, X, O = Envelope.PKO, Envelope.WAKACJE, Envelope.XTB, Envelope.OBLIGACJE
OCT12, OCT19, OCT20, NOV1 = date(2026, 10, 12), date(2026, 10, 19), date(2026, 10, 20), date(2026, 11, 1)


def zl(text):
    return Money.parse(text)


XTB_START = BalanceEntry(X, OCT12, zl("1200"))
XTB_TRANSFER = Contribution(X, OCT19, zl("322"))


def test_entry_sets_balance():
    assert balance(X, [XTB_START], [], OCT12) == zl("1200")
    assert balance(X, [XTB_START], [], date(2026, 10, 11)) is None


def test_transfer_after_entry_is_added():
    assert balance(X, [XTB_START], [XTB_TRANSFER], OCT19) == zl("1522")
    assert balance(X, [XTB_START], [XTB_TRANSFER], date(2026, 10, 18)) == zl("1200")


def test_transfer_before_newer_entry_is_not_counted_twice():
    entries = [XTB_START, BalanceEntry(X, OCT20, zl("1550"))]
    assert balance(X, entries, [XTB_TRANSFER], OCT20) == zl("1550")


def test_transfer_on_entry_day_is_included_in_entry():
    assert balance(X, [BalanceEntry(X, OCT19, zl("1500"))], [XTB_TRANSFER], OCT19) == zl("1500")


def test_without_entries_balance_is_sum_of_transfers():
    assert balance(O, [], [Contribution(O, OCT12, zl("300")), Contribution(O, OCT19, zl("22"))], OCT19) == zl("322")


def test_difference_shows_gain_or_loss():
    gain = BalanceEntry(X, NOV1, zl("1560"))
    assert difference(gain, [XTB_START, gain], [XTB_TRANSFER]) == zl("38")
    loss = BalanceEntry(X, NOV1, zl("1500"))
    assert difference(loss, [XTB_START, loss], [XTB_TRANSFER]) == zl("-22")
    assert difference(BalanceEntry(O, NOV1, zl("10")), [], []) is None


def test_pko_only_from_entries():
    pko = BalanceEntry(P, OCT12, zl("3000"))
    assert balance(P, [pko], [Contribution(X, OCT19, zl("43"))], OCT19) == zl("3000")
    assert balance(P, [], [], OCT19) is None


def test_total_net_worth_excludes_holidays():
    entries = [BalanceEntry(P, OCT12, zl("3000")), XTB_START, BalanceEntry(O, OCT12, zl("1088,25"))]
    contributions = [XTB_TRANSFER, Contribution(O, OCT19, zl("322")), Contribution(W, OCT19, zl("644"))]
    snap = snapshot(entries, contributions, OCT19)
    assert snap.balances == {P: zl("3000"), X: zl("1522"), O: zl("1410,25")}
    assert snap.total == zl("5932,25")


def test_timeline_points_on_entry_and_settlement_days():
    entries = [BalanceEntry(P, OCT12, zl("3000")), XTB_START]
    contributions = [XTB_TRANSFER, Contribution(W, OCT20, zl("644"))]  # Wakacje nie tworzą punktu
    points = timeline(entries, contributions)
    assert [(p.day, p.total) for p in points] == [(OCT12, zl("4200")), (OCT19, zl("4522"))]


def test_empty_timeline():
    assert timeline([], []) == []
    assert snapshot([], [], OCT12).total == Money.zero()

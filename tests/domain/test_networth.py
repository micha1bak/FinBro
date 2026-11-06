from datetime import date

from finbro.domain.envelopes import Envelope
from finbro.domain.money import Money
from finbro.domain.networth import Account, BalanceEntry, Contribution, balance, difference, snapshot, timeline

P, G, F, X, O = Account.PKO, Account.GOTOWKA, Account.WAKACJE, Account.XTB, Account.OBLIGACJE
W = Envelope.WAKACJE
OCT12, OCT19, OCT20, NOV1 = date(2026, 10, 12), date(2026, 10, 19), date(2026, 10, 20), date(2026, 11, 1)


def zl(text):
    return Money.parse(text)


XTB_START = BalanceEntry(X, OCT12, zl("1200"))
XTB_TRANSFER = Contribution(Envelope.XTB, OCT19, zl("322"))


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
    assert balance(O, [], [Contribution(Envelope.OBLIGACJE, OCT12, zl("300")), Contribution(Envelope.OBLIGACJE, OCT19, zl("22"))], OCT19) == zl("322")


def test_difference_shows_gain_or_loss():
    gain = BalanceEntry(X, NOV1, zl("1560"))
    assert difference(gain, [XTB_START, gain], [XTB_TRANSFER]) == zl("38")
    loss = BalanceEntry(X, NOV1, zl("1500"))
    assert difference(loss, [XTB_START, loss], [XTB_TRANSFER]) == zl("-22")
    assert difference(BalanceEntry(O, NOV1, zl("10")), [], []) is None


def test_pko_only_from_entries():
    pko = BalanceEntry(P, OCT12, zl("3000"))
    assert balance(P, [pko], [Contribution(Envelope.XTB, OCT19, zl("43"))], OCT19) == zl("3000")
    assert balance(P, [], [], OCT19) is None


def test_total_net_worth_with_cash_and_vacation_fund():
    entries = [
        BalanceEntry(P, OCT12, zl("3000")), BalanceEntry(G, OCT12, zl("250")), BalanceEntry(F, OCT12, zl("500")),
        XTB_START, BalanceEntry(O, OCT12, zl("1088,25")),
    ]
    contributions = [XTB_TRANSFER, Contribution(Envelope.OBLIGACJE, OCT19, zl("322")), Contribution(W, OCT19, zl("644"))]
    snap = snapshot(entries, contributions, OCT19)
    assert snap.balances == {P: zl("3000"), G: zl("250"), F: zl("1144"), X: zl("1522"), O: zl("1410,25")}
    assert snap.total == zl("7326,25")


def test_vacation_fund_grows_with_settlements_and_entry_corrects_it():
    start, transfer = BalanceEntry(F, OCT12, zl("500")), Contribution(W, OCT19, zl("103"))
    assert balance(F, [start], [transfer], OCT19) == zl("603")
    spent = BalanceEntry(F, NOV1, zl("200"))
    assert balance(F, [start, spent], [transfer], NOV1) == zl("200")
    assert difference(spent, [start, spent], [transfer]) == zl("-403")
    assert difference(start, [start, spent], [transfer]) is None  # pierwszy wpis nie ma z czym się różnić


def test_backdated_entries_rebuild_history_on_every_day():
    """Wpisy z przeszłości poprawiają wcześniejsze punkty wykresu i różnice bez przeliczania czegokolwiek."""
    pko = [BalanceEntry(P, d, zl("1000")) for d in (OCT12, OCT19, NOV1)]
    transfers = [Contribution(W, OCT19, zl("103")), Contribution(W, NOV1, zl("203"))]
    assert [p.total for p in timeline(pko, transfers)] == [zl("1000"), zl("1103"), zl("1306")]  # sam wyliczony fundusz

    fund = [BalanceEntry(F, OCT12, zl("500")), BalanceEntry(F, OCT19, zl("603")), BalanceEntry(F, NOV1, zl("800"))]
    entries = pko + fund
    assert [p.total for p in timeline(entries, transfers)] == [zl("1500"), zl("1603"), zl("1800")]
    assert [difference(e, entries, transfers) for e in fund] == [None, Money.zero(), zl("-6")]


def test_cash_only_from_entries_and_without_difference():
    cash = BalanceEntry(G, OCT12, zl("250"))
    assert balance(G, [cash], [XTB_TRANSFER, Contribution(W, OCT19, zl("44"))], OCT19) == zl("250")
    later = BalanceEntry(G, OCT20, zl("180"))
    assert difference(later, [cash, later], []) is None


def test_timeline_points_on_entry_and_settlement_days():
    entries = [BalanceEntry(P, OCT12, zl("3000")), XTB_START]
    contributions = [XTB_TRANSFER, Contribution(W, OCT20, zl("644")), Contribution(Envelope.PKO, NOV1, zl("10"))]
    points = timeline(entries, contributions)  # koperta PKO nie tworzy punktu
    assert [(p.day, p.total) for p in points] == [(OCT12, zl("4200")), (OCT19, zl("4522")), (OCT20, zl("5166"))]


def test_empty_timeline():
    assert timeline([], []) == []
    assert snapshot([], [], OCT12).total == Money.zero()

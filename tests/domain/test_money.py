import pytest
from hypothesis import given
from hypothesis import strategies as st

from finbro.domain.money import NBSP, Money, MoneyParseError


@pytest.mark.parametrize(
    ("text", "grosze"),
    [
        ("-645.00", -64500),
        ("+2753,36", 275336),
        ("1 234,56", 123456),
        (f"1{NBSP}234,56", 123456),
        ("0.01", 1),
        ("-0,07", -7),
        ("12,5", 1250),
        ("100", 10000),
        ("  4950.03 ", 495003),
        ("6351.56", 635156),
    ],
)
def test_parse(text, grosze):
    assert Money.parse(text) == Money(grosze)


@pytest.mark.parametrize("text", ["", "abc", "1,234,56", "1.234,56", "12.345", "--5", "5-", "1e3", ",50"])
def test_parse_rejects_invalid(text):
    with pytest.raises(MoneyParseError):
        Money.parse(text)


def test_parse_rejects_sub_grosz_precision():
    # Trzy miejsca po przecinku oznaczałyby utratę dokładności, więc są błędem.
    with pytest.raises(MoneyParseError):
        Money.parse("0.005")


@pytest.mark.parametrize(
    ("grosze", "expected"),
    [
        (64500, "645,00 zł"),
        (-64500, "-645,00 zł"),
        (495003, "4950,03 zł"),
        (1234567, f"12{NBSP}345,67 zł"),
        (123456789, f"1{NBSP}234{NBSP}567,89 zł"),
        (7, "0,07 zł"),
        (0, "0,00 zł"),
    ],
)
def test_format_polish(grosze, expected):
    assert Money(grosze).format().replace(f"{NBSP}zł", " zł") == expected


def test_format_options():
    assert Money(3750).format(plus=True, currency=False) == "+37,50"
    assert Money(-8125).format(plus=True, currency=False) == "-81,25"
    assert Money(-64500).to_plain() == "-645.00"
    assert Money(5).to_plain() == "0.05"


def test_sign_helpers_and_arithmetic():
    a, b = Money.parse("1237.50"), Money.parse("1200.00")
    assert a - b == Money(3750)
    assert b - a == Money(-3750)
    assert -a == Money(-123750)
    assert abs(Money(-5)) == Money(5)
    assert Money(-1).is_negative and Money(1).is_positive and Money(0).is_zero
    assert Money(3) * 4 == Money(12) == 4 * Money(3)
    assert sum([Money(1), Money(2), Money(3)]) == Money(6)
    assert Money(1) < Money(2)


def test_money_requires_int():
    with pytest.raises(TypeError):
        Money(1.5)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        Money(True)  # type: ignore[arg-type]


@given(st.integers(min_value=-10**12, max_value=10**12))
def test_plain_roundtrip_has_no_precision_loss(grosze):
    money = Money(grosze)
    assert Money.parse(money.to_plain()) == money
    assert Money.parse(money.format(currency=False)) == money

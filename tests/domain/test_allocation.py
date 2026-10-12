from datetime import date

import pytest
from hypothesis import given
from hypothesis import strategies as st

from finbro.domain.allocation import (
    AllocationError,
    AllocationPlan,
    format_basis_points,
    plan_for_date,
    split_amount,
    validate_shares,
)
from finbro.domain.money import Money

DEFAULT_SHARES = {"zycie": 5000, "xtb": 1250, "obligacje": 1250, "wakacje": 2500}


def test_split_with_rounding_down_and_remainder_for_life():
    parts = split_amount(Money.parse("4950.03"), DEFAULT_SHARES, "zycie")
    assert parts == {
        "xtb": Money.parse("618.75"),
        "obligacje": Money.parse("618.75"),
        "wakacje": Money.parse("1237.50"),
        "zycie": Money.parse("2475.03"),
    }


def test_negative_split_mirrors_positive():
    positive = split_amount(Money.parse("400.07"), DEFAULT_SHARES, "zycie")
    negative = split_amount(Money.parse("-400.07"), DEFAULT_SHARES, "zycie")
    assert negative == {k: -v for k, v in positive.items()}


def test_zero_split():
    assert all(v.is_zero for v in split_amount(Money(0), DEFAULT_SHARES, "zycie").values())


@pytest.mark.parametrize(
    "shares",
    [
        {"zycie": 5000, "xtb": 1250, "obligacje": 1250, "wakacje": 2000},  # 95%
        {"zycie": 6000, "xtb": 1250, "obligacje": 1250, "wakacje": 2500},  # 110%
    ],
)
def test_shares_must_sum_to_100_percent(shares):
    with pytest.raises(AllocationError, match="100%"):
        validate_shares(shares, "zycie")


def test_shares_require_life_and_non_negative():
    with pytest.raises(AllocationError, match="Życie"):
        validate_shares({"xtb": 10000}, "zycie")
    with pytest.raises(AllocationError, match="ujemny"):
        validate_shares({"zycie": 11000, "xtb": -1000}, "zycie")


def test_format_basis_points():
    assert format_basis_points(1250) == "12,5%"
    assert format_basis_points(5000) == "50%"
    assert format_basis_points(9500) == "95%"
    assert format_basis_points(3333) == "33,33%"


def test_plan_for_date_uses_plan_effective_on_that_day():
    old = AllocationPlan(date(2026, 10, 12), DEFAULT_SHARES, "zycie")
    new = AllocationPlan(date(2026, 11, 2), {"zycie": 6000, "xtb": 1000, "obligacje": 1000, "wakacje": 2000}, "zycie")
    plans = [new, old]
    assert plan_for_date(plans, date(2026, 11, 1)) is old
    assert plan_for_date(plans, date(2026, 11, 2)) is new
    assert plan_for_date(plans, date(2027, 1, 1)) is new
    with pytest.raises(AllocationError):
        plan_for_date(plans, date(2026, 10, 1))


def test_plan_validates_on_creation():
    with pytest.raises(AllocationError):
        AllocationPlan(date(2026, 1, 1), {"zycie": 9500}, "zycie")


share_vectors = st.lists(st.integers(min_value=0, max_value=10_000), min_size=1, max_size=5).filter(
    lambda xs: sum(xs) <= 10_000
)


@given(st.integers(min_value=-10**11, max_value=10**11), share_vectors)
def test_sum_of_envelopes_equals_input(total_grosze, others):
    shares = {f"k{i}": bp for i, bp in enumerate(others)}
    shares["zycie"] = 10_000 - sum(others)
    total = Money(total_grosze)
    parts = split_amount(total, shares, "zycie")
    assert sum(parts.values()) == total
    for key, bp in shares.items():
        if key != "zycie":
            # Udział zaokrąglony w dół co do wartości bezwzględnej, z błędem poniżej grosza.
            exact = abs(total_grosze) * bp / 10_000
            assert abs(parts[key].grosze) <= exact < abs(parts[key].grosze) + 1

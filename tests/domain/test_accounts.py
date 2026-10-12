import pytest

from finbro.domain.accounts import account_matches, normalize_account

MAIN = "27 1020 1026 0000 1234 5678 9012"


def test_normalize():
    assert normalize_account("PL27 1020 1026 0000-1234 5678 9012") == "PL27102010260000123456789012"
    assert normalize_account(None) == ""


@pytest.mark.parametrize(
    "candidate",
    [
        MAIN,
        "PL27102010260000123456789012",
        "27 1020 **** **** **** **** 9012",
        "271020102600********789012",
    ],
)
def test_matches(candidate):
    assert account_matches(candidate, MAIN)
    assert account_matches(candidate, "PL" + MAIN)


@pytest.mark.parametrize(
    "candidate",
    [
        "83 1020 5555 0000 9876 5432 1098",
        "27 1020 **** **** **** **** 9013",
        "28 1020 **** **** **** **** 9012",
        "27 1020 **** 9012",  # inna długość
        "**** **** ****",
        "",
    ],
)
def test_does_not_match(candidate):
    assert not account_matches(candidate, MAIN)


def test_unconfigured_account_never_matches():
    assert not account_matches(MAIN, None)
    assert not account_matches(MAIN, "")


def test_same_account():
    from finbro.domain.accounts import same_account

    assert same_account("PL61 1140 2004 0000 3502 7777 0001", "61114020040000350277770001")
    assert not same_account("61 1140 2004 0000 3502 7777 0001", "61 1140 2004 0000 3502 7777 0002")
    assert not same_account("27 1020 **** 9012", "27 1020 **** 9012")
    assert not same_account(None, None)

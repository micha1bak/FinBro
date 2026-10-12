import pytest

from finbro.domain.classification import (
    ClassificationError,
    check_category_choice,
    check_classification,
    check_type,
    normalized,
    types_for,
)
from finbro.domain.enums import TransferKind, TxType
from finbro.domain.reference import Category
from finbro.domain.transactions import Classification, Direction

IN, OUT = Direction.IN, Direction.OUT


def test_income_rejected_for_expense():
    with pytest.raises(ClassificationError, match="nie pasuje do kierunku"):
        check_type(OUT, TxType.DOCHOD)


def test_expense_requires_category():
    with pytest.raises(ClassificationError, match="wymaga wskazania kategorii"):
        check_type(OUT, TxType.WYDATEK)
    check_type(OUT, TxType.WYDATEK, category_id=1)


@pytest.mark.parametrize("tx_type", [TxType.ZWROT, TxType.ROZLICZENIE])
def test_refund_and_settlement_require_category(tx_type):
    with pytest.raises(ClassificationError, match="kategorii"):
        check_type(IN, tx_type)
    check_type(IN, tx_type, category_id=3)


@pytest.mark.parametrize(("direction", "tx_type"), [(OUT, TxType.POZYCZKA), (IN, TxType.SPLATA)])
def test_loan_and_repayment_require_debtor(direction, tx_type):
    with pytest.raises(ClassificationError, match="dłużnika"):
        check_type(direction, tx_type)
    check_type(direction, tx_type, debtor_id=7)


@pytest.mark.parametrize(
    ("direction", "tx_type"),
    [(OUT, TxType.ZWROT), (OUT, TxType.SPLATA), (IN, TxType.ODKLADANIE), (IN, TxType.POZYCZKA), (IN, TxType.WYDATEK)],
)
def test_wrong_direction(direction, tx_type):
    with pytest.raises(ClassificationError):
        check_type(direction, tx_type, category_id=1, debtor_id=1)


def test_transfer_in_both_directions():
    check_type(IN, TxType.TRANSFER)
    check_type(OUT, TxType.TRANSFER)


def test_types_for_direction():
    assert types_for(IN) == [TxType.DOCHOD, TxType.TRANSFER, TxType.ZWROT, TxType.ROZLICZENIE, TxType.SPLATA]
    assert types_for(OUT) == [TxType.WYDATEK, TxType.ODKLADANIE, TxType.TRANSFER, TxType.POZYCZKA]


def test_category_choice():
    system = Category(id=1, name="Gotówka (bez kategorii)", active=True, is_system=True, sort_order=999)
    inactive = Category(id=2, name="Stara", active=False, is_system=False, sort_order=1)
    normal = Category(id=3, name="Spożywcze", active=True, is_system=False, sort_order=1)
    with pytest.raises(ClassificationError, match="systemowa"):
        check_category_choice(system, chosen_by_user=True)
    check_category_choice(system, chosen_by_user=False)
    with pytest.raises(ClassificationError, match="nieaktywna"):
        check_category_choice(inactive, chosen_by_user=True)
    check_category_choice(normal, chosen_by_user=True)


def test_confirmed_requires_type():
    with pytest.raises(ClassificationError):
        check_classification(IN, Classification(confirmed=True))
    check_classification(IN, Classification())


def test_normalized_drops_irrelevant_fields():
    c = normalized(Classification(type=TxType.TRANSFER, category_id=1, debtor_id=2))
    assert (c.category_id, c.debtor_id, c.transfer_kind) == (None, None, TransferKind.OTHER)
    c = normalized(Classification(type=TxType.WYDATEK, category_id=1, debtor_id=2, transfer_kind=TransferKind.WALLET))
    assert (c.category_id, c.debtor_id, c.transfer_kind) == (1, None, None)

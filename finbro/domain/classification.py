"""Zasady klasyfikacji: dozwolone kierunki typów oraz wymagane kategorie i dłużnicy."""

from __future__ import annotations

from dataclasses import replace

from finbro.domain.enums import ProposalSource, TransferKind, TxType
from finbro.domain.reference import Category
from finbro.domain.transactions import Classification, Direction


class ClassificationError(ValueError):
    """Klasyfikacja niezgodna z zasadami (kierunek, brak kategorii lub dłużnika)."""


ALLOWED_DIRECTIONS: dict[TxType, frozenset[Direction]] = {
    TxType.DOCHOD: frozenset({Direction.IN}),
    TxType.ZWROT: frozenset({Direction.IN}),
    TxType.ROZLICZENIE: frozenset({Direction.IN}),
    TxType.SPLATA: frozenset({Direction.IN}),
    TxType.WYDATEK: frozenset({Direction.OUT}),
    TxType.ODKLADANIE: frozenset({Direction.OUT}),
    TxType.POZYCZKA: frozenset({Direction.OUT}),
    TxType.TRANSFER: frozenset({Direction.IN, Direction.OUT}),
}

REQUIRES_CATEGORY = frozenset({TxType.WYDATEK, TxType.ZWROT, TxType.ROZLICZENIE})
REQUIRES_DEBTOR = frozenset({TxType.POZYCZKA, TxType.SPLATA})

# Typy, które nie są ani przychodem, ani wydatkiem.
NEUTRAL_TYPES = frozenset({TxType.TRANSFER, TxType.ODKLADANIE, TxType.POZYCZKA, TxType.SPLATA})


def types_for(direction: Direction) -> list[TxType]:
    """Typy dozwolone dla kierunku, w kolejności wyliczenia."""
    return [t for t in TxType if direction in ALLOWED_DIRECTIONS[t]]


def check_type(
    direction: Direction,
    tx_type: TxType,
    *,
    category_id: int | None = None,
    debtor_id: int | None = None,
) -> None:
    if direction not in ALLOWED_DIRECTIONS[tx_type]:
        raise ClassificationError(
            f"Typ {tx_type.label} nie pasuje do kierunku operacji ({direction.label}). "
            f"Dozwolone typy: {', '.join(t.label for t in types_for(direction))}."
        )
    if tx_type in REQUIRES_CATEGORY and category_id is None:
        raise ClassificationError(f"Typ {tx_type.label} wymaga wskazania kategorii.")
    if tx_type in REQUIRES_DEBTOR and debtor_id is None:
        raise ClassificationError(f"Typ {tx_type.label} wymaga wskazania dłużnika.")


def check_category_choice(category: Category, *, chosen_by_user: bool) -> None:
    """Kategoria systemowa i kategorie nieaktywne nie są dostępne do ręcznego wyboru."""
    if chosen_by_user and category.is_system:
        raise ClassificationError(f"Kategoria „{category.name}” jest systemowa i nie można jej wybrać ręcznie.")
    if not category.active:
        raise ClassificationError(f"Kategoria „{category.name}” jest nieaktywna.")


def normalized(classification: Classification, keep_debtor: bool = False) -> Classification:
    """Usuwa pola, które nie dotyczą danego typu (np. kategorię przy TRANSFERZE).

    ``keep_debtor`` zachowuje dłużnika przy wydatku z darowania długu.
    """
    t = classification.type
    if t is None:
        return classification
    return replace(
        classification,
        category_id=classification.category_id if t in REQUIRES_CATEGORY else None,
        debtor_id=classification.debtor_id if t in REQUIRES_DEBTOR or keep_debtor else None,
        transfer_kind=(classification.transfer_kind or TransferKind.OTHER) if t is TxType.TRANSFER else None,
        envelope_id=classification.envelope_id if t is TxType.ODKLADANIE else None,
    )


def is_auto_accepted(direction: Direction, proposal: Classification) -> bool:
    """Reguły akceptacji z D9.

    DOCHÓD zawsze wymaga zatwierdzenia. Propozycje dla wydatków są przyjmowane
    automatycznie z każdego źródła. Wpływy innego typu niż DOCHÓD są przyjmowane
    automatycznie tylko wtedy, gdy pochodzą z reguły; z historii i od modelu trafiają do skrzynki.
    Propozycja niespełniająca wymagań typu (np. bez kategorii) nigdy nie jest przyjmowana.
    """
    if proposal.type is None or proposal.type is TxType.DOCHOD:
        return False
    try:
        check_classification(direction, proposal)
    except ClassificationError:
        return False
    if direction is Direction.OUT:
        return True
    return proposal.source is ProposalSource.RULE


def check_classification(direction: Direction, classification: Classification) -> None:
    if classification.type is None:
        if classification.confirmed:
            raise ClassificationError("Zatwierdzona transakcja musi mieć typ.")
        return
    check_type(
        direction,
        classification.type,
        category_id=classification.category_id,
        debtor_id=classification.debtor_id,
    )

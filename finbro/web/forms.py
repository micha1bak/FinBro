"""Wspólne formularze klasyfikacji (skrzynka i lista transakcji)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from fastapi import Request

from finbro.domain.classification import ClassificationError, types_for
from finbro.domain.enums import TransferKind, TxType
from finbro.services.classification import Decision
from finbro.services.uow import UnitOfWork


def is_htmx(request: Request) -> bool:
    return request.headers.get("HX-Request") == "true"


def _int_or_none(value: Any) -> int | None:
    return int(value) if value not in (None, "") else None


def decision_from_form(form: Mapping[str, Any]) -> Decision:
    try:
        tx_type = TxType(form.get("type", ""))
    except ValueError as exc:
        raise ClassificationError("Wybierz typ transakcji.") from exc
    kind = form.get("transfer_kind") or None
    return Decision(
        type=tx_type,
        category_id=_int_or_none(form.get("category_id")),
        debtor_id=_int_or_none(form.get("debtor_id")),
        transfer_kind=TransferKind(kind) if kind else None,
        envelope_id=_int_or_none(form.get("envelope_id")),
        new_debtor_name=(form.get("new_debtor_name") or "").strip() or None,
        remember=form.get("remember") in ("on", "true", "1"),
    )


def form_context(uow: UnitOfWork) -> dict[str, Any]:
    categories = uow.reference.categories()
    return {
        "categories_by_id": {c.id: c for c in categories},
        "selectable_categories": [c for c in categories if c.active and not c.is_system],
        "debtors": uow.reference.debtors(),
        "debtors_by_id": {d.id: d for d in uow.reference.debtors()},
        "envelopes": [e for e in uow.reference.envelopes() if not e.is_life],
        "envelopes_by_id": {e.id: e for e in uow.reference.envelopes()},
        "transfer_kinds": list(TransferKind),
        "types_for": types_for,
    }

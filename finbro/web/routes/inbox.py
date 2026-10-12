"""Skrzynka: pozycje czekające na decyzję użytkownika."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from finbro.domain.classification import ClassificationError, types_for
from finbro.domain.enums import ProposalSource, TransferKind, TxType
from finbro.domain.transactions import Transaction
from finbro.services.classification import ClassificationService, Decision
from finbro.services.uow import UnitOfWork
from finbro.web.deps import get_uow
from finbro.web.templating import templates

router = APIRouter()


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


def render_row(request: Request, uow: UnitOfWork, tx: Transaction, error: str | None = None) -> HTMLResponse:
    return templates.TemplateResponse(
        request, "_inbox_row.html", {"tx": tx, "error": error, **form_context(uow), **inbox_extras(uow, [tx])}
    )


def inbox_extras(uow: UnitOfWork, items: list[Transaction]) -> dict[str, Any]:
    """Dodatkowe dane skrzynki; rozszerzane przez kolejne funkcje (należności, kolejka LLM)."""
    return {"queued_ids": uow.llm_jobs.queued_transaction_ids()}


@router.get("/inbox", response_class=HTMLResponse)
def inbox(request: Request, uow: UnitOfWork = Depends(get_uow)) -> HTMLResponse:
    items = uow.transactions.unconfirmed()
    rule_incomes = sum(
        1 for t in items if t.classification.type is TxType.DOCHOD and t.classification.source is ProposalSource.RULE
    )
    return templates.TemplateResponse(
        request,
        "inbox.html",
        {
            "items": items,
            "rule_incomes": rule_incomes,
            "message": request.query_params.get("msg"),
            **form_context(uow),
            **inbox_extras(uow, items),
        },
    )


def _done(request: Request, message: str | None = None) -> Response:
    if is_htmx(request):
        return HTMLResponse("")
    url = "/inbox" + (f"?msg={message}" if message else "")
    return RedirectResponse(url, status_code=303)


def _failed(request: Request, uow: UnitOfWork, transaction_id: int, error: str) -> Response:
    tx = uow.transactions.get(transaction_id)
    response = render_row(request, uow, tx, error=error)
    if not is_htmx(request):
        response.status_code = 400
    return response


@router.post("/inbox/{transaction_id}/accept")
def accept(request: Request, transaction_id: int, uow: UnitOfWork = Depends(get_uow)) -> Response:
    try:
        ClassificationService(uow).accept_proposal(transaction_id)
    except ClassificationError as exc:
        return _failed(request, uow, transaction_id, str(exc))
    return _done(request)


def _decide(request: Request, transaction_id: int, uow: UnitOfWork, form: Mapping[str, Any]) -> Response:
    try:
        ClassificationService(uow).decide(transaction_id, decision_from_form(form))
    except (ClassificationError, ValueError) as exc:
        return _failed(request, uow, transaction_id, str(exc))
    return _done(request)


@router.post("/inbox/{transaction_id}/decide")
async def decide(request: Request, transaction_id: int, uow: UnitOfWork = Depends(get_uow)) -> Response:
    form = dict(await request.form())
    return await run_in_threadpool(_decide, request, transaction_id, uow, form)


@router.post("/inbox/approve-rule-incomes")
def approve_rule_incomes(request: Request, uow: UnitOfWork = Depends(get_uow)) -> Response:
    count = ClassificationService(uow).approve_rule_incomes()
    return RedirectResponse(f"/inbox?msg=Zatwierdzono dochody z reguł: {count}", status_code=303)

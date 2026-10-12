"""Skrzynka: pozycje czekające na decyzję użytkownika."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from finbro.domain.classification import ClassificationError
from finbro.domain.enums import ProposalSource, TxType
from finbro.domain.transactions import Transaction
from finbro.services.classification import ClassificationService
from finbro.services.llm_jobs import model_name
from finbro.services.receivables import ReceivablesService
from finbro.services.uow import UnitOfWork
from finbro.web.deps import get_uow
from finbro.web.forms import decision_from_form, form_context, is_htmx
from finbro.web.templating import templates

router = APIRouter()


def render_row(request: Request, uow: UnitOfWork, tx: Transaction, error: str | None = None) -> HTMLResponse:
    return templates.TemplateResponse(
        request, "_inbox_row.html", {"tx": tx, "error": error, **form_context(uow), **inbox_extras(uow, [tx], request)}
    )


def inbox_extras(uow: UnitOfWork, items: list[Transaction], request: Request | None = None) -> dict[str, Any]:
    """Stan kolejki LLM i podpowiedzi spłat od dłużników dla pozycji skrzynki."""
    receivables = ReceivablesService(uow)
    balances = receivables.balances()
    suggestions = {}
    if balances:
        for tx in items:
            match = receivables.suggest_repayment(tx, balances)
            if match is not None:
                suggestions[tx.id] = match
    llm_enabled = request is not None and model_name(request.app.state.settings, uow) is not None
    return {
        "queued_ids": uow.llm_jobs.queued_transaction_ids(),
        "repayment_suggestions": suggestions,
        "llm_enabled": llm_enabled,
    }


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
            **inbox_extras(uow, items, request),
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


@router.get("/inbox/{transaction_id}/row", response_class=HTMLResponse)
def row(request: Request, transaction_id: int, uow: UnitOfWork = Depends(get_uow)) -> HTMLResponse:
    """Aktualny wiersz skrzynki (odświeżanie, gdy model językowy liczy propozycję)."""
    tx = uow.transactions.get(transaction_id)
    if tx.classification.confirmed:
        return HTMLResponse("")
    return render_row(request, uow, tx)


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

"""Widok należności: kto i ile jest winien, historia i darowanie."""

from __future__ import annotations

from datetime import date
from urllib.parse import quote

from fastapi import APIRouter, Depends, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from finbro.domain.classification import ClassificationError
from finbro.domain.money import Money
from finbro.domain.receivables import event_from_transaction
from finbro.services.receivables import ReceivablesService
from finbro.services.uow import UnitOfWork
from finbro.web.deps import get_uow
from finbro.web.routes.wallet import parse_date
from finbro.web.templating import templates

router = APIRouter()


def _render(request: Request, uow: UnitOfWork, debtor_id: int | None = None, status_code: int = 200, **extra: object) -> HTMLResponse:
    service = ReceivablesService(uow)
    balances = service.balances()
    context: dict[str, object] = {
        "balances": balances,
        "total": service.total(balances),
        "categories": [c for c in uow.reference.categories() if c.active and not c.is_system],
        "today": date.today(),
        "message": request.query_params.get("msg"),
        **extra,
    }
    if debtor_id is not None:
        selected = service.of(debtor_id)
        context["selected"] = selected
        context["history"] = [
            (tx, event_from_transaction(tx, debtor_id)) for tx in service.history(debtor_id)
        ]
    return templates.TemplateResponse(request, "receivables.html", context, status_code=status_code)


@router.get("/receivables", response_class=HTMLResponse)
def receivables(request: Request, uow: UnitOfWork = Depends(get_uow)) -> HTMLResponse:
    return _render(request, uow)


@router.get("/receivables/{debtor_id}", response_class=HTMLResponse)
def debtor(request: Request, debtor_id: int, uow: UnitOfWork = Depends(get_uow)) -> HTMLResponse:
    return _render(request, uow, debtor_id)


def _forgive(request: Request, debtor_id: int, uow: UnitOfWork, form: dict[str, str]) -> Response:
    try:
        amount = Money.parse(form["amount"])
        category = form.get("category_id")
        if not category:
            raise ClassificationError("Wybierz kategorię wydatku dla darowanej kwoty.")
        ReceivablesService(uow).forgive(debtor_id, amount, parse_date(form.get("date"), date.today()), int(category))
    except (ClassificationError, ValueError, KeyError) as exc:
        return _render(request, uow, debtor_id, status_code=400, error=str(exc))
    return RedirectResponse(f"/receivables/{debtor_id}?msg={quote('Darowano ' + amount.format())}", status_code=303)


@router.post("/receivables/{debtor_id}/forgive")
async def forgive(request: Request, debtor_id: int, uow: UnitOfWork = Depends(get_uow)) -> Response:
    form = {k: str(v) for k, v in (await request.form()).items()}
    return await run_in_threadpool(_forgive, request, debtor_id, uow, form)

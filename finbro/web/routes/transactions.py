"""Lista transakcji z filtrem i zmianą klasyfikacji dowolnej transakcji."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from finbro.domain.classification import ClassificationError
from finbro.domain.enums import TxType
from finbro.domain.periods import Month
from finbro.domain.transactions import Transaction, TransactionFilter
from finbro.services.classification import ClassificationService
from finbro.services.uow import UnitOfWork
from finbro.web.deps import get_uow
from finbro.web.forms import decision_from_form, form_context, is_htmx
from finbro.web.templating import templates

router = APIRouter()


def _date(value: str | None, default: date) -> date:
    try:
        return date.fromisoformat(value) if value else default
    except ValueError:
        return default


def filter_from_query(query: Mapping[str, str], today: date | None = None) -> TransactionFilter:
    month = Month.of(today or date.today())
    tx_type = query.get("type") or None
    category = query.get("category_id") or None
    return TransactionFilter(
        date_from=_date(query.get("from"), month.start),
        date_to=_date(query.get("to"), month.end),
        type=TxType(tx_type) if tx_type in TxType.__members__ else None,
        category_id=int(category) if category and category.isdigit() else None,
        text=(query.get("q") or "").strip() or None,
        only_unconfirmed=query.get("unconfirmed") == "1",
    )


def render_row(request: Request, uow: UnitOfWork, tx: Transaction, error: str | None = None) -> HTMLResponse:
    return templates.TemplateResponse(request, "_tx_row.html", {"tx": tx, "error": error, **form_context(uow)})


@router.get("/transactions", response_class=HTMLResponse)
def transactions(request: Request, uow: UnitOfWork = Depends(get_uow)) -> HTMLResponse:
    f = filter_from_query(request.query_params)
    items = uow.transactions.search(f)
    return templates.TemplateResponse(
        request,
        "transactions.html",
        {"items": items, "filter": f, "tx_types": list(TxType), "query": request.url.query, **form_context(uow)},
    )


def _classify(request: Request, transaction_id: int, uow: UnitOfWork, form: Mapping[str, Any]) -> Response:
    error = None
    try:
        ClassificationService(uow).decide(transaction_id, decision_from_form(form))
    except (ClassificationError, ValueError) as exc:
        error = str(exc)
    if is_htmx(request):
        return render_row(request, uow, uow.transactions.get(transaction_id), error=error)
    if error:
        response = render_row(request, uow, uow.transactions.get(transaction_id), error=error)
        response.status_code = 400
        return response
    back = form.get("back") or ""
    return RedirectResponse("/transactions" + (f"?{back}" if back else ""), status_code=303)


@router.post("/transactions/{transaction_id}/classify")
async def classify(request: Request, transaction_id: int, uow: UnitOfWork = Depends(get_uow)) -> Response:
    form = dict(await request.form())
    return await run_in_threadpool(_classify, request, transaction_id, uow, form)

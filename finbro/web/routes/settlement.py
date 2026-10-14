"""Widok Rozliczenie: lista przelewów dla nierozliczonych dochodów, rozliczenie i historia."""

from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from finbro.domain.envelopes import TRANSFER_ENVELOPES
from finbro.domain.money import Money
from finbro.services.settlements import SettlementError, SettlementService
from finbro.web.deps import DbSession
from finbro.web.templating import templates

router = APIRouter()


def page(request: Request, session: DbSession, status_code: int = 200, **extra: Any) -> HTMLResponse:
    service = SettlementService(session)
    context = {
        "pending": service.pending(date.today()),
        "history": service.history(),
        "envelopes": TRANSFER_ENVELOPES,
        "error": None,
        "done": request.query_params.get("done") == "1",
        **extra,
    }
    return templates.TemplateResponse(request, "settlement.html", context, status_code=status_code)


@router.get("/settlement", response_class=HTMLResponse)
def settlement_page(request: Request, session: DbSession) -> HTMLResponse:
    return page(request, session)


@router.post("/settlement", response_model=None)
async def settle(request: Request, session: DbSession) -> Response:
    form = await request.form()
    try:
        income_ids = [int(v) for v in form.getlist("income_id")]
        expected = {e: Money(int(form[f"expected_{e.value}"])) for e in TRANSFER_ENVELOPES if f"expected_{e.value}" in form}
    except (TypeError, ValueError):
        return page(request, session, 400, error="Niepoprawny formularz. Odśwież widok.")
    try:
        SettlementService(session).settle(income_ids, expected, date.today())
    except SettlementError as exc:
        session.rollback()
        return page(request, session, 400, error=str(exc))
    return RedirectResponse("/settlement?done=1", status_code=303)


@router.post("/settlement/{settlement_id}/undo", response_model=None)
def undo(request: Request, settlement_id: int, session: DbSession) -> Response:
    try:
        SettlementService(session).undo(settlement_id)
    except SettlementError as exc:
        session.rollback()
        return page(request, session, 400, error=str(exc))
    return RedirectResponse("/settlement", status_code=303)

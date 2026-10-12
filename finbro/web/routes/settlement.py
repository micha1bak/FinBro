"""Widok rozliczenia tygodniowego: wyliczenie, ostrzeżenia, zamknięcie i lista przelewów."""

from __future__ import annotations

from datetime import date
from urllib.parse import quote

from fastapi import APIRouter, Depends, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from finbro.domain.periods import IsoWeek
from finbro.domain.settlement import LineState, transfer_title
from finbro.services.settlement import SettlementError, SettlementService
from finbro.services.uow import UnitOfWork
from finbro.web.deps import get_uow
from finbro.web.templating import templates

router = APIRouter()


def default_week(today: date | None = None) -> IsoWeek:
    """W poniedziałek (i w każdy dzień tygodnia) proponujemy poprzedni, zakończony tydzień."""
    return IsoWeek.of(today or date.today()).prev()


def parse_week(value: str | None) -> IsoWeek:
    try:
        return IsoWeek.parse(value) if value else default_week()
    except ValueError:
        return default_week()


def render(request: Request, uow: UnitOfWork, week: IsoWeek, status_code: int = 200, **extra: object) -> HTMLResponse:
    service = SettlementService(uow)
    result = service.compute(week)
    today = date.today()
    start_date = uow.reference.config().start_date
    transfers = []
    if result.is_closed:
        for env in result.envelopes:
            if env.is_life:
                continue
            line = result.line(env)
            transfers.append(
                {
                    "envelope": env,
                    "line": line,
                    "amount": line.to_transfer,
                    "title": transfer_title(week, env.name),
                    "paid": result.paid(line),
                    "state": result.state(line),
                }
            )
    payments = uow.settlements.payments_by_line()
    paid_txs = {tx.id: tx for tx in uow.transactions.get_many([i for ids in payments.values() for i in ids])}
    context = {
        "week": week,
        "result": result,
        "transfers": [t for t in transfers if t["state"] is not LineState.NO_TRANSFER],
        "skipped": [t for t in transfers if t["state"] is LineState.NO_TRANSFER],
        "payments": {line_id: [paid_txs[i] for i in ids if i in paid_txs] for line_id, ids in payments.items()},
        "warnings": [] if result.is_closed else service.warnings(week),
        "week_ended": today > week.end,
        "before_start": start_date is not None and week.end < start_date,
        "start_date": start_date,
        "message": request.query_params.get("msg"),
        "history": [s for s in uow.settlements.list_all() if s.status.value != "OPEN"][-8:],
        **extra,
    }
    return templates.TemplateResponse(request, "settlement.html", context, status_code=status_code)


@router.get("/settlement", response_class=HTMLResponse)
def settlement(request: Request, uow: UnitOfWork = Depends(get_uow)) -> HTMLResponse:
    return render(request, uow, parse_week(request.query_params.get("week")))


def _close(request: Request, uow: UnitOfWork, form: dict[str, str]) -> Response:
    week = parse_week(form.get("week"))
    service = SettlementService(uow)
    warnings = service.warnings(week)
    if warnings and form.get("confirm") != "1":
        return render(request, uow, week, status_code=400, error="Potwierdź zamknięcie mimo ostrzeżeń.")
    try:
        service.close(week)
    except SettlementError as exc:
        return render(request, uow, week, status_code=400, error=str(exc))
    return RedirectResponse(f"/settlement?week={week.label}&msg={quote('Rozliczenie zamknięte')}", status_code=303)


@router.post("/settlement/close")
async def close(request: Request, uow: UnitOfWork = Depends(get_uow)) -> Response:
    form = {k: str(v) for k, v in (await request.form()).items()}
    return await run_in_threadpool(_close, request, uow, form)

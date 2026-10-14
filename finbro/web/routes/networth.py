"""Widok Majątek: salda PKO, Gotówki, XTB i Obligacji, suma, wpis salda faktycznego i wykres."""

from __future__ import annotations

import json
from datetime import date
from typing import Any

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from finbro.domain.networth import Account
from finbro.services.networth import NetWorthError, NetWorthService
from finbro.web.deps import DbSession
from finbro.web.forms import FormError, parse_date, parse_money
from finbro.web.templating import templates

router = APIRouter()


def page(request: Request, session: DbSession, status_code: int = 200, **extra: Any) -> HTMLResponse:
    overview = NetWorthService(session).overview(date.today())
    recorded = None
    account, day = request.query_params.get("account"), request.query_params.get("date")
    if account and day:
        recorded = next((v for v in overview.entries if v.entry.account.value == account and v.entry.date.isoformat() == day), None)
    chart = {
        "labels": [s.day.isoformat() for s in overview.timeline],
        "totals": [s.total.grosze / 100 for s in overview.timeline],
    }
    context = {
        "overview": overview,
        "accounts": list(Account),
        "recorded": recorded,
        "chart_json": json.dumps(chart),
        "form": {"account": "XTB", "date": date.today().isoformat(), "amount": ""},
        "error": None,
        **extra,
    }
    return templates.TemplateResponse(request, "networth.html", context, status_code=status_code)


@router.get("/networth", response_class=HTMLResponse)
def networth_page(request: Request, session: DbSession) -> HTMLResponse:
    return page(request, session)


@router.post("/networth/balance", response_model=None)
def record_balance(
    request: Request,
    session: DbSession,
    account: str = Form(""),
    date_: str = Form("", alias="date"),
    amount: str = Form(""),
) -> Response:
    try:
        if account not in Account.__members__:
            raise NetWorthError("Saldo można wpisać tylko dla PKO, Gotówki, XTB i Obligacji.")
        view = NetWorthService(session).record(Account(account), parse_date(date_), parse_money(amount))
    except (FormError, NetWorthError) as exc:
        session.rollback()
        return page(request, session, 400, error=str(exc), form={"account": account, "date": date_, "amount": amount})
    return RedirectResponse(f"/networth?account={view.entry.account.value}&date={view.entry.date.isoformat()}", status_code=303)

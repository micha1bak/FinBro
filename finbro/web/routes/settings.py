"""Widok Ustawienia: rachunki docelowe kopert i plan podziału."""

from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from finbro.domain.allocation import PlanError, format_percent, parse_percent
from finbro.domain.envelopes import TRANSFER_ENVELOPES, Envelope
from finbro.services.incomes import IncomeError, IncomeService
from finbro.services.settings import SettingsError, SettingsService
from finbro.web.deps import DbSession
from finbro.web.forms import FormError, parse_date
from finbro.web.templating import templates

router = APIRouter()


def page(request: Request, session: DbSession, status_code: int = 200, **extra: Any) -> HTMLResponse:
    plans = IncomeService(session).plans()
    accounts = SettingsService(session).accounts()
    context = {
        "plans": plans,
        "envelopes": list(Envelope),
        "transfer_envelopes": TRANSFER_ENVELOPES,
        "format_percent": format_percent,
        "accounts_form": {e.value: accounts.get(e, "") for e in TRANSFER_ENVELOPES},
        "plan_form": {
            "effective_from": date.today().isoformat(),
            **{e.value: format_percent(plans[0].shares[e]).rstrip("%") for e in Envelope},
        },
        "error": None,
        "saved": request.query_params.get("saved"),
        **extra,
    }
    return templates.TemplateResponse(request, "settings.html", context, status_code=status_code)


@router.get("/settings", response_class=HTMLResponse)
def settings_page(request: Request, session: DbSession) -> HTMLResponse:
    return page(request, session)


@router.post("/settings/accounts", response_model=None)
async def save_accounts(request: Request, session: DbSession) -> Response:
    form = await request.form()
    values = {e: str(form.get(e.value, "")) for e in TRANSFER_ENVELOPES}
    try:
        SettingsService(session).save_accounts(values)
    except SettingsError as exc:
        session.rollback()
        return page(request, session, 400, error=str(exc), accounts_form={e.value: v for e, v in values.items()})
    return RedirectResponse("/settings?saved=accounts", status_code=303)


@router.post("/settings/plan", response_model=None)
async def add_plan(request: Request, session: DbSession) -> Response:
    form = await request.form()
    raw = {key: str(form.get(key, "")) for key in ["effective_from", *(e.value for e in Envelope)]}
    try:
        shares = {e: parse_percent(raw[e.value]) for e in Envelope}
        IncomeService(session).add_plan(parse_date(raw["effective_from"], "Obowiązuje od"), shares)
    except (FormError, PlanError, IncomeError) as exc:
        session.rollback()
        return page(request, session, 400, error=str(exc), plan_form=raw)
    return RedirectResponse("/settings?saved=plan", status_code=303)

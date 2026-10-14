"""Widok Dochody: wpisywanie dochodów i lista miesiąca z podziałem na koperty."""

from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from finbro.domain.envelopes import Envelope
from finbro.services.incomes import IncomeError, IncomeService
from finbro.web.deps import DbSession
from finbro.web.forms import FormError, month_label, parse_date, parse_money, parse_month, shift_month
from finbro.web.templating import templates

router = APIRouter()


def month_page(request: Request, session: DbSession, year: int, month: int, **extra: Any) -> dict[str, Any]:
    return {
        "summary": IncomeService(session).month(year, month),
        "envelopes": list(Envelope),
        "month_label": month_label(year, month),
        "month_value": f"{year}-{month:02d}",
        "prev_month": shift_month(year, month, -1),
        "next_month": shift_month(year, month, 1),
        "form": {"date": date.today().isoformat(), "source": "", "amount": ""},
        "error": None,
        **extra,
    }


@router.get("/", response_class=HTMLResponse)
def incomes_page(request: Request, session: DbSession) -> HTMLResponse:
    year, month = parse_month(request.query_params.get("month"), date.today())
    return templates.TemplateResponse(request, "incomes.html", month_page(request, session, year, month))


@router.post("/incomes", response_model=None)
def add_income(
    request: Request,
    session: DbSession,
    date_: str = Form("", alias="date"),
    source: str = Form(""),
    amount: str = Form(""),
) -> Response:
    try:
        day = parse_date(date_)
        view = IncomeService(session).add(day, source, parse_money(amount))
    except (FormError, IncomeError) as exc:
        session.rollback()
        today = date.today()
        context = month_page(request, session, today.year, today.month,
                             form={"date": date_, "source": source, "amount": amount}, error=str(exc))
        return templates.TemplateResponse(request, "incomes.html", context, status_code=400)
    return RedirectResponse(f"/?month={view.date:%Y-%m}", status_code=303)


@router.get("/incomes/{income_id}/edit", response_class=HTMLResponse)
def edit_income_page(request: Request, income_id: int, session: DbSession) -> HTMLResponse:
    view = IncomeService(session).get(income_id)
    form = {"date": view.date.isoformat(), "source": view.source, "amount": view.amount.format(currency=False)}
    return templates.TemplateResponse(request, "income_edit.html", {"income": view, "form": form, "error": None})


@router.post("/incomes/{income_id}", response_model=None)
def update_income(
    request: Request,
    income_id: int,
    session: DbSession,
    date_: str = Form("", alias="date"),
    source: str = Form(""),
    amount: str = Form(""),
) -> Response:
    service = IncomeService(session)
    try:
        view = service.update(income_id, parse_date(date_), source, parse_money(amount))
    except (FormError, IncomeError) as exc:
        session.rollback()
        context = {"income": service.get(income_id), "form": {"date": date_, "source": source, "amount": amount},
                   "error": str(exc)}
        return templates.TemplateResponse(request, "income_edit.html", context, status_code=400)
    return RedirectResponse(f"/?month={view.date:%Y-%m}", status_code=303)


@router.post("/incomes/{income_id}/delete", response_model=None)
def delete_income(request: Request, income_id: int, session: DbSession) -> Response:
    service = IncomeService(session)
    view = service.get(income_id)
    try:
        service.delete(income_id)
    except IncomeError as exc:
        session.rollback()
        context = month_page(request, session, view.date.year, view.date.month, error=str(exc))
        return templates.TemplateResponse(request, "incomes.html", context, status_code=400)
    return RedirectResponse(f"/?month={view.date:%Y-%m}", status_code=303)

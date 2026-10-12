"""Widok Portfela: stan oczekiwany, stan początkowy i ręczne wpisy gotówkowe."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import date
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, Depends, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from finbro.domain.classification import ClassificationError
from finbro.domain.money import Money
from finbro.domain.periods import IsoWeek
from finbro.services.uow import UnitOfWork
from finbro.services.wallet import WalletError, WalletService
from finbro.web.deps import get_uow
from finbro.web.templating import templates

router = APIRouter()

FORM_ERRORS = (WalletError, ClassificationError, ValueError, KeyError)


def parse_date(value: str | None, default: date) -> date:
    try:
        return date.fromisoformat(value) if value else default
    except ValueError:
        return default


def wallet_context(uow: UnitOfWork, at: date) -> dict[str, Any]:
    service = WalletService(uow)
    config = uow.reference.config()
    categories = [c for c in uow.reference.categories() if c.active and not c.is_system]
    return {
        "state": service.state(at),
        "today": date.today(),
        "start_date": config.start_date,
        "inventory_default": IsoWeek.of(date.today()).prev().end,
        "categories": categories,
        "categories_by_id": {c.id: c for c in uow.reference.categories()},
        "debtors": uow.reference.debtors(),
        "inventories": uow.inventories.latest(),
    }


def render(request: Request, uow: UnitOfWork, at: date, status_code: int = 200, **extra: Any) -> HTMLResponse:
    return templates.TemplateResponse(request, "wallet.html", {**wallet_context(uow, at), **extra}, status_code=status_code)


@router.get("/wallet", response_class=HTMLResponse)
def wallet(request: Request, uow: UnitOfWork = Depends(get_uow)) -> HTMLResponse:
    at = parse_date(request.query_params.get("at"), date.today())
    return render(request, uow, at, message=request.query_params.get("msg"))


def handle(
    request: Request, uow: UnitOfWork, form: Mapping[str, Any], action: Callable[[], str]
) -> Response:
    try:
        message = action()
    except FORM_ERRORS as exc:
        return render(request, uow, date.today(), status_code=400, error=str(exc))
    return RedirectResponse(f"/wallet?msg={quote(message)}", status_code=303)


def form_route(path: str, action: Callable[[WalletService, Mapping[str, Any]], str]) -> None:
    async def endpoint(request: Request, uow: UnitOfWork = Depends(get_uow)) -> Response:
        form = dict(await request.form())
        return await run_in_threadpool(handle, request, uow, form, lambda: action(WalletService(uow), form))

    router.add_api_route(path, endpoint, methods=["POST"], name=path)


def _opening(service: WalletService, form: Mapping[str, Any]) -> str:
    amount = Money.parse(form["amount"])
    service.set_opening_balance(amount, parse_date(form.get("date"), date.today()))
    return f"Ustawiono stan początkowy {amount.format()}"


def _income(service: WalletService, form: Mapping[str, Any]) -> str:
    amount = Money.parse(form["amount"])
    service.add_cash_income(parse_date(form.get("date"), date.today()), amount, form.get("note"))
    return f"Zapisano dochód gotówkowy {amount.format()}"


def _expense(service: WalletService, form: Mapping[str, Any]) -> str:
    amount = Money.parse(form["amount"])
    category = form.get("category_id")
    service.add_cash_expense(
        parse_date(form.get("date"), date.today()), amount, int(category) if category else None, form.get("note")
    )
    return f"Zapisano wydatek gotówkowy {amount.format()}"


def _inventory(service: WalletService, form: Mapping[str, Any]) -> str:
    result = service.inventory(parse_date(form.get("date"), date.today()), Money.parse(form["amount"]))
    difference = result.inventory.difference
    if difference.is_negative:
        return f"Niedobór {abs(difference).format()} zapisany jako wydatek gotówkowy bez kategorii"
    if difference.is_positive:
        return f"Nadwyżka {difference.format()} czeka w skrzynce na decyzję"
    return "Stan zgodny z oczekiwanym"


form_route("/wallet/opening", _opening)
form_route("/wallet/inventory", _inventory)
form_route("/wallet/income", _income)
form_route("/wallet/expense", _expense)

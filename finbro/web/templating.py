"""Szablony Jinja2 i filtry formatujące."""

from __future__ import annotations

from pathlib import Path

from fastapi.templating import Jinja2Templates

from finbro.domain.money import Money

WEB_DIR = Path(__file__).parent
templates = Jinja2Templates(directory=WEB_DIR / "templates")


def money_filter(value: Money | int | None, plus: bool = False, currency: bool = True) -> str:
    if value is None:
        return ""
    money = value if isinstance(value, Money) else Money(value)
    return money.format(currency=currency, plus=plus)


templates.env.filters["money"] = money_filter

"""Szablony Jinja2 i filtry formatujące."""

from __future__ import annotations

import hashlib
from pathlib import Path

from fastapi.templating import Jinja2Templates

from finbro.domain.money import Money

WEB_DIR = Path(__file__).parent
templates = Jinja2Templates(directory=WEB_DIR / "templates")


def content_version(*paths: Path) -> str:
    """Skrót treści plików do adresu: po zmianie pliku przeglądarka nie użyje starej kopii z pamięci."""
    digest = hashlib.sha256()
    for path in paths:
        digest.update(path.read_bytes())
    return digest.hexdigest()[:10]


def money_filter(value: Money | int | None, plus: bool = False, currency: bool = True) -> str:
    if value is None:
        return ""
    money = value if isinstance(value, Money) else Money(value)
    return money.format(currency=currency, plus=plus)


def plural_filter(n: int, one: str, few: str, many: str) -> str:
    """Polska odmiana po liczbie: 1 dochód, 2–4 dochody, 5 dochodów (też 12–14 i 0)."""
    if n == 1:
        return f"{n} {one}"
    return f"{n} {few if n % 10 in (2, 3, 4) and n % 100 not in (12, 13, 14) else many}"


templates.env.filters["money"] = money_filter
templates.env.filters["plural"] = plural_filter
templates.env.globals["asset_version"] = content_version(WEB_DIR / "static" / "finbro.css", WEB_DIR / "static" / "theme.js")

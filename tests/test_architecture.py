"""Granice warstw z D1: domena to czyste funkcje, a widoki nie wykonują zapytań do bazy."""

import ast
from pathlib import Path

import finbro

PACKAGE_ROOT = Path(finbro.__file__).parent

# Jedyny moduł webowy, który zna SQLAlchemy: dostarcza sesję do serwisów.
WEB_ALLOWED = {PACKAGE_ROOT / "web" / "deps.py"}


def imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module)
    return names


def offenders(package: str, forbidden: tuple[str, ...], allowed: set[Path] = frozenset()) -> dict[str, list[str]]:
    result = {}
    for path in sorted((PACKAGE_ROOT / package).rglob("*.py")):
        if path in allowed:
            continue
        bad = sorted(m for m in imported_modules(path) if m.startswith(forbidden))
        if bad:
            result[str(path.relative_to(PACKAGE_ROOT))] = bad
    return result


def test_domain_is_pure():
    assert offenders("domain", ("sqlalchemy", "fastapi", "starlette", "finbro.db", "finbro.services", "finbro.web")) == {}


def test_web_does_not_query_database():
    assert offenders("web", ("sqlalchemy", "finbro.db.models"), WEB_ALLOWED) == {}


def test_architecture_check_sees_modules():
    # Zabezpieczenie przed testem, który niczego nie sprawdza.
    assert (PACKAGE_ROOT / "domain" / "money.py").exists()
    assert (PACKAGE_ROOT / "web" / "app.py").exists()

"""Granice warstw z D2: domena i warstwa webowa nie zależą od SQLAlchemy."""

import ast
from pathlib import Path

import pytest

import finbro

PACKAGE_ROOT = Path(finbro.__file__).parent

# SQLAdmin z definicji działa bezpośrednio na modelach, więc jego konfiguracja jest wyjątkiem.
ALLOWED = {PACKAGE_ROOT / "web" / "admin.py"}


def imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module)
    return names


def modules_in(package: str) -> list[Path]:
    return sorted(p for p in (PACKAGE_ROOT / package).rglob("*.py") if p not in ALLOWED)


@pytest.mark.parametrize("package", ["domain", "web", "importers"])
def test_layer_does_not_import_sqlalchemy(package):
    offenders = {
        str(path.relative_to(PACKAGE_ROOT)): sorted(m for m in imported_modules(path) if m.split(".")[0] == "sqlalchemy")
        for path in modules_in(package)
    }
    assert {k: v for k, v in offenders.items() if v} == {}


@pytest.mark.parametrize("package", ["domain", "importers"])
def test_pure_layers_do_not_import_outer_layers(package):
    forbidden = ("finbro.db", "finbro.services", "finbro.web", "finbro.classification", "finbro.llm")
    offenders = {
        str(path.relative_to(PACKAGE_ROOT)): sorted(m for m in imported_modules(path) if m.startswith(forbidden))
        for path in modules_in(package)
    }
    assert {k: v for k, v in offenders.items() if v} == {}


def test_architecture_check_sees_modules():
    # Zabezpieczenie przed testem, który niczego nie sprawdza.
    assert len(modules_in("domain")) >= 5
    assert any(p.name == "app.py" for p in modules_in("web"))

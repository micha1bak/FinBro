"""Konfiguracja aplikacji ze zmiennych środowiskowych."""

from __future__ import annotations

import os
from collections.abc import Mapping, MutableMapping
from dataclasses import dataclass
from pathlib import Path

class ConfigError(RuntimeError):
    """Brak lub błędna wartość wymaganej zmiennej środowiskowej."""


@dataclass(frozen=True)
class Settings:
    database_url: str

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> Settings:
        env = os.environ if environ is None else environ
        database_url = env.get("DATABASE_URL", "").strip()
        if not database_url:
            raise ConfigError(
                "Brak zmiennej DATABASE_URL. Ustaw ją w pliku .env "
                "(wzór w .env.example) albo w środowisku procesu."
            )
        return cls(database_url=database_url)


def load_dotenv(path: Path | str = ".env", environ: MutableMapping[str, str] | None = None) -> None:
    """Wczytuje proste pary KLUCZ=wartość z pliku .env, nie nadpisując istniejących zmiennych.

    Służy wyłącznie pracy deweloperskiej w .venv. W kontenerze pliku .env nie ma,
    a zmienne ustawia docker compose.
    """
    env = os.environ if environ is None else environ
    file = Path(path)
    if not file.is_file():
        return
    for raw in file.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        env.setdefault(key, value)

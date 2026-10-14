"""Fabryka aplikacji FastAPI.

Uruchomienie: ``uvicorn finbro.web.app:create_app --factory``.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from finbro.config import Settings, load_dotenv
from finbro.db.session import make_engine, make_session_factory, ping
from finbro.web.routes import incomes
from finbro.web.templating import WEB_DIR


def create_app(settings: Settings | None = None, session_factory: Callable[..., Any] | None = None) -> FastAPI:
    """Tworzy aplikację. ``session_factory`` pozwala testom podać sesje w transakcji testu."""
    if settings is None:
        load_dotenv()
        settings = Settings.from_env()

    engine = make_engine(settings.database_url)
    app = FastAPI(title="FinBro", docs_url=None, redoc_url=None)
    app.state.settings = settings
    app.state.engine = engine
    app.state.session_factory = session_factory or make_session_factory(engine)
    app.mount("/static", StaticFiles(directory=WEB_DIR / "static"), name="static")

    app.include_router(incomes.router)

    @app.get("/health")
    def health() -> JSONResponse:
        if ping(engine):
            return JSONResponse({"status": "ok", "database": "ok"})
        return JSONResponse({"status": "error", "database": "unavailable"}, status_code=503)

    return app

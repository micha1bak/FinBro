"""Fabryka aplikacji FastAPI.

Uruchomienie: ``uvicorn finbro.web.app:create_app --factory``.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import FastAPI, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from finbro.config import Settings, load_dotenv
from finbro.db.session import make_engine, make_session_factory, ping
from finbro.web.admin import setup_admin
from finbro.web.routes import imports, inbox
from finbro.web.templating import WEB_DIR, templates


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
    setup_admin(app, engine, app.state.session_factory)
    app.include_router(imports.router)
    app.include_router(inbox.router)

    @app.middleware("http")
    async def limit_upload_size(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        if request.method == "POST" and request.url.path == "/import":
            length = request.headers.get("content-length")
            if length is None or not length.isdigit():
                return PlainTextResponse("Brak nagłówka Content-Length.", status_code=411)
            if int(length) > imports.MAX_UPLOAD_BYTES:
                return PlainTextResponse("Plik jest za duży.", status_code=413)
        return await call_next(request)

    @app.get("/", response_class=HTMLResponse)
    def index(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(request, "index.html")

    @app.get("/health")
    def health() -> JSONResponse:
        if ping(engine):
            return JSONResponse({"status": "ok", "database": "ok"})
        return JSONResponse({"status": "error", "database": "unavailable"}, status_code=503)

    return app

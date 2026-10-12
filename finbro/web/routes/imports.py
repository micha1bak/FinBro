"""Widok importu wyciągów XML z iPKO."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request, UploadFile
from fastapi.responses import HTMLResponse
from starlette.formparsers import MultiPartParser

from finbro.services.importing import ImportRejected, ImportService
from finbro.services.uow import UnitOfWork
from finbro.web.deps import get_uow
from finbro.web.templating import templates

MAX_UPLOAD_BYTES = 10 * 1024 * 1024

# Wyciągi nie mogą trafiać na dysk (D12). Starlette domyślnie przenosi pliki powyżej 1 MB
# do pliku tymczasowego, więc podnosimy próg do limitu przesyłanego pliku; większe żądania
# odrzuca middleware w app.py na podstawie Content-Length, zanim formularz zostanie odczytany.
MultiPartParser.spool_max_size = MAX_UPLOAD_BYTES

router = APIRouter()


def _page(request: Request, uow: UnitOfWork, status_code: int = 200, **context: object) -> HTMLResponse:
    service = ImportService(uow)
    batches = list(reversed(uow.imports.batches()))[:10]
    return templates.TemplateResponse(
        request,
        "import.html",
        {"gaps": service.coverage_gaps(), "batches": batches, **context},
        status_code=status_code,
    )


@router.get("/import", response_class=HTMLResponse)
def import_form(request: Request, uow: UnitOfWork = Depends(get_uow)) -> HTMLResponse:
    return _page(request, uow)


@router.post("/import", response_class=HTMLResponse)
def import_upload(request: Request, file: UploadFile, uow: UnitOfWork = Depends(get_uow)) -> HTMLResponse:
    content = file.file.read()
    try:
        result = ImportService(uow).import_pko_xml(content, file.filename)
    except ImportRejected as exc:
        return _page(request, uow, status_code=400, error=str(exc))
    return _page(request, uow, result=result)

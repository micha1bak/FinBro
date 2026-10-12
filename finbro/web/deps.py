"""Zależności FastAPI: jednostka pracy na czas żądania."""

from __future__ import annotations

from collections.abc import Iterator

from fastapi import Request

from finbro.services.uow import UnitOfWork


def get_uow(request: Request) -> Iterator[UnitOfWork]:
    uow = UnitOfWork(request.app.state.session_factory())
    try:
        yield uow
    except Exception:
        uow.rollback()
        raise
    finally:
        uow.close()

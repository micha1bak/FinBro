"""Sesja bazy dla widoków: jedna na żądanie, zamykana po odpowiedzi."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session


def get_session(request: Request) -> Iterator[Session]:
    session = request.app.state.session_factory()
    try:
        yield session
    finally:
        session.close()


# Typ parametru widoku: widoki nie importują SQLAlchemy (test architektury).
DbSession = Annotated[Session, Depends(get_session)]

from datetime import date

import pytest

from finbro.services.uow import UnitOfWork
from tests.helpers import MAIN_ACCOUNT


@pytest.fixture
def uow(db_session):
    """Jednostka pracy ze skonfigurowanym kontem głównym i datą startu 2026-10-05.

    Korzysta z tej samej sesji co ``db_session``, żeby savepointy w transakcji testu
    nie przeplatały się między sesjami.
    """
    unit = UnitOfWork(db_session)
    unit.reference.update_config(main_account_number=MAIN_ACCOUNT, start_date=date(2026, 10, 5))
    unit.commit()
    return unit

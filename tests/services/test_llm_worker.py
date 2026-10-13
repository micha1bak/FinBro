from datetime import date

from sqlalchemy import select, update

from finbro.db import models
from finbro.domain.enums import LlmJobStatus, ProposalSource, TxType
from finbro.domain.money import Money
from finbro.domain.transactions import Classification
from finbro.llm.classifier import ClassifierUnavailable, LlmClassifier
from finbro.services.importing import ImportService
from finbro.services.llm_jobs import MAX_ATTEMPTS, LlmJobService
from finbro.services.uow import UnitOfWork
from finbro.web.worker import LlmWorker
from tests.helpers import WEEK41, fixture_bytes


class FakeClassifier:
    """Atrapa modelu: Biedronka to Spożywcze, kancelaria to DOCHÓD, reszta bez propozycji."""

    def __init__(self):
        self.calls = []

    def classify(self, view, context):
        self.calls.append(view)
        if view.counterparty == "JMP S.A. BIEDRONKA 2422":
            return_type, category = TxType.WYDATEK, context.categories["Spożywcze"]
        elif view.counterparty and view.counterparty.startswith("KANCELARIA"):
            return_type, category = TxType.DOCHOD, None
        else:
            return None
        return Classification(type=return_type, category_id=category, source=ProposalSource.LLM, reason="atrapa")


class DownClassifier:
    def classify(self, view, context):
        raise ClassifierUnavailable("serwer modelu nie działa")


def by(uow, **criteria):
    txs = uow.transactions.list_between(date(2026, 1, 1), date(2026, 12, 31))
    [match] = [t for t in txs if all(getattr(t.data, k) == v for k, v in criteria.items())]
    return match


def test_import_finishes_immediately_and_proposals_appear_after_queue(uow, session_factory):
    ImportService(uow).import_pko_xml(fixture_bytes(WEEK41))
    queued = uow.llm_jobs.queued_transaction_ids()
    assert len(queued) == 11
    assert by(uow, merchant="JMP S.A. BIEDRONKA 2422").classification.type is None
    uow.commit()

    fake = FakeClassifier()
    service = LlmJobService(session_factory, lambda _uow: fake)
    assert service.process_all() == 11
    assert len(fake.calls) == 11
    # Do modelu nie trafiają numery rachunków ani salda.
    assert all("1140 2004" not in (v.title or "") + (v.counterparty or "") for v in fake.calls)

    uow.session.expire_all()
    groceries = by(uow, merchant="JMP S.A. BIEDRONKA 2422").classification
    assert (groceries.type, groceries.source, groceries.confirmed) == (TxType.WYDATEK, ProposalSource.LLM, True)
    income = by(uow, amount=Money.parse("4250.00")).classification
    assert (income.type, income.source, income.confirmed) == (TxType.DOCHOD, ProposalSource.LLM, False)
    netflix = by(uow, merchant="NETFLIX.COM").classification
    assert (netflix.type, netflix.confirmed) == (None, False)
    assert uow.llm_jobs.queued_transaction_ids() == set()


def test_model_down_retries_then_leaves_items_without_proposal(uow, session_factory, db_session):
    ImportService(uow).import_pko_xml(fixture_bytes(WEEK41))
    uow.commit()
    service = LlmJobService(session_factory, lambda _uow: DownClassifier())

    assert service.process_one() is True
    job = db_session.scalar(select(models.LlmJob).where(models.LlmJob.attempts == 1))
    assert job.status is LlmJobStatus.PENDING and "nie działa" in job.last_error

    for _ in range(MAX_ATTEMPTS * 11):
        db_session.execute(update(models.LlmJob).values(next_attempt_at=date(2000, 1, 1)))
        db_session.commit()
        if not service.process_one():
            break
    db_session.expire_all()
    statuses = set(db_session.scalars(select(models.LlmJob.status)))
    assert statuses == {LlmJobStatus.FAILED}
    assert by(uow, merchant="NETFLIX.COM").classification.type is None


def test_disabled_llm_does_not_consume_queue(uow, session_factory):
    ImportService(uow).import_pko_xml(fixture_bytes(WEEK41))
    uow.commit()
    service = LlmJobService(session_factory, lambda _uow: None)
    assert service.process_one() is False
    assert len(uow.llm_jobs.queued_transaction_ids()) == 11


def test_user_decision_before_model_wins(uow, session_factory):
    from finbro.services.classification import ClassificationService, Decision

    ImportService(uow).import_pko_xml(fixture_bytes(WEEK41))
    income = by(uow, amount=Money.parse("4250.00"))
    ClassificationService(uow).decide(income.id, Decision(type=TxType.TRANSFER))
    assert income.id not in uow.llm_jobs.queued_transaction_ids()
    uow.commit()
    LlmJobService(session_factory, lambda _uow: FakeClassifier()).process_all()
    uow.session.expire_all()
    assert by(uow, amount=Money.parse("4250.00")).classification.type is TxType.TRANSFER


def test_interrupted_jobs_are_requeued_after_restart(uow, session_factory, db_session):
    ImportService(uow).import_pko_xml(fixture_bytes(WEEK41))
    db_session.execute(update(models.LlmJob).values(status=LlmJobStatus.RUNNING))
    db_session.commit()
    service = LlmJobService(session_factory, lambda _uow: FakeClassifier())
    assert service.requeue_interrupted() == 11
    assert service.process_all() == 11


def test_unreachable_model_server_is_treated_as_unavailable(uow, session_factory, db_session):
    ImportService(uow).import_pko_xml(fixture_bytes(WEEK41))
    uow.commit()
    server = LlmClassifier("http://127.0.0.1:1/engines/v1", "dowolny", timeout=2)
    assert LlmJobService(session_factory, lambda _uow: server).process_one() is True
    job = db_session.scalar(select(models.LlmJob).where(models.LlmJob.attempts == 1))
    assert job.status is LlmJobStatus.PENDING and "połączenia" in job.last_error


def test_worker_thread_processes_queue_in_background(uow, session_factory):
    ImportService(uow).import_pko_xml(fixture_bytes(WEEK41))
    uow.commit()
    worker = LlmWorker(LlmJobService(session_factory, lambda _uow: FakeClassifier()), idle_poll=0.05)
    worker.start()
    try:
        assert worker.idle.wait(timeout=30)
    finally:
        worker.stop()
    uow.session.expire_all()
    assert uow.llm_jobs.queued_transaction_ids() == set()
    assert by(uow, merchant="JMP S.A. BIEDRONKA 2422").classification.confirmed

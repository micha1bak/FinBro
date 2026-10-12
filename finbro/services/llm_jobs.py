"""Przetwarzanie kolejki klasyfikacji modelem językowym (jedno zadanie na raz)."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime, timedelta

from finbro.classification.pipeline import accept_if_allowed
from finbro.config import Settings
from finbro.domain.classification import ClassificationError, types_for
from finbro.domain.enums import LlmJobStatus
from finbro.domain.transactions import Transaction
from finbro.llm.classifier import Classifier, ClassifierContext, ClassifierUnavailable, Example, OllamaClassifier
from finbro.llm.view import build_view
from finbro.services.receivables import ReceivablesService
from finbro.services.uow import UnitOfWork

log = logging.getLogger(__name__)

MAX_ATTEMPTS = 5
BASE_RETRY_DELAY = timedelta(seconds=30)
MAX_RETRY_DELAY = timedelta(minutes=30)
EXAMPLES = 5


def retry_delay(attempts: int) -> timedelta:
    return min(BASE_RETRY_DELAY * (2 ** max(attempts - 1, 0)), MAX_RETRY_DELAY)


def model_name(settings: Settings, uow: UnitOfWork) -> str | None:
    """Model z ustawień aplikacji, a gdy pusty, z konfiguracji środowiska. Brak = LLM wyłączony."""
    return (uow.reference.config().llm_model or settings.ollama_model or "").strip() or None


def ollama_factory(settings: Settings) -> Callable[[UnitOfWork], Classifier | None]:
    cache: dict[tuple[str, str], OllamaClassifier] = {}

    def factory(uow: UnitOfWork) -> Classifier | None:
        model = model_name(settings, uow)
        if model is None:
            return None
        key = (settings.ollama_url, model)
        if key not in cache:
            cache[key] = OllamaClassifier(settings.ollama_url, model)
        return cache[key]

    return factory


class LlmJobService:
    def __init__(self, session_factory: Callable[[], object], classifier_factory: Callable[[UnitOfWork], Classifier | None]) -> None:
        self.session_factory = session_factory
        self.classifier_factory = classifier_factory

    def _uow(self) -> UnitOfWork:
        return UnitOfWork(self.session_factory())  # type: ignore[arg-type]

    def requeue_interrupted(self) -> int:
        uow = self._uow()
        try:
            count = uow.llm_jobs.requeue_running()
            uow.commit()
            return count
        finally:
            uow.close()

    def context_for(self, uow: UnitOfWork, tx: Transaction) -> ClassifierContext:
        categories = {c.name: c.id for c in uow.reference.categories(active_only=True) if not c.is_system}
        names = {c.id: c.name for c in uow.reference.categories()}
        examples = [
            Example(view=build_view(t), type=t.classification.type, category=names.get(t.classification.category_id))
            for t in uow.transactions.recent_user_decisions(tx.direction, EXAMPLES)
            if t.classification.type is not None
        ]
        return ClassifierContext(
            allowed_types=types_for(tx.direction),
            categories=categories,
            debtors={d.name: d.id for d in uow.reference.debtors()},
            examples=examples,
        )

    def process_one(self) -> bool:
        """Przetwarza jedno zadanie. Zwraca False, gdy nie było nic do zrobienia (albo LLM jest wyłączony)."""
        uow = self._uow()
        try:
            classifier = self.classifier_factory(uow)
            if classifier is None:
                return False
            job = uow.llm_jobs.claim_next()
            if job is None:
                uow.rollback()
                return False
            tx = uow.transactions.get(job.transaction_id)
            context = self.context_for(uow, tx)
            uow.commit()  # zadanie oznaczone jako przetwarzane; model działa poza transakcją bazy
        finally:
            uow.close()

        try:
            proposal = classifier.classify(build_view(tx), context)
        except ClassifierUnavailable as exc:
            self._retry_or_fail(job.id, job.attempts, str(exc))
            return True
        except Exception as exc:  # błąd nieoczekiwany: nie blokujemy kolejki
            log.exception("Błąd klasyfikacji transakcji %s", tx.id)
            self._retry_or_fail(job.id, job.attempts, repr(exc))
            return True
        self._store(job.id, tx.id, proposal)
        return True

    def _retry_or_fail(self, job_id: int, attempts: int, error: str) -> None:
        uow = self._uow()
        try:
            if attempts >= MAX_ATTEMPTS:
                uow.llm_jobs.finish(job_id, LlmJobStatus.FAILED, error)
            else:
                retry_at = datetime.now(UTC) + retry_delay(attempts)
                uow.llm_jobs.finish(job_id, LlmJobStatus.PENDING, error, retry_at=retry_at)
            uow.commit()
        finally:
            uow.close()

    def _store(self, job_id: int, transaction_id: int, proposal) -> None:
        uow = self._uow()
        try:
            tx = uow.transactions.get(transaction_id)
            current = tx.classification
            # Użytkownik mógł w międzyczasie zdecydować sam; jego decyzja ma pierwszeństwo.
            if proposal is not None and not current.confirmed and current.type is None:
                final = accept_if_allowed(tx, proposal)
                if final.confirmed and final.debtor_id is not None:
                    try:
                        ReceivablesService(uow).check_change(tx, final)
                    except ClassificationError:
                        final = replace(final, confirmed=False, confirmed_at=None)
                uow.transactions.set_classification(tx.id, final)
            uow.llm_jobs.finish(job_id, LlmJobStatus.DONE)
            uow.commit()
        finally:
            uow.close()

    def process_all(self, limit: int = 1000) -> int:
        """Przetwarza kolejkę do końca (testy, narzędzia). Zwraca liczbę przetworzonych zadań."""
        count = 0
        while count < limit and self.process_one():
            count += 1
        return count

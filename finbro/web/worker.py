"""Wątek w tle przetwarzający kolejkę klasyfikacji modelem językowym (D9).

Jeden wątek w procesie aplikacji przetwarza zadania sekwencyjnie. Kolejka jest
w bazie, więc zadania przetrwają restart.
"""

from __future__ import annotations

import logging
import threading

from finbro.services.llm_jobs import LlmJobService

log = logging.getLogger(__name__)

IDLE_POLL_SECONDS = 5.0


class LlmWorker:
    def __init__(self, service: LlmJobService, idle_poll: float = IDLE_POLL_SECONDS) -> None:
        self.service = service
        self.idle_poll = idle_poll
        self._stop = threading.Event()
        self.idle = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None:
            return
        try:
            requeued = self.service.requeue_interrupted()
            if requeued:
                log.info("Przywrócono do kolejki %s przerwanych zadań LLM", requeued)
        except Exception:
            log.exception("Nie udało się przywrócić przerwanych zadań LLM")
        self._thread = threading.Thread(target=self._run, name="finbro-llm-worker", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout)
            self._thread = None

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                worked = self.service.process_one()
            except Exception:
                log.exception("Błąd workera LLM")
                worked = False
            if worked:
                self.idle.clear()
                continue
            self.idle.set()
            self._stop.wait(self.idle_poll)

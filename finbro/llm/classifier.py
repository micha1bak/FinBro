"""Klasyfikator transakcji lokalnym modelem językowym (API zgodne z OpenAI, odpowiedź według schematu JSON).

Domyślnie Docker Model Runner (llama.cpp); działa też z Ollamą pod adresem ``.../v1``.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Protocol

import httpx

from finbro.domain.classification import REQUIRES_CATEGORY, REQUIRES_DEBTOR
from finbro.domain.enums import ProposalSource, TxType
from finbro.domain.transactions import Classification
from finbro.llm.view import TxView

log = logging.getLogger(__name__)

DEFAULT_TIMEOUT_SECONDS = 180.0

TYPE_HELP = {
    TxType.DOCHOD: "zarobek, wynagrodzenie, zapłata od klienta",
    TxType.WYDATEK: "zakup, opłata, rachunek (wymaga kategorii)",
    TxType.ODKLADANIE: "przelew oszczędności na inwestycje, obligacje lub wakacje",
    TxType.TRANSFER: "przesunięcie własnych pieniędzy, budżet rodzinny, gotówka z bankomatu",
    TxType.ZWROT: "zwrot pieniędzy za zakup (wymaga kategorii)",
    TxType.ROZLICZENIE: "ktoś oddaje swoją część wspólnego wydatku (wymaga kategorii)",
    TxType.POZYCZKA: "pożyczenie pieniędzy znajomej osobie (wymaga dłużnika)",
    TxType.SPLATA: "osoba oddaje pożyczone pieniądze (wymaga dłużnika)",
}


class ClassifierUnavailable(RuntimeError):
    """Serwer modelu nie odpowiedział poprawnie (do ponowienia później)."""


@dataclass(frozen=True)
class Example:
    view: TxView
    type: TxType
    category: str | None = None


@dataclass(frozen=True)
class ClassifierContext:
    """Dozwolone wartości odpowiedzi i kilka przykładów z historii użytkownika."""

    allowed_types: list[TxType]
    categories: dict[str, int]  # nazwa aktywnej kategorii -> id
    debtors: dict[str, int]  # nazwa dłużnika -> id
    examples: list[Example] = field(default_factory=list)


class Classifier(Protocol):
    def classify(self, view: TxView, context: ClassifierContext) -> Classification | None: ...


def response_schema(context: ClassifierContext) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "type": {"type": "string", "enum": [t.value for t in context.allowed_types]},
            "category": {"type": ["string", "null"], "enum": [*context.categories, None]},
            "debtor": {"type": ["string", "null"], "enum": [*context.debtors, None]},
            "reason": {"type": "string"},
        },
        "required": ["type", "category", "debtor", "reason"],
    }


def system_prompt(context: ClassifierContext) -> str:
    """Stały prefiks promptu (sprzyja cache'owi prefiksu po stronie serwera modelu)."""
    lines = [
        "Klasyfikujesz transakcje z polskiego konta bankowego. Odpowiadasz wyłącznie obiektem JSON.",
        "Typy:",
        *(f"- {t.value}: {TYPE_HELP[t]}" for t in TxType),
        "Kategorie wydatków: " + ", ".join(context.categories),
        "Dłużnicy: " + (", ".join(context.debtors) or "brak"),
        "Gdy typ nie wymaga kategorii ani dłużnika, wpisz null. Uzasadnienie: jedno krótkie zdanie po polsku.",
    ]
    if context.examples:
        lines.append("Przykłady wcześniejszych decyzji użytkownika:")
        for ex in context.examples:
            lines.append(
                json.dumps(ex.view.as_dict(), ensure_ascii=False)
                + f" => {ex.type.value}" + (f" / {ex.category}" if ex.category else "")
            )
    return "\n".join(lines)


def parse_answer(content: str, context: ClassifierContext) -> Classification | None:
    """Zamienia odpowiedź modelu na propozycję; wartości spoza schematu oznaczają brak propozycji."""
    try:
        data = json.loads(content)
    except (TypeError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    allowed = {t.value: t for t in context.allowed_types}
    tx_type = allowed.get(data.get("type"))
    category, debtor = data.get("category"), data.get("debtor")
    if tx_type is None:
        return None
    if category is not None and category not in context.categories:
        return None
    if debtor is not None and debtor not in context.debtors:
        return None
    reason = data.get("reason")
    return Classification(
        type=tx_type,
        category_id=context.categories.get(category) if tx_type in REQUIRES_CATEGORY and category else None,
        debtor_id=context.debtors.get(debtor) if tx_type in REQUIRES_DEBTOR and debtor else None,
        source=ProposalSource.LLM,
        reason=str(reason)[:500] if reason else None,
    )


class LlmClassifier:
    def __init__(
        self,
        base_url: str,
        model: str,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.model = model
        self._client = httpx.Client(base_url=base_url.rstrip("/"), timeout=timeout, transport=transport)

    def close(self) -> None:
        self._client.close()

    def classify(self, view: TxView, context: ClassifierContext) -> Classification | None:
        payload = {
            "model": self.model,
            "stream": False,
            "temperature": 0,
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "klasyfikacja", "strict": True, "schema": response_schema(context)},
            },
            # Modele z trybem rozumowania (np. Gemma 4) odpowiadają bez niego wielokrotnie szybciej.
            "chat_template_kwargs": {"enable_thinking": False},
            "messages": [
                {"role": "system", "content": system_prompt(context)},
                {"role": "user", "content": json.dumps(view.as_dict(), ensure_ascii=False)},
            ],
        }
        try:
            response = self._client.post("/chat/completions", json=payload)
        except httpx.HTTPError as exc:
            raise ClassifierUnavailable(f"Brak połączenia z serwerem modelu: {exc}") from exc
        if response.status_code >= 500 or response.status_code == 404:
            raise ClassifierUnavailable(f"Serwer modelu zwrócił błąd {response.status_code}: {response.text[:200]}")
        if response.status_code != 200:
            log.warning("Odpowiedź serwera modelu %s: %s", response.status_code, response.text[:200])
            return None
        try:
            content = response.json()["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError):
            return None
        return parse_answer(content, context)


def classify_or_none(classifier: Classifier, view: TxView, context: ClassifierContext) -> Classification | None:
    """Wariant bez wyjątków: niedostępny model oznacza brak propozycji."""
    try:
        return classifier.classify(view, context)
    except ClassifierUnavailable as exc:
        log.info("Model językowy niedostępny: %s", exc)
        return None

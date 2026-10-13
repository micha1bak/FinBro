"""Spike modelu językowego (zadanie 8.1): trafność i czas klasyfikacji na syntetycznych transakcjach.

Uruchomienie w kontenerze aplikacji (serwer modelu: Docker Model Runner, adres z LLM_URL):

    docker compose run --rm --no-deps -v ./scripts:/scripts:ro app python /scripts/llm_spike.py ai/gemma4:E2B

Dane są zmyślone. Skrypt używa tego samego klasyfikatora co aplikacja (prompt, schemat JSON,
walidacja odpowiedzi), a z odpowiedzi serwera zbiera dodatkowo liczbę tokenów.
"""

from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import dataclass

import httpx

from finbro.domain.classification import types_for
from finbro.domain.enums import TxType
from finbro.domain.transactions import Direction
from finbro.llm.classifier import ClassifierContext, Example, LlmClassifier
from finbro.llm.view import TxView

CATEGORIES = [
    "Spożywcze", "Restauracje i na mieście", "Transport", "Mieszkanie", "Abonamenty i subskrypcje",
    "Zdrowie", "Ubrania", "Dom i wyposażenie", "Rozrywka i hobby", "Prezenty", "Edukacja", "Podróże", "Inne",
]
DEBTORS = ["Martyna", "Tomek"]

W, D = TxType.WYDATEK, TxType.DOCHOD


@dataclass(frozen=True)
class Case:
    bank_type: str
    amount: str
    counterparty: str | None
    title: str | None
    type: TxType
    category: str | tuple[str, ...] | None = None  # krotka = kilka poprawnych odpowiedzi
    debtor: str | None = None

    @property
    def direction(self) -> Direction:
        return Direction.IN if self.type in {D, TxType.ZWROT, TxType.ROZLICZENIE, TxType.SPLATA} else Direction.OUT

    def view(self) -> TxView:
        return TxView(self.bank_type, self.direction.label, self.amount, "2026-10-07", self.counterparty, self.title)


CARD = "Płatność kartą"
OUT_TRANSFER = "Przelew z rachunku"
IN_TRANSFER = "Przelew na konto"

CASES = [
    Case(CARD, "54,30 zł", "BIEDRONKA 3412 WARSZAWA", None, W, "Spożywcze"),
    Case(CARD, "123,87 zł", "LIDL GRUNWALDZKA", None, W, "Spożywcze"),
    Case(CARD, "38,99 zł", "ZABKA Z5521 K.1", None, W, "Spożywcze"),
    Case(CARD, "289,40 zł", "ORLEN STACJA NR 512", None, W, "Transport"),
    Case(CARD, "27,50 zł", "UBER *TRIP HELP.UBER.COM", None, W, "Transport"),
    Case(CARD, "89,00 zł", "PKP INTERCITY", None, W, ("Transport", "Podróże")),
    Case(CARD, "60,00 zł", "NETFLIX.COM", None, W, "Abonamenty i subskrypcje"),
    Case(CARD, "23,99 zł", "SPOTIFY P2C4F81", None, W, "Abonamenty i subskrypcje"),
    Case(OUT_TRANSFER, "75,00 zł", "PLAY SA", "Faktura za telefon 10/2026", W, "Abonamenty i subskrypcje"),
    Case(CARD, "46,20 zł", "APTEKA DOZ 112", None, W, "Zdrowie"),
    Case(CARD, "250,00 zł", "MEDICOVER SP Z O O", None, W, "Zdrowie"),
    Case(CARD, "41,80 zł", "MCDONALDS 23 KRAKOW", None, W, "Restauracje i na mieście"),
    Case(CARD, "96,00 zł", "PIZZERIA DA GRASSO", None, W, "Restauracje i na mieście"),
    Case(OUT_TRANSFER, "780,00 zł", "WSPOLNOTA MIESZKANIOWA ZIELONA 5", "Czynsz październik 2026", W, "Mieszkanie"),
    Case(OUT_TRANSFER, "212,34 zł", "TAURON SPRZEDAZ SP Z O O", "Faktura za energię elektryczną", W, "Mieszkanie"),
    Case(CARD, "199,90 zł", "ZARA POLSKA", None, W, "Ubrania"),
    Case(CARD, "349,00 zł", "IKEA KRAKOW", None, W, "Dom i wyposażenie"),
    Case(CARD, "58,00 zł", "CINEMA CITY BONARKA", None, W, "Rozrywka i hobby"),
    Case(CARD, "69,99 zł", "UDEMY.COM", None, W, "Edukacja"),
    Case(CARD, "640,00 zł", "BOOKING.COM HOTEL", None, W, "Podróże"),
    Case(CARD, "129,00 zł", "SMYK SKLEP ZABAWKI", None, W, ("Prezenty", "Inne")),
    Case("Przelew na telefon", "300,00 zł", "Martyna", "Pożyczka do wypłaty", TxType.POZYCZKA, debtor="Martyna"),
    Case(OUT_TRANSFER, "1000,00 zł", "XTB S.A.", "Wpłata na rachunek inwestycyjny", TxType.ODKLADANIE),
    Case(OUT_TRANSFER, "1500,00 zł", "ANNA TESTOWA", "Na wspólne wydatki domowe", TxType.TRANSFER),
    Case(IN_TRANSFER, "7380,00 zł", "SOFTWARE HOUSE TESTOWY SP Z O O", "FV 12/2026 usługi programistyczne", D),
    Case(IN_TRANSFER, "2500,00 zł", "STUDIO GRAFICZNE PRZYKLAD", "Wynagrodzenie za projekt logo", D),
    Case(IN_TRANSFER, "300,00 zł", "Martyna", "Oddaję pożyczkę, dzięki!", TxType.SPLATA, debtor="Martyna"),
    Case(IN_TRANSFER, "48,00 zł", "TOMASZ PRZYKLADOWY", "Za pizzę wczoraj", TxType.ROZLICZENIE, "Restauracje i na mieście"),
    Case("Zwrot płatności kartą", "199,90 zł", "ZALANDO SE", "Zwrot zamówienia", TxType.ZWROT, "Ubrania"),
    Case(IN_TRANSFER, "150,00 zł", "Tomek", "Oddaję kasę", TxType.SPLATA, debtor="Tomek"),
]

# Przykłady wcześniejszych decyzji (jak w aplikacji: do 5 ostatnich decyzji w tym samym kierunku).
EXAMPLES = {
    Direction.OUT: [
        Example(TxView(CARD, "wydatek", "35,10 zł", "2026-10-01", "KAUFLAND 1022", None), W, "Spożywcze"),
        Example(TxView(CARD, "wydatek", "15,00 zł", "2026-10-02", "JAKDOJADE", None), W, "Transport"),
    ],
    Direction.IN: [
        Example(TxView(IN_TRANSFER, "wpływ", "5200,00 zł", "2026-10-01", "KANCELARIA TESTOWA", "FV 9/2026"), D),
    ],
}


class RecordingTransport(httpx.HTTPTransport):
    """Zapamiętuje ostatnią odpowiedź serwera modelu (liczba tokenów)."""

    last: dict = {}

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        response = super().handle_request(request)
        response.read()
        try:
            RecordingTransport.last = response.json()
        except ValueError:
            RecordingTransport.last = {}
        return response


def context_for(case: Case, with_examples: bool) -> ClassifierContext:
    return ClassifierContext(
        allowed_types=types_for(case.direction),
        categories={name: i for i, name in enumerate(CATEGORIES, start=1)},
        debtors={name: i for i, name in enumerate(DEBTORS, start=1)},
        examples=EXAMPLES[case.direction] if with_examples else [],
    )


def run(model: str, with_examples: bool) -> None:
    url = os.environ.get("LLM_URL", "http://model-runner.docker.internal/engines/v1")
    classifier = LlmClassifier(url, model, transport=RecordingTransport())
    names = {i: n for i, n in enumerate(CATEGORIES, start=1)}
    debtors = {i: n for i, n in enumerate(DEBTORS, start=1)}
    type_ok = cat_ok = cat_total = debtor_ok = debtor_total = no_answer = 0
    times: list[float] = []
    print(f"\n## {model}, przykłady z historii: {'tak' if with_examples else 'nie'}\n")
    print("| # | kontrahent | oczekiwane | odpowiedź | czas [s] | tokeny wej./wyj. |")
    print("|---|---|---|---|---|---|")
    for i, case in enumerate(CASES, start=1):
        started = time.perf_counter()
        result = classifier.classify(case.view(), context_for(case, with_examples))
        elapsed = time.perf_counter() - started
        times.append(elapsed)
        stats = RecordingTransport.last
        accepted = case.category if isinstance(case.category, tuple) else (case.category,)
        expected = case.type.value + (f" / {' lub '.join(accepted)}" if case.category else "") + (f" / {case.debtor}" if case.debtor else "")
        correct = False
        if result is None:
            no_answer += 1
            got = "brak propozycji"
        else:
            category = names.get(result.category_id) if result.category_id else None
            debtor = debtors.get(result.debtor_id) if result.debtor_id else None
            got = result.type.value + (f" / {category}" if category else "") + (f" / {debtor}" if debtor else "")
            type_ok += result.type == case.type
            correct = result.type == case.type
            if case.category:
                cat_total += 1
                correct = correct and category in accepted
                cat_ok += correct
            if case.debtor:
                debtor_total += 1
                correct = correct and debtor == case.debtor
                debtor_ok += correct
        mark = "" if correct else " ✗"
        usage = stats.get("usage") or {}
        tokens = f"{usage.get('prompt_tokens', '?')}/{usage.get('completion_tokens', '?')}"
        print(f"| {i} | {case.counterparty} | {expected} | {got}{mark} | {elapsed:.1f} | {tokens} |", flush=True)
    classifier.close()
    n = len(CASES)
    print(f"\nTyp: {type_ok}/{n}. Kategoria: {cat_ok}/{cat_total}. Dłużnik: {debtor_ok}/{debtor_total}. Brak propozycji: {no_answer}.")
    print(f"Czas na transakcję: średnio {sum(times) / n:.1f} s, mediana {sorted(times)[n // 2]:.1f} s, "
          f"pierwsza (z ładowaniem modelu) {times[0]:.1f} s, maks. {max(times):.1f} s.")
    print(json.dumps({"model": model, "examples": with_examples, "type_ok": type_ok, "category_ok": cat_ok,
                      "category_total": cat_total, "debtor_ok": debtor_ok, "debtor_total": debtor_total,
                      "no_answer": no_answer, "times": [round(t, 2) for t in times]}, ensure_ascii=False))


if __name__ == "__main__":
    model = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("LLM_MODEL", "")
    if not model:
        raise SystemExit("Podaj nazwę modelu, np. python /scripts/llm_spike.py ai/gemma4:E2B")
    for with_examples in (False, True):
        run(model, with_examples)

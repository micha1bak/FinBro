import json

import httpx
import pytest

from finbro.domain.enums import ProposalSource, TxType
from finbro.domain.transactions import Direction
from finbro.domain.classification import types_for
from finbro.llm.classifier import (
    ClassifierContext,
    ClassifierUnavailable,
    OllamaClassifier,
    classify_or_none,
    response_schema,
)
from finbro.llm.view import TxView

VIEW = TxView(bank_type="Płatność kartą", direction="wydatek", amount="89,99 zł", date="2026-10-08",
              counterparty="KINO HELIOS", title=None)
CONTEXT = ClassifierContext(
    allowed_types=types_for(Direction.OUT),
    categories={"Spożywcze": 1, "Rozrywka i hobby": 9},
    debtors={"Martyna": 3},
)


def classifier_with(handler) -> OllamaClassifier:
    return OllamaClassifier("http://ollama:11434", "test-model", transport=httpx.MockTransport(handler))


def answering(content: dict | str, status: int = 200):
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(json.loads(request.content))
        body = content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)
        return httpx.Response(status, json={"message": {"role": "assistant", "content": body}})

    return handler, requests


def test_valid_answer_becomes_llm_proposal():
    handler, requests = answering({"type": "WYDATEK", "category": "Rozrywka i hobby", "debtor": None, "reason": "bilety do kina"})
    proposal = classifier_with(handler).classify(VIEW, CONTEXT)
    assert proposal.type is TxType.WYDATEK
    assert proposal.category_id == 9
    assert proposal.source is ProposalSource.LLM
    assert proposal.reason == "bilety do kina"
    assert not proposal.confirmed

    [sent] = requests
    assert sent["model"] == "test-model" and sent["stream"] is False
    assert sent["format"] == response_schema(CONTEXT)
    assert sent["format"]["properties"]["type"]["enum"] == ["WYDATEK", "ODKLADANIE", "TRANSFER", "POZYCZKA"]
    assert sent["format"]["properties"]["category"]["enum"] == ["Spożywcze", "Rozrywka i hobby", None]
    assert json.loads(sent["messages"][-1]["content"]) == VIEW.as_dict()


@pytest.mark.parametrize(
    "answer",
    [
        {"type": "DOCHOD", "category": None, "debtor": None, "reason": "?"},  # typ spoza dozwolonych dla wydatku
        {"type": "WYDATEK", "category": "Kosmetyki", "debtor": None, "reason": "?"},  # kategoria spoza listy
        {"type": "POZYCZKA", "category": None, "debtor": "Zenek", "reason": "?"},  # nieznany dłużnik
        "to nie jest JSON",
        "[1, 2]",
    ],
)
def test_out_of_schema_answer_means_no_proposal(answer):
    handler, _ = answering(answer)
    assert classifier_with(handler).classify(VIEW, CONTEXT) is None


def test_debtor_is_mapped_for_loans_and_ignored_otherwise():
    handler, _ = answering({"type": "POZYCZKA", "category": "Spożywcze", "debtor": "Martyna", "reason": "BLIK do znajomej"})
    proposal = classifier_with(handler).classify(VIEW, CONTEXT)
    assert (proposal.type, proposal.debtor_id, proposal.category_id) == (TxType.POZYCZKA, 3, None)


def test_server_error_means_no_proposal():
    def handler(request):
        return httpx.Response(500, text="model failed to load")

    classifier = classifier_with(handler)
    with pytest.raises(ClassifierUnavailable):
        classifier.classify(VIEW, CONTEXT)
    assert classify_or_none(classifier, VIEW, CONTEXT) is None


def test_connection_error_means_no_proposal():
    def handler(request):
        raise httpx.ConnectError("connection refused", request=request)

    assert classify_or_none(classifier_with(handler), VIEW, CONTEXT) is None

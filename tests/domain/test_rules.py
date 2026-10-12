import importlib.util
from datetime import date
from pathlib import Path

import pytest

import finbro
from finbro.domain.enums import ProposalSource, TransferKind, TxSource, TxType
from finbro.domain.money import Money
from finbro.domain.rules import Rule, RuleConditions, RuleError, RuleResult, first_match, validate_rule
from finbro.domain.text import fold
from finbro.domain.transactions import TransactionData
from finbro.importers.pko_xml import parse_statement
from finbro.services.importing import operation_to_data
from tests.helpers import OVERLAP, WEEK41, fixture_bytes


def tx(amount: str, **fields) -> TransactionData:
    return TransactionData(source=TxSource.IMPORT, transaction_date=date(2026, 10, 7), amount=Money.parse(amount), **fields)


def rule(name, conditions, result_type, priority=100, rule_id=None, **result):
    return Rule(
        id=rule_id,
        name=name,
        priority=priority,
        conditions=RuleConditions.from_json(conditions),
        result=RuleResult(type=result_type, **result),
    )


def test_fold():
    assert fold("  Wpłata   GOTÓWKI ") == "wplata gotowki"
    assert fold(None) == ""


def test_text_conditions_ignore_case_diacritics_and_accept_lists():
    conditions = RuleConditions.from_json({"bank_type": ["wpłatomat", "wplata gotowk"]})
    assert conditions.matches(tx("+10.00", bank_type="Wpłata gotówki we wpłatomacie"))
    assert conditions.matches(tx("+10.00", bank_type="WPŁATA GOTÓWKOWA W KASIE"))
    assert not conditions.matches(tx("+10.00", bank_type="Przelew na konto"))


def test_all_conditions_must_match():
    conditions = RuleConditions.from_json({"direction": "OUT", "bank_type": "Przelew z karty", "merchant": "Revolut"})
    assert conditions.matches(tx("-300.00", bank_type="Przelew z karty", merchant="Revolut**4321*"))
    assert not conditions.matches(tx("+300.00", bank_type="Przelew z karty", merchant="Revolut**4321*"))
    assert not conditions.matches(tx("-300.00", bank_type="Przelew z karty", merchant="ZONDA"))
    assert not conditions.matches(tx("-300.00", bank_type="Przelew z karty"))


def test_counterparty_account_and_amount_range():
    conditions = RuleConditions.from_json(
        {"counterparty_account": "PL61 1140 2004 0000 3502 7777 0001", "amount_min": "100", "amount_max": "500.00"}
    )
    assert conditions.matches(tx("+477.08", counterparty_account="61 1140 2004 0000 3502 7777 0001"))
    assert not conditions.matches(tx("+77.08", counterparty_account="61 1140 2004 0000 3502 7777 0001"))
    assert not conditions.matches(tx("+577.08", counterparty_account="61 1140 2004 0000 3502 7777 0001"))
    assert not conditions.matches(tx("+477.08", counterparty_account="61 1140 2004 0000 3502 7777 0002"))
    assert not conditions.matches(tx("+477.08"))


@pytest.mark.parametrize(
    "data",
    [
        {},
        {"direction": "OUT"},
        {"kolor": "zielony"},
        {"direction": "BOTH", "title": "x"},
        {"title": 5},
        {"title": ["", " "]},
        {"amount_min": "abc"},
        {"amount_min": "-5"},
        {"amount_min": "10", "amount_max": "5"},
        ["title"],
    ],
)
def test_invalid_conditions(data):
    with pytest.raises(RuleError):
        RuleConditions.from_json(data)


def test_conditions_json_roundtrip():
    data = {"direction": "IN", "bank_type": ["a", "b"], "counterparty_name": "X", "amount_min": "1.50"}
    assert RuleConditions.from_json(data).to_json() == data


def test_priority_order_and_inactive_rules():
    general = rule("ogólna", {"title": "zwrot"}, TxType.ZWROT, priority=50, rule_id=1, category_id=3)
    specific = rule("rodzina", {"counterparty_name": "KOWALSKA"}, TxType.TRANSFER, priority=10, rule_id=2,
                    transfer_kind=TransferKind.FAMILY)
    t = tx("+477.08", counterparty_name="ANNA KOWALSKA-TESTOWA", title="zwrot za zakupy rodzinne")
    assert first_match([general, specific], t) is specific
    inactive = Rule(**{**specific.__dict__, "active": False})
    assert first_match([general, inactive], t) is general
    assert first_match([], t) is None


def test_rule_never_assigns_type_against_direction():
    income = rule("dochód od X", {"counterparty_name": "X"}, TxType.DOCHOD)
    assert first_match([income], tx("-10.00", counterparty_name="X")) is None
    assert first_match([income], tx("+10.00", counterparty_name="X")) is income


def test_proposal_from_rule():
    r = rule("FinBro", {"title": "FinBro"}, TxType.ODKLADANIE, rule_id=7)
    proposal = r.proposal()
    assert proposal.type is TxType.ODKLADANIE
    assert proposal.source is ProposalSource.RULE
    assert proposal.rule_id == 7
    assert "FinBro" in proposal.reason
    assert not proposal.confirmed


def test_validate_rule_result():
    validate_rule(RuleConditions.from_json({"direction": "OUT", "merchant": "x"}), RuleResult(TxType.WYDATEK, category_id=1))
    with pytest.raises(RuleError, match="kategorii"):
        validate_rule(RuleConditions.from_json({"direction": "OUT", "merchant": "x"}), RuleResult(TxType.WYDATEK))
    with pytest.raises(RuleError, match="kierunku"):
        validate_rule(RuleConditions.from_json({"direction": "OUT", "merchant": "x"}), RuleResult(TxType.DOCHOD))
    validate_rule(RuleConditions.from_json({"merchant": "x"}), RuleResult(TxType.TRANSFER))


# --- reguły startowe z migracji danych na operacjach z fixture'ów ---


MIGRATIONS = Path(finbro.__file__).parent / "db" / "migrations" / "versions"


def starter_rules() -> list[Rule]:
    migration = next(MIGRATIONS.glob("*_0002_dane_poczatkowe.py"))
    spec = importlib.util.spec_from_file_location("seed_migration", migration)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return [
        Rule(
            id=i,
            name=r["name"],
            priority=r["priority"],
            conditions=RuleConditions.from_json(r["conditions"]),
            result=RuleResult(
                type=TxType(r["result_type"]),
                transfer_kind=TransferKind(r["result_transfer_kind"]) if r["result_transfer_kind"] else None,
            ),
        )
        for i, r in enumerate(module.RULES, start=1)
    ]


def fixture_transactions(name: str) -> list[TransactionData]:
    statement = parse_statement(fixture_bytes(name))
    return [operation_to_data(op, account_id=1, occurrence=1, batch_id=1) for op in statement.booked]


def matched(rules, txs, predicate):
    [t] = [t for t in txs if predicate(t)]
    found = first_match(rules, t)
    return (found.result.type, found.result.transfer_kind) if found else None


def test_starter_rules_on_fixture_operations():
    rules = starter_rules()
    week41 = fixture_transactions(WEEK41)
    week42 = fixture_transactions(OVERLAP)

    assert matched(rules, week41, lambda t: t.bank_type == "Wypłata w bankomacie") == (TxType.TRANSFER, TransferKind.WALLET)
    assert matched(rules, week41, lambda t: t.bank_type == "Wpłata gotówki we wpłatomacie") == (TxType.TRANSFER, TransferKind.WALLET)
    assert matched(rules, week41, lambda t: t.bank_type == "Przelew z karty") == (TxType.TRANSFER, TransferKind.FAMILY)
    assert matched(rules, week42, lambda t: t.title == "FinBro 2026-T41 Wakacje") == (TxType.ODKLADANIE, None)
    assert matched(rules, week42, lambda t: t.title == "finbro 2026-t41 xtb") == (TxType.ODKLADANIE, None)

    # Pozostałe operacje nie pasują do żadnej reguły startowej.
    assert matched(rules, week41, lambda t: t.merchant == "JMP S.A. BIEDRONKA 2422") is None
    assert matched(rules, week41, lambda t: t.amount == Money.parse("4250.00")) is None
    assert matched(rules, week42, lambda t: t.title == "zakup obligacji") is None

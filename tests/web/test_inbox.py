from datetime import date

from sqlalchemy import select

from finbro.db import models
from finbro.domain.enums import ProposalSource, TxType
from finbro.domain.money import Money
from finbro.services.uow import UnitOfWork
from tests.helpers import OVERLAP, WEEK41

HTMX = {"HX-Request": "true"}


def tx_by(session_factory, **criteria):
    uow = UnitOfWork(session_factory())
    try:
        txs = uow.transactions.list_between(date(2026, 1, 1), date(2026, 12, 31))
        [match] = [t for t in txs if all(getattr(t.data, k) == v for k, v in criteria.items())]
        return match
    finally:
        uow.close()


def category_id(db_session, name):
    return db_session.scalar(select(models.Category.id).where(models.Category.name == name))


def add_income_rule(session_factory):
    from finbro.domain.rules import Rule, RuleConditions, RuleResult

    uow = UnitOfWork(session_factory())
    uow.rules.add(Rule(name="Kancelaria", priority=50,
                       conditions=RuleConditions.from_json({"direction": "IN", "counterparty_name": "KANCELARIA"}),
                       result=RuleResult(type=TxType.DOCHOD)))
    uow.commit()
    uow.close()


def test_inbox_lists_items_with_proposals(client, upload, session_factory):
    add_income_rule(session_factory)
    upload(WEEK41)
    response = client.get("/inbox")
    assert response.status_code == 200
    income = tx_by(session_factory, amount=Money.parse("4250.00"))
    assert f'id="tx-{income.id}"' in response.text
    assert "DOCHÓD" in response.text and "reguła" in response.text
    # Transakcje przyjęte automatycznie (bankomat) nie trafiają do skrzynki.
    atm = tx_by(session_factory, bank_type="Wypłata w bankomacie")
    assert f'id="tx-{atm.id}"' not in response.text
    assert "Zatwierdź wszystkie dochody z reguł" in response.text


def test_accept_proposal_with_one_click(client, upload, session_factory):
    add_income_rule(session_factory)
    upload(WEEK41)
    income = tx_by(session_factory, amount=Money.parse("4250.00"))
    response = client.post(f"/inbox/{income.id}/accept", headers=HTMX)
    assert response.status_code == 200
    assert response.text == ""  # wiersz znika ze skrzynki
    c = tx_by(session_factory, amount=Money.parse("4250.00")).classification
    assert (c.type, c.confirmed, c.source) == (TxType.DOCHOD, True, ProposalSource.RULE)
    assert f'id="tx-{income.id}"' not in client.get("/inbox").text


def test_change_classification(client, upload, session_factory, db_session):
    upload(WEEK41)
    payment = tx_by(session_factory, merchant="JMP S.A. BIEDRONKA 2422")
    groceries = category_id(db_session, "Spożywcze")
    response = client.post(
        f"/inbox/{payment.id}/decide", data={"type": "WYDATEK", "category_id": str(groceries)}, headers=HTMX
    )
    assert response.text == ""
    c = tx_by(session_factory, merchant="JMP S.A. BIEDRONKA 2422").classification
    assert (c.type, c.category_id, c.source, c.confirmed) == (TxType.WYDATEK, groceries, ProposalSource.USER, True)
    # Zadanie LLM dla tej transakcji jest anulowane.
    uow = UnitOfWork(session_factory())
    assert payment.id not in uow.llm_jobs.queued_transaction_ids()
    uow.close()


def test_invalid_decision_shows_error_in_row(client, upload, session_factory):
    upload(WEEK41)
    payment = tx_by(session_factory, merchant="JMP S.A. BIEDRONKA 2422")
    response = client.post(f"/inbox/{payment.id}/decide", data={"type": "DOCHOD"}, headers=HTMX)
    assert response.status_code == 200
    assert "nie pasuje do kierunku" in response.text
    assert f'id="tx-{payment.id}"' in response.text
    response = client.post(f"/inbox/{payment.id}/decide", data={"type": "WYDATEK"})
    assert response.status_code == 400
    assert "wymaga wskazania kategorii" in response.text
    assert not tx_by(session_factory, merchant="JMP S.A. BIEDRONKA 2422").classification.confirmed


def test_system_category_cannot_be_chosen(client, upload, session_factory, db_session):
    upload(WEEK41)
    payment = tx_by(session_factory, merchant="JMP S.A. BIEDRONKA 2422")
    system = db_session.scalar(select(models.Category.id).where(models.Category.is_system))
    response = client.post(f"/inbox/{payment.id}/decide", data={"type": "WYDATEK", "category_id": str(system)}, headers=HTMX)
    assert "systemowa" in response.text


def test_remember_as_rule_applies_to_next_import(client, upload, session_factory, db_session):
    upload(WEEK41)
    income = tx_by(session_factory, amount=Money.parse("4250.00"))
    response = client.post(f"/inbox/{income.id}/decide", data={"type": "DOCHOD", "remember": "on"}, follow_redirects=False)
    assert response.status_code == 303
    rule = db_session.scalar(select(models.Rule).where(models.Rule.name.like("KANCELARIA%")))
    assert rule is not None and rule.conditions["counterparty_account"] == "12 1140 2004 0000 3102 1234 5678"

    upload(OVERLAP)
    later = tx_by(session_factory, amount=Money.parse("3100.00")).classification
    assert (later.type, later.source, later.rule_id, later.confirmed) == (TxType.DOCHOD, ProposalSource.RULE, rule.id, False)


def test_new_debtor_from_inbox(client, upload, session_factory, db_session):
    upload(WEEK41)
    loan = tx_by(session_factory, bank_type="Przelew na telefon przychodz. zew.")
    client.post(f"/inbox/{loan.id}/decide", data={"type": "POZYCZKA", "new_debtor_name": "Martyna"}, headers=HTMX)
    debtor = db_session.scalar(select(models.Debtor).where(models.Debtor.name == "Martyna"))
    c = tx_by(session_factory, bank_type="Przelew na telefon przychodz. zew.").classification
    assert (c.type, c.debtor_id, c.confirmed) == (TxType.POZYCZKA, debtor.id, True)


def test_bulk_approve_rule_incomes(client, upload, session_factory):
    add_income_rule(session_factory)
    upload(WEEK41)
    response = client.post("/inbox/approve-rule-incomes", follow_redirects=True)
    assert "Zatwierdzono dochody z reguł: 1" in response.text
    assert tx_by(session_factory, amount=Money.parse("4250.00")).classification.confirmed
    # Dochody spoza reguł pozostają niezatwierdzone.
    assert not tx_by(session_factory, amount=Money.parse("705.87")).classification.confirmed

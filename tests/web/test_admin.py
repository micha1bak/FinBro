"""Panel administracyjny: walidacja planu podziału i ochrona kategorii systemowej."""

from datetime import date

from sqlalchemy import select

from finbro.db import models


def envelope_ids(db_session) -> dict[str, int]:
    return {e.code: e.id for e in db_session.scalars(select(models.Envelope))}


def plan_form(ids: dict[str, int], percents: dict[str, str], effective_from: str = "2026-11-02") -> dict[str, str]:
    form = {"effective_from": effective_from, "save": "Save"}
    form.update({f"share_{ids[code]}": value for code, value in percents.items()})
    return form


def plans_from(db_session, day: date):
    return db_session.scalars(select(models.AllocationPlan).where(models.AllocationPlan.effective_from == day)).all()


def test_plan_summing_to_95_percent_is_rejected(client, db_session):
    ids = envelope_ids(db_session)
    response = client.post(
        "/admin/allocation-plan/create",
        data=plan_form(ids, {"zycie": "50", "xtb": "12,5", "obligacje": "12,5", "wakacje": "20"}),
        follow_redirects=False,
    )
    assert response.status_code == 400
    assert "Suma udziałów musi wynosić 100%" in response.text
    assert plans_from(db_session, date(2026, 11, 2)) == []


def test_plan_summing_to_100_percent_is_saved(client, db_session):
    ids = envelope_ids(db_session)
    response = client.post(
        "/admin/allocation-plan/create",
        data=plan_form(ids, {"zycie": "60", "xtb": "10", "obligacje": "10", "wakacje": "20"}),
        follow_redirects=False,
    )
    assert response.status_code == 302
    [plan] = plans_from(db_session, date(2026, 11, 2))
    shares = {s.envelope_id: s.basis_points for s in plan.shares}
    assert shares == {ids["zycie"]: 6000, ids["xtb"]: 1000, ids["obligacje"]: 1000, ids["wakacje"]: 2000}

    listing = client.get("/admin/allocation-plan/list")
    assert listing.status_code == 200
    assert "2026-11-02" in listing.text


def test_plan_edit_form_shows_current_percentages(client, db_session):
    [plan] = db_session.scalars(select(models.AllocationPlan)).all()
    response = client.get(f"/admin/allocation-plan/edit/{plan.id}")
    assert response.status_code == 200
    assert 'value="12,5"' in response.text


def test_system_category_cannot_be_edited(client, db_session):
    system = db_session.scalar(select(models.Category).where(models.Category.is_system))
    response = client.post(
        f"/admin/category/edit/{system.id}",
        data={"name": "Zmieniona", "active": "y", "sort_order": "1", "save": "Save"},
        follow_redirects=False,
    )
    assert response.status_code in (400, 403)
    db_session.expire_all()
    assert db_session.get(models.Category, system.id).name == "Gotówka (bez kategorii)"


def test_regular_category_can_be_renamed_and_added(client, db_session):
    regular = db_session.scalar(select(models.Category).where(models.Category.name == "Inne"))
    response = client.post(
        f"/admin/category/edit/{regular.id}",
        data={"name": "Różne", "active": "y", "sort_order": "130", "save": "Save"},
        follow_redirects=False,
    )
    assert response.status_code == 302
    response = client.post(
        "/admin/category/create",
        data={"name": "Zwierzęta", "active": "y", "sort_order": "125", "save": "Save"},
        follow_redirects=False,
    )
    assert response.status_code == 302
    db_session.expire_all()
    names = set(db_session.scalars(select(models.Category.name)))
    assert {"Różne", "Zwierzęta"} <= names and "Inne" not in names


def test_settings_can_be_edited(client, db_session):
    response = client.post(
        "/admin/app-settings/edit/1",
        data={"start_date": "2026-10-05", "main_account_number": "12 1020 0000 0000 0000 0000 0001", "llm_model": "", "save": "Save"},
        follow_redirects=False,
    )
    assert response.status_code == 302
    db_session.expire_all()
    assert db_session.get(models.AppSettings, 1).start_date == date(2026, 10, 5)

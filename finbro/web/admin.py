"""Panel administracyjny (SQLAdmin) dla danych słownikowych i ustawień.

SQLAdmin z definicji działa bezpośrednio na modelach SQLAlchemy, dlatego ten moduł
jest jedynym wyjątkiem od zasady, że warstwa webowa nie korzysta z bazy bezpośrednio.
Walidacja reguł biznesowych pochodzi z domeny.
"""

from __future__ import annotations

from typing import Any

import anyio
from fastapi import FastAPI, Request
from sqladmin import Admin, ModelView
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session, selectinload, sessionmaker
from wtforms import DateField, Form, StringField
from wtforms.validators import InputRequired

from finbro.db.models import (
    AllocationPlan,
    AllocationShare,
    AppSettings,
    Category,
    Debtor,
    Envelope,
    Rule,
)
from finbro.domain.allocation import AllocationError, format_basis_points, parse_percent, validate_shares


class CategoryAdmin(ModelView, model=Category):
    name = "Kategoria"
    name_plural = "Kategorie"
    icon = "fa-solid fa-tags"
    column_list = [Category.name, Category.active, Category.is_system, Category.sort_order]
    column_labels = {
        Category.name: "Nazwa",
        Category.active: "Aktywna",
        Category.is_system: "Systemowa",
        Category.sort_order: "Kolejność",
    }
    form_columns = [Category.name, Category.active, Category.sort_order]
    column_default_sort = "sort_order"
    # Kategorii się nie usuwa (transakcje zachowują kategorię), tylko dezaktywuje.
    can_delete = False

    async def check_can_edit(self, request: Request, model: Any) -> bool:
        return await super().check_can_edit(request, model) and not model.is_system

    async def on_model_change(self, data: dict, model: Any, is_created: bool, request: Request) -> None:
        if not is_created and model.is_system:
            raise ValueError("Kategoria systemowa nie może być edytowana.")


class DebtorAdmin(ModelView, model=Debtor):
    name = "Dłużnik"
    name_plural = "Dłużnicy"
    icon = "fa-solid fa-user"
    column_list = [Debtor.name, Debtor.aliases, Debtor.note]
    column_labels = {Debtor.name: "Nazwa", Debtor.aliases: "Inne nazwy w banku (po jednej w linii)", Debtor.note: "Notatka"}
    form_columns = [Debtor.name, Debtor.aliases, Debtor.note]


class EnvelopeAdmin(ModelView, model=Envelope):
    name = "Koperta"
    name_plural = "Koperty"
    icon = "fa-solid fa-envelope"
    column_list = [Envelope.name, Envelope.target_account, Envelope.is_life]
    column_labels = {Envelope.name: "Nazwa", Envelope.target_account: "Rachunek docelowy", Envelope.is_life: "Życie"}
    form_columns = [Envelope.name, Envelope.target_account]
    column_default_sort = "sort_order"
    # Zestaw kopert jest stały; edytuje się nazwę i rachunek docelowy.
    can_create = False
    can_delete = False


class RuleAdmin(ModelView, model=Rule):
    name = "Reguła"
    name_plural = "Reguły"
    icon = "fa-solid fa-filter"
    column_list = [Rule.priority, Rule.name, Rule.active, Rule.result_type, Rule.conditions]
    column_labels = {
        Rule.name: "Nazwa",
        Rule.priority: "Priorytet (mniejszy = ważniejszy)",
        Rule.active: "Aktywna",
        Rule.conditions: "Warunki (JSON)",
        Rule.result_type: "Typ",
        Rule.result_category: "Kategoria",
        Rule.result_debtor: "Dłużnik",
        Rule.result_transfer_kind: "Rodzaj transferu",
    }
    form_columns = [
        Rule.name,
        Rule.priority,
        Rule.active,
        Rule.conditions,
        Rule.result_type,
        Rule.result_category,
        Rule.result_debtor,
        Rule.result_transfer_kind,
    ]
    column_default_sort = "priority"


class SettingsAdmin(ModelView, model=AppSettings):
    name = "Ustawienia"
    name_plural = "Ustawienia"
    icon = "fa-solid fa-gear"
    column_list = [AppSettings.start_date, AppSettings.main_account_number, AppSettings.llm_model]
    column_labels = {
        AppSettings.start_date: "Data startu rozliczeń",
        AppSettings.main_account_number: "Numer konta głównego",
        AppSettings.llm_model: "Model LLM (pusty = z konfiguracji)",
    }
    form_columns = [AppSettings.start_date, AppSettings.main_account_number, AppSettings.llm_model]
    can_create = False
    can_delete = False


class AllocationPlanAdmin(ModelView, model=AllocationPlan):
    """Plan podziału z udziałem każdej koperty w jednym formularzu."""

    name = "Plan podziału"
    name_plural = "Plany podziału"
    icon = "fa-solid fa-chart-pie"
    column_list = [AllocationPlan.effective_from, AllocationPlan.shares]
    column_labels = {AllocationPlan.effective_from: "Obowiązuje od", AllocationPlan.shares: "Udziały"}
    column_formatters = {
        AllocationPlan.shares: lambda m, a: ", ".join(
            f"{s.envelope.name} {format_basis_points(s.basis_points)}" for s in m.shares
        )
    }
    column_formatters_detail = column_formatters
    column_default_sort = ("effective_from", True)

    def _with_shares(self, stmt: Any) -> Any:
        return stmt.options(selectinload(AllocationPlan.shares).selectinload(AllocationShare.envelope))

    def list_query(self, request: Request) -> Any:
        return self._with_shares(super().list_query(request))

    def details_query(self, request: Request) -> Any:
        return self._with_shares(super().details_query(request))

    def form_edit_query(self, request: Request) -> Any:
        return self._with_shares(super().form_edit_query(request))

    def _envelopes(self) -> list[Envelope]:
        with self.session_maker() as session:
            return list(session.scalars(select(Envelope).order_by(Envelope.sort_order, Envelope.id)))

    async def scaffold_form(self, rules: list[str] | None = None) -> type[Form]:
        envelopes = await anyio.to_thread.run_sync(self._envelopes)
        fields: dict[str, Any] = {
            "effective_from": DateField("Obowiązuje od", validators=[InputRequired()]),
        }
        for env in envelopes:
            fields[f"share_{env.id}"] = StringField(f"{env.name} (%)", validators=[InputRequired()])
        return type("AllocationPlanForm", (Form,), fields)

    async def get_form_data_for_edit(self, obj: Any) -> dict[str, Any]:
        data: dict[str, Any] = {"effective_from": obj.effective_from}
        for share in obj.shares:
            data[f"share_{share.envelope_id}"] = format_basis_points(share.basis_points).removesuffix("%")
        return data

    async def insert_model(self, request: Request, data: dict) -> Any:
        return await anyio.to_thread.run_sync(self._save_plan, None, data)

    async def update_model(self, request: Request, pk: str, data: dict) -> Any:
        return await anyio.to_thread.run_sync(self._save_plan, int(pk), data)

    def _save_plan(self, pk: int | None, data: dict) -> AllocationPlan:
        with self.session_maker(expire_on_commit=False) as session:
            envelopes = list(session.scalars(select(Envelope)))
            life = next(e.id for e in envelopes if e.is_life)
            shares = {e.id: parse_percent(str(data.get(f"share_{e.id}") or "")) for e in envelopes}
            validate_shares(shares, life)

            duplicate = session.scalar(
                select(AllocationPlan).where(
                    AllocationPlan.effective_from == data["effective_from"],
                    AllocationPlan.id != (pk or 0),
                )
            )
            if duplicate is not None:
                raise AllocationError("Plan obowiązujący od tej daty już istnieje.")

            plan = session.get(AllocationPlan, pk) if pk else AllocationPlan()
            if plan is None:
                raise AllocationError("Plan nie istnieje.")
            plan.effective_from = data["effective_from"]
            existing = {s.envelope_id: s for s in plan.shares}
            for envelope_id, bp in shares.items():
                if envelope_id in existing:
                    existing[envelope_id].basis_points = bp
                else:
                    plan.shares.append(AllocationShare(envelope_id=envelope_id, basis_points=bp))
            session.add(plan)
            session.commit()
            return plan


def setup_admin(app: FastAPI, engine: Engine, session_factory: sessionmaker[Session]) -> Admin:
    admin = Admin(app, engine=engine, session_maker=session_factory, base_url="/admin", title="FinBro – ustawienia")
    for view in (SettingsAdmin, EnvelopeAdmin, AllocationPlanAdmin, CategoryAdmin, RuleAdmin, DebtorAdmin):
        admin.add_view(view)
    return admin

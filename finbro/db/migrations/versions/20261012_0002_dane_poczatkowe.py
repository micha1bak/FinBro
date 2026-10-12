"""dane początkowe: konta, kategorie, koperty, plan podziału i reguły startowe

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-12 19:00:00

"""
from collections.abc import Sequence
from datetime import date

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0002"
down_revision: str | Sequence[str] | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SYSTEM_CATEGORY = "Gotówka (bez kategorii)"

CATEGORIES = [
    "Spożywcze",
    "Restauracje i na mieście",
    "Transport",
    "Mieszkanie",
    "Abonamenty i subskrypcje",
    "Zdrowie",
    "Ubrania",
    "Dom i wyposażenie",
    "Rozrywka i hobby",
    "Prezenty",
    "Edukacja",
    "Podróże",
    "Inne",
]

ENVELOPES = [
    # (kod, nazwa, czy Życie, kolejność, udział w punktach bazowych)
    ("zycie", "Życie", True, 10, 5000),
    ("xtb", "XTB", False, 20, 1250),
    ("obligacje", "Obligacje", False, 30, 1250),
    ("wakacje", "Wakacje", False, 40, 2500),
]

# Plan początkowy obowiązuje od dawna, żeby obejmował każdą datę startu.
INITIAL_PLAN_FROM = date(2000, 1, 1)

# Mniejsza liczba = wyższy priorytet. Warunki tekstowe porównujemy bez wielkości liter
# i polskich znaków; lista oznacza "którykolwiek z". Warunki to rdzenie słów, bo nazwy
# typów odmieniają się ("Wypłata w bankomacie", "wpłatomat").
RULES = [
    dict(
        name="Przelew z tytułem FinBro → ODKŁADANIE",
        priority=10,
        conditions={"direction": "OUT", "title": "FinBro"},
        result_type="ODKLADANIE",
        result_transfer_kind=None,
    ),
    dict(
        name="Wypłata z bankomatu → Portfel",
        priority=20,
        conditions={"direction": "OUT", "bank_type": "bankoma"},
        result_type="TRANSFER",
        result_transfer_kind="WALLET",
    ),
    dict(
        name="Wpłata gotówki na konto → z Portfela",
        priority=20,
        conditions={"direction": "IN", "bank_type": ["wpłatoma", "wpłata gotówk"]},
        result_type="TRANSFER",
        result_transfer_kind="WALLET",
    ),
    dict(
        name="Doładowanie Revoluta kartą → budżet rodzinny",
        priority=30,
        conditions={"direction": "OUT", "bank_type": "Przelew z karty", "merchant": "Revolut"},
        result_type="TRANSFER",
        result_transfer_kind="FAMILY",
    ),
]

account = sa.table(
    "account",
    sa.column("code", sa.String),
    sa.column("name", sa.String),
    sa.column("kind", sa.String),
    sa.column("opening_balance", sa.BigInteger),
)
category = sa.table(
    "category",
    sa.column("name", sa.String),
    sa.column("active", sa.Boolean),
    sa.column("is_system", sa.Boolean),
    sa.column("sort_order", sa.Integer),
)
envelope = sa.table(
    "envelope",
    sa.column("id", sa.Integer),
    sa.column("code", sa.String),
    sa.column("name", sa.String),
    sa.column("is_life", sa.Boolean),
    sa.column("sort_order", sa.Integer),
)
allocation_plan = sa.table("allocation_plan", sa.column("id", sa.Integer), sa.column("effective_from", sa.Date))
allocation_share = sa.table(
    "allocation_share",
    sa.column("plan_id", sa.Integer),
    sa.column("envelope_id", sa.Integer),
    sa.column("basis_points", sa.Integer),
)
rule = sa.table(
    "rule",
    sa.column("name", sa.String),
    sa.column("priority", sa.Integer),
    sa.column("active", sa.Boolean),
    sa.column("conditions", JSONB),
    sa.column("result_type", sa.String),
    sa.column("result_transfer_kind", sa.String),
)
app_settings = sa.table("app_settings", sa.column("id", sa.Integer))


def upgrade() -> None:
    op.bulk_insert(app_settings, [{"id": 1}])
    op.bulk_insert(
        account,
        [
            {"code": "pko", "name": "PKO BP (konto główne)", "kind": "BANK", "opening_balance": 0},
            {"code": "portfel", "name": "Portfel", "kind": "CASH", "opening_balance": 0},
        ],
    )
    op.bulk_insert(
        category,
        [
            {"name": name, "active": True, "is_system": False, "sort_order": (i + 1) * 10}
            for i, name in enumerate(CATEGORIES)
        ]
        + [{"name": SYSTEM_CATEGORY, "active": True, "is_system": True, "sort_order": 999}],
    )
    op.bulk_insert(
        envelope,
        [{"code": c, "name": n, "is_life": life, "sort_order": order} for c, n, life, order, _ in ENVELOPES],
    )

    conn = op.get_bind()
    plan_id = conn.execute(
        sa.insert(allocation_plan).values(effective_from=INITIAL_PLAN_FROM).returning(allocation_plan.c.id)
    ).scalar_one()
    envelope_ids = dict(conn.execute(sa.select(envelope.c.code, envelope.c.id)).all())
    op.bulk_insert(
        allocation_share,
        [{"plan_id": plan_id, "envelope_id": envelope_ids[c], "basis_points": bp} for c, _, _, _, bp in ENVELOPES],
    )
    op.bulk_insert(rule, [{**r, "active": True} for r in RULES])


def downgrade() -> None:
    op.execute(rule.delete().where(rule.c.name.in_([r["name"] for r in RULES])))
    # Udziały planu usuwa kaskada klucza obcego.
    op.execute(allocation_plan.delete().where(allocation_plan.c.effective_from == INITIAL_PLAN_FROM))
    op.execute(envelope.delete().where(envelope.c.code.in_([c for c, *_ in ENVELOPES])))
    op.execute(category.delete().where(category.c.name.in_([*CATEGORIES, SYSTEM_CATEGORY])))
    op.execute(account.delete().where(account.c.code.in_(["pko", "portfel"])))
    op.execute(app_settings.delete())

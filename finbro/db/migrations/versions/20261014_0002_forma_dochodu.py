"""Forma dochodu (PKO albo gotówka); istniejące dochody dostają PKO.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-14 13:55:11.832573

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = '0002'
down_revision: str | Sequence[str] | None = '0001'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('income', sa.Column('form', sa.String(length=10), server_default='PKO', nullable=False))
    op.create_check_constraint(op.f('ck_income_form'), 'income', "form IN ('PKO', 'GOTOWKA')")


def downgrade() -> None:
    op.drop_constraint(op.f('ck_income_form'), 'income', type_='check')
    op.drop_column('income', 'form')

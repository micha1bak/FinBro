"""Fundusz wakacyjny w majątku: rozszerzenie dozwolonych kont salda faktycznego.

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-06 12:00:00

"""
from collections.abc import Sequence

from alembic import op


revision: str = '0004'
down_revision: str | Sequence[str] | None = '0003'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(op.f('ck_balance_entry_account'), 'balance_entry', type_='check')
    op.create_check_constraint(
        op.f('ck_balance_entry_account'), 'balance_entry', "account IN ('PKO', 'GOTOWKA', 'WAKACJE', 'XTB', 'OBLIGACJE')"
    )


def downgrade() -> None:
    op.execute("DELETE FROM balance_entry WHERE account = 'WAKACJE'")
    op.drop_constraint(op.f('ck_balance_entry_account'), 'balance_entry', type_='check')
    op.create_check_constraint(
        op.f('ck_balance_entry_account'), 'balance_entry', "account IN ('PKO', 'GOTOWKA', 'XTB', 'OBLIGACJE')"
    )

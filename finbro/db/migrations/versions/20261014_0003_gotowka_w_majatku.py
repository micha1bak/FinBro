"""Konto Gotówka w majątku: rozszerzenie dozwolonych kont salda faktycznego.

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-14 15:00:00

"""
from collections.abc import Sequence

from alembic import op


revision: str = '0003'
down_revision: str | Sequence[str] | None = '0002'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(op.f('ck_balance_entry_account'), 'balance_entry', type_='check')
    op.create_check_constraint(
        op.f('ck_balance_entry_account'), 'balance_entry', "account IN ('PKO', 'GOTOWKA', 'XTB', 'OBLIGACJE')"
    )


def downgrade() -> None:
    op.execute("DELETE FROM balance_entry WHERE account = 'GOTOWKA'")
    op.drop_constraint(op.f('ck_balance_entry_account'), 'balance_entry', type_='check')
    op.create_check_constraint(op.f('ck_balance_entry_account'), 'balance_entry', "account IN ('PKO', 'XTB', 'OBLIGACJE')")

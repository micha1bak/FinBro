"""Schemat FinBro w wersji prostej i plan startowy 50/25/12,5/12,5.

Revision ID: 0001
Revises: 
Create Date: 2026-10-14 12:17:25.508422

"""
from collections.abc import Sequence
from datetime import date

import sqlalchemy as sa
from alembic import op


revision: str = '0001'
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

INITIAL_PLAN_FROM = date(2000, 1, 1)


def upgrade() -> None:
    op.create_table('allocation_plan',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('effective_from', sa.Date(), nullable=False),
    sa.Column('pko', sa.Integer(), nullable=False),
    sa.Column('wakacje', sa.Integer(), nullable=False),
    sa.Column('xtb', sa.Integer(), nullable=False),
    sa.Column('obligacje', sa.Integer(), nullable=False),
    sa.CheckConstraint('pko + wakacje + xtb + obligacje = 10000', name=op.f('ck_allocation_plan_shares_sum_100')),
    sa.CheckConstraint('pko >= 0 AND wakacje >= 0 AND xtb >= 0 AND obligacje >= 0', name=op.f('ck_allocation_plan_shares_non_negative')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_allocation_plan')),
    sa.UniqueConstraint('effective_from', name=op.f('uq_allocation_plan_effective_from'))
    )
    op.create_table('balance_entry',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('account', sa.String(length=20), nullable=False),
    sa.Column('date', sa.Date(), nullable=False),
    sa.Column('amount', sa.BigInteger(), nullable=False),
    sa.CheckConstraint("account IN ('PKO', 'XTB', 'OBLIGACJE')", name=op.f('ck_balance_entry_account')),
    sa.CheckConstraint('amount >= 0', name=op.f('ck_balance_entry_amount_non_negative')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_balance_entry')),
    sa.UniqueConstraint('account', 'date', name=op.f('uq_balance_entry_account_date'))
    )
    op.create_table('envelope_account',
    sa.Column('envelope', sa.String(length=20), nullable=False),
    sa.Column('target_account', sa.String(length=64), nullable=False),
    sa.CheckConstraint("envelope IN ('WAKACJE', 'XTB', 'OBLIGACJE')", name=op.f('ck_envelope_account_envelope')),
    sa.PrimaryKeyConstraint('envelope', name=op.f('pk_envelope_account'))
    )
    op.create_table('settlement',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('date', sa.Date(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_settlement'))
    )
    op.create_table('income',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('date', sa.Date(), nullable=False),
    sa.Column('source', sa.String(length=200), nullable=False),
    sa.Column('amount', sa.BigInteger(), nullable=False),
    sa.Column('settlement_id', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('amount > 0', name=op.f('ck_income_amount_positive')),
    sa.CheckConstraint('length(trim(source)) > 0', name=op.f('ck_income_source_not_empty')),
    sa.ForeignKeyConstraint(['settlement_id'], ['settlement.id'], name=op.f('fk_income_settlement_id_settlement'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_income'))
    )
    op.create_index(op.f('ix_income_date'), 'income', ['date'], unique=False)
    op.create_index(op.f('ix_income_settlement_id'), 'income', ['settlement_id'], unique=False)
    op.create_table('settlement_line',
    sa.Column('settlement_id', sa.Integer(), nullable=False),
    sa.Column('envelope', sa.String(length=20), nullable=False),
    sa.Column('amount', sa.BigInteger(), nullable=False),
    sa.CheckConstraint("envelope IN ('WAKACJE', 'XTB', 'OBLIGACJE')", name=op.f('ck_settlement_line_envelope')),
    sa.CheckConstraint('amount > 0', name=op.f('ck_settlement_line_amount_positive')),
    sa.ForeignKeyConstraint(['settlement_id'], ['settlement.id'], name=op.f('fk_settlement_line_settlement_id_settlement'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('settlement_id', 'envelope', name=op.f('pk_settlement_line'))
    )
    op.create_table('income_share',
    sa.Column('income_id', sa.Integer(), nullable=False),
    sa.Column('envelope', sa.String(length=20), nullable=False),
    sa.Column('settlement_id', sa.Integer(), nullable=False),
    sa.Column('amount', sa.BigInteger(), nullable=False),
    sa.CheckConstraint("envelope IN ('PKO', 'WAKACJE', 'XTB', 'OBLIGACJE')", name=op.f('ck_income_share_envelope')),
    sa.ForeignKeyConstraint(['income_id'], ['income.id'], name=op.f('fk_income_share_income_id_income'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['settlement_id'], ['settlement.id'], name=op.f('fk_income_share_settlement_id_settlement'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('income_id', 'envelope', name=op.f('pk_income_share'))
    )
    op.create_index(op.f('ix_income_share_settlement_id'), 'income_share', ['settlement_id'], unique=False)

    # Plan startowy obowiązuje od dawna, żeby obejmował każdy wpisany dochód.
    plan = sa.table(
        'allocation_plan',
        sa.column('effective_from', sa.Date()),
        sa.column('pko', sa.Integer()),
        sa.column('wakacje', sa.Integer()),
        sa.column('xtb', sa.Integer()),
        sa.column('obligacje', sa.Integer()),
    )
    op.bulk_insert(plan, [{'effective_from': INITIAL_PLAN_FROM, 'pko': 5000, 'wakacje': 2500, 'xtb': 1250, 'obligacje': 1250}])


def downgrade() -> None:
    op.drop_index(op.f('ix_income_share_settlement_id'), table_name='income_share')
    op.drop_table('income_share')
    op.drop_table('settlement_line')
    op.drop_index(op.f('ix_income_settlement_id'), table_name='income')
    op.drop_index(op.f('ix_income_date'), table_name='income')
    op.drop_table('income')
    op.drop_table('settlement')
    op.drop_table('envelope_account')
    op.drop_table('balance_entry')
    op.drop_table('allocation_plan')

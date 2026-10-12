"""schemat początkowy

Revision ID: 0001
Revises: 
Create Date: 2026-10-12 18:31:20.927718

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = '0001'
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('account',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('code', sa.String(length=20), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('kind', sa.Enum('BANK', 'CASH', name='account_kind', native_enum=False, create_constraint=False, length=20), nullable=False),
    sa.Column('opening_balance', sa.BigInteger(), server_default='0', nullable=False),
    sa.Column('opening_date', sa.Date(), nullable=True),
    sa.CheckConstraint("kind IN ('BANK', 'CASH')", name=op.f('ck_account_account_kind')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_account')),
    sa.UniqueConstraint('code', name=op.f('uq_account_code'))
    )
    op.create_table('allocation_plan',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('effective_from', sa.Date(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_allocation_plan')),
    sa.UniqueConstraint('effective_from', name=op.f('uq_allocation_plan_effective_from'))
    )
    op.create_table('app_settings',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('start_date', sa.Date(), nullable=True),
    sa.Column('main_account_number', sa.String(length=64), nullable=True),
    sa.Column('llm_model', sa.String(length=200), nullable=True),
    sa.CheckConstraint('id = 1', name=op.f('ck_app_settings_single_row')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_app_settings'))
    )
    op.create_table('category',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
    sa.Column('is_system', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.Column('sort_order', sa.Integer(), server_default='100', nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_category')),
    sa.UniqueConstraint('name', name=op.f('uq_category_name'))
    )
    op.create_table('debtor',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('aliases', sa.Text(), nullable=True),
    sa.Column('note', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_debtor')),
    sa.UniqueConstraint('name', name=op.f('uq_debtor_name'))
    )
    op.create_table('envelope',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('code', sa.String(length=20), nullable=False),
    sa.Column('name', sa.String(length=50), nullable=False),
    sa.Column('target_account', sa.String(length=64), nullable=True),
    sa.Column('is_life', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.Column('sort_order', sa.Integer(), server_default='100', nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_envelope')),
    sa.UniqueConstraint('code', name=op.f('uq_envelope_code')),
    sa.UniqueConstraint('name', name=op.f('uq_envelope_name'))
    )
    op.create_index('uq_envelope_single_life', 'envelope', ['is_life'], unique=True, postgresql_where=sa.text('is_life'))
    op.create_table('settlement',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('week_start', sa.Date(), nullable=False),
    sa.Column('status', sa.Enum('OPEN', 'CLOSED', 'SETTLED', name='settlement_status', native_enum=False, create_constraint=False, length=20), nullable=False),
    sa.Column('closed_at', sa.DateTime(timezone=True), nullable=True),
    sa.CheckConstraint("status IN ('OPEN', 'CLOSED', 'SETTLED')", name=op.f('ck_settlement_settlement_status')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_settlement')),
    sa.UniqueConstraint('week_start', name=op.f('uq_settlement_week_start'))
    )
    op.create_table('allocation_share',
    sa.Column('plan_id', sa.Integer(), nullable=False),
    sa.Column('envelope_id', sa.Integer(), nullable=False),
    sa.Column('basis_points', sa.Integer(), nullable=False),
    sa.CheckConstraint('basis_points BETWEEN 0 AND 10000', name=op.f('ck_allocation_share_basis_points_range')),
    sa.ForeignKeyConstraint(['envelope_id'], ['envelope.id'], name=op.f('fk_allocation_share_envelope_id_envelope')),
    sa.ForeignKeyConstraint(['plan_id'], ['allocation_plan.id'], name=op.f('fk_allocation_share_plan_id_allocation_plan'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('plan_id', 'envelope_id', name=op.f('pk_allocation_share'))
    )
    op.create_table('import_batch',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('account_id', sa.Integer(), nullable=False),
    sa.Column('filename', sa.String(length=255), nullable=True),
    sa.Column('date_from', sa.Date(), nullable=False),
    sa.Column('date_to', sa.Date(), nullable=False),
    sa.Column('new_count', sa.Integer(), nullable=False),
    sa.Column('existing_count', sa.Integer(), nullable=False),
    sa.Column('skipped_count', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['account_id'], ['account.id'], name=op.f('fk_import_batch_account_id_account')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_import_batch'))
    )
    op.create_table('rule',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('priority', sa.Integer(), server_default='100', nullable=False),
    sa.Column('active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
    sa.Column('conditions', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
    sa.Column('result_type', sa.Enum('DOCHOD', 'WYDATEK', 'ODKLADANIE', 'TRANSFER', 'ZWROT', 'ROZLICZENIE', 'POZYCZKA', 'SPLATA', name='rule_result_type', native_enum=False, create_constraint=False, length=20), nullable=False),
    sa.Column('result_category_id', sa.Integer(), nullable=True),
    sa.Column('result_debtor_id', sa.Integer(), nullable=True),
    sa.Column('result_transfer_kind', sa.Enum('WALLET', 'FAMILY', 'OTHER', name='rule_result_transfer_kind', native_enum=False, create_constraint=False, length=20), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("result_transfer_kind IN ('WALLET', 'FAMILY', 'OTHER')", name=op.f('ck_rule_rule_result_transfer_kind')),
    sa.CheckConstraint("result_type IN ('DOCHOD', 'WYDATEK', 'ODKLADANIE', 'TRANSFER', 'ZWROT', 'ROZLICZENIE', 'POZYCZKA', 'SPLATA')", name=op.f('ck_rule_rule_result_type')),
    sa.ForeignKeyConstraint(['result_category_id'], ['category.id'], name=op.f('fk_rule_result_category_id_category')),
    sa.ForeignKeyConstraint(['result_debtor_id'], ['debtor.id'], name=op.f('fk_rule_result_debtor_id_debtor')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_rule'))
    )
    op.create_table('settlement_line',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('settlement_id', sa.Integer(), nullable=False),
    sa.Column('envelope_id', sa.Integer(), nullable=False),
    sa.Column('due', sa.BigInteger(), nullable=False),
    sa.Column('corrections', sa.BigInteger(), nullable=False),
    sa.Column('carryover', sa.BigInteger(), nullable=False),
    sa.Column('to_transfer', sa.BigInteger(), nullable=False),
    sa.ForeignKeyConstraint(['envelope_id'], ['envelope.id'], name=op.f('fk_settlement_line_envelope_id_envelope')),
    sa.ForeignKeyConstraint(['settlement_id'], ['settlement.id'], name=op.f('fk_settlement_line_settlement_id_settlement'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_settlement_line')),
    sa.UniqueConstraint('settlement_id', 'envelope_id', name=op.f('uq_settlement_line_settlement_id_envelope_id'))
    )
    op.create_table('transaction',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('account_id', sa.Integer(), nullable=True),
    sa.Column('source', sa.Enum('IMPORT', 'MANUAL', 'INVENTORY', 'FORGIVENESS', name='tx_source', native_enum=False, create_constraint=False, length=20), nullable=False),
    sa.Column('transaction_date', sa.Date(), nullable=False),
    sa.Column('booking_date', sa.Date(), nullable=True),
    sa.Column('amount', sa.BigInteger(), nullable=False),
    sa.Column('balance_after', sa.BigInteger(), nullable=True),
    sa.Column('occurrence', sa.Integer(), nullable=True),
    sa.Column('bank_type', sa.String(length=200), nullable=True),
    sa.Column('raw_description', sa.Text(), nullable=True),
    sa.Column('counterparty_name', sa.String(length=300), nullable=True),
    sa.Column('counterparty_account', sa.String(length=64), nullable=True),
    sa.Column('counterparty_address', sa.String(length=300), nullable=True),
    sa.Column('title', sa.Text(), nullable=True),
    sa.Column('merchant', sa.String(length=300), nullable=True),
    sa.Column('city', sa.String(length=100), nullable=True),
    sa.Column('country', sa.String(length=100), nullable=True),
    sa.Column('reference_number', sa.String(length=100), nullable=True),
    sa.Column('extra', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
    sa.Column('note', sa.Text(), nullable=True),
    sa.Column('import_batch_id', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("source IN ('IMPORT', 'MANUAL', 'INVENTORY', 'FORGIVENESS')", name=op.f('ck_transaction_tx_source')),
    sa.CheckConstraint('amount <> 0', name=op.f('ck_transaction_amount_not_zero')),
    sa.ForeignKeyConstraint(['account_id'], ['account.id'], name=op.f('fk_transaction_account_id_account')),
    sa.ForeignKeyConstraint(['import_batch_id'], ['import_batch.id'], name=op.f('fk_transaction_import_batch_id_import_batch')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_transaction')),
    sa.UniqueConstraint('account_id', 'booking_date', 'amount', 'balance_after', 'occurrence', name='uq_transaction_fingerprint')
    )
    op.create_index('ix_transaction_transaction_date', 'transaction', ['transaction_date'], unique=False)
    op.create_table('classification',
    sa.Column('transaction_id', sa.Integer(), nullable=False),
    sa.Column('type', sa.Enum('DOCHOD', 'WYDATEK', 'ODKLADANIE', 'TRANSFER', 'ZWROT', 'ROZLICZENIE', 'POZYCZKA', 'SPLATA', name='classification_type', native_enum=False, create_constraint=False, length=20), nullable=True),
    sa.Column('category_id', sa.Integer(), nullable=True),
    sa.Column('debtor_id', sa.Integer(), nullable=True),
    sa.Column('transfer_kind', sa.Enum('WALLET', 'FAMILY', 'OTHER', name='classification_transfer_kind', native_enum=False, create_constraint=False, length=20), nullable=True),
    sa.Column('envelope_id', sa.Integer(), nullable=True),
    sa.Column('source', sa.Enum('RULE', 'HISTORY', 'LLM', 'USER', 'SYSTEM', name='proposal_source', native_enum=False, create_constraint=False, length=20), nullable=True),
    sa.Column('rule_id', sa.Integer(), nullable=True),
    sa.Column('reason', sa.Text(), nullable=True),
    sa.Column('confirmed', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.Column('confirmed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('settlement_week', sa.Date(), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("source IN ('RULE', 'HISTORY', 'LLM', 'USER', 'SYSTEM')", name=op.f('ck_classification_proposal_source')),
    sa.CheckConstraint("transfer_kind IN ('WALLET', 'FAMILY', 'OTHER')", name=op.f('ck_classification_classification_transfer_kind')),
    sa.CheckConstraint("type IN ('DOCHOD', 'WYDATEK', 'ODKLADANIE', 'TRANSFER', 'ZWROT', 'ROZLICZENIE', 'POZYCZKA', 'SPLATA')", name=op.f('ck_classification_classification_type')),
    sa.CheckConstraint('NOT confirmed OR type IS NOT NULL', name=op.f('ck_classification_confirmed_has_type')),
    sa.ForeignKeyConstraint(['category_id'], ['category.id'], name=op.f('fk_classification_category_id_category')),
    sa.ForeignKeyConstraint(['debtor_id'], ['debtor.id'], name=op.f('fk_classification_debtor_id_debtor')),
    sa.ForeignKeyConstraint(['envelope_id'], ['envelope.id'], name=op.f('fk_classification_envelope_id_envelope')),
    sa.ForeignKeyConstraint(['rule_id'], ['rule.id'], name=op.f('fk_classification_rule_id_rule'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['transaction_id'], ['transaction.id'], name=op.f('fk_classification_transaction_id_transaction'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('transaction_id', name=op.f('pk_classification'))
    )
    op.create_index('ix_classification_settlement_week', 'classification', ['settlement_week'], unique=False)
    op.create_table('llm_job',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('transaction_id', sa.Integer(), nullable=False),
    sa.Column('status', sa.Enum('PENDING', 'RUNNING', 'DONE', 'FAILED', name='llm_job_status', native_enum=False, create_constraint=False, length=20), nullable=False),
    sa.Column('attempts', sa.Integer(), server_default='0', nullable=False),
    sa.Column('last_error', sa.Text(), nullable=True),
    sa.Column('next_attempt_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("status IN ('PENDING', 'RUNNING', 'DONE', 'FAILED')", name=op.f('ck_llm_job_llm_job_status')),
    sa.ForeignKeyConstraint(['transaction_id'], ['transaction.id'], name=op.f('fk_llm_job_transaction_id_transaction'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_llm_job')),
    sa.UniqueConstraint('transaction_id', name=op.f('uq_llm_job_transaction_id'))
    )
    op.create_table('settlement_adjustment',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('week_start', sa.Date(), nullable=False),
    sa.Column('transaction_id', sa.Integer(), nullable=False),
    sa.Column('amount', sa.BigInteger(), nullable=False),
    sa.Column('income_date', sa.Date(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['transaction_id'], ['transaction.id'], name=op.f('fk_settlement_adjustment_transaction_id_transaction'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_settlement_adjustment'))
    )
    op.create_index(op.f('ix_settlement_adjustment_week_start'), 'settlement_adjustment', ['week_start'], unique=False)
    op.create_table('settlement_payment',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('settlement_line_id', sa.Integer(), nullable=False),
    sa.Column('transaction_id', sa.Integer(), nullable=False),
    sa.Column('amount', sa.BigInteger(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['settlement_line_id'], ['settlement_line.id'], name=op.f('fk_settlement_payment_settlement_line_id_settlement_line'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['transaction_id'], ['transaction.id'], name=op.f('fk_settlement_payment_transaction_id_transaction'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_settlement_payment')),
    sa.UniqueConstraint('transaction_id', name=op.f('uq_settlement_payment_transaction_id'))
    )
    op.create_table('wallet_inventory',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('inventory_date', sa.Date(), nullable=False),
    sa.Column('actual', sa.BigInteger(), nullable=False),
    sa.Column('expected', sa.BigInteger(), nullable=False),
    sa.Column('transaction_id', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['transaction_id'], ['transaction.id'], name=op.f('fk_wallet_inventory_transaction_id_transaction'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_wallet_inventory'))
    )
    op.create_index(op.f('ix_wallet_inventory_inventory_date'), 'wallet_inventory', ['inventory_date'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_wallet_inventory_inventory_date'), table_name='wallet_inventory')
    op.drop_table('wallet_inventory')
    op.drop_table('settlement_payment')
    op.drop_index(op.f('ix_settlement_adjustment_week_start'), table_name='settlement_adjustment')
    op.drop_table('settlement_adjustment')
    op.drop_table('llm_job')
    op.drop_index('ix_classification_settlement_week', table_name='classification')
    op.drop_table('classification')
    op.drop_index('ix_transaction_transaction_date', table_name='transaction')
    op.drop_table('transaction')
    op.drop_table('settlement_line')
    op.drop_table('rule')
    op.drop_table('import_batch')
    op.drop_table('allocation_share')
    op.drop_table('settlement')
    op.drop_index('uq_envelope_single_life', table_name='envelope', postgresql_where=sa.text('is_life'))
    op.drop_table('envelope')
    op.drop_table('debtor')
    op.drop_table('category')
    op.drop_table('app_settings')
    op.drop_table('allocation_plan')
    op.drop_table('account')

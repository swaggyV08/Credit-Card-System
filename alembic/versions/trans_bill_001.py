"""create transaction and billing tables

Revision ID: trans_bill_001
Revises: 
Create Date: 2026-03-23 11:45:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'trans_bill_001'
down_revision = None # Adjust based on existing head
branch_labels = None
depends_on = None

def upgrade():
    # 1. New Tables: billing_statements
    op.create_table(
        'billing_statements',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('credit_account_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('statement_period_start', sa.DateTime(timezone=True), nullable=False),
        sa.Column('statement_period_end', sa.DateTime(timezone=True), nullable=False),
        sa.Column('statement_date', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column('due_date', sa.DateTime(timezone=True), nullable=False),
        sa.Column('opening_balance', sa.Numeric(15, 2), nullable=True),
        sa.Column('total_purchases', sa.Numeric(15, 2), nullable=True),
        sa.Column('total_cash_advances', sa.Numeric(15, 2), nullable=True),
        sa.Column('total_payments', sa.Numeric(15, 2), nullable=True),
        sa.Column('total_credits', sa.Numeric(15, 2), nullable=True),
        sa.Column('interest_charged', sa.Numeric(15, 2), nullable=True),
        sa.Column('fees_charged', sa.Numeric(15, 2), nullable=True),
        sa.Column('closing_balance', sa.Numeric(15, 2), nullable=True),
        sa.Column('minimum_amount_due', sa.Numeric(15, 2), nullable=True),
        sa.Column('is_fully_paid', sa.Boolean(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(['credit_account_id'], ['ccm_credit_accounts.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

    # 2. New Table: rewards_ledger
    op.create_table(
        'rewards_ledger',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('credit_account_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('transaction_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('points_earned', sa.Numeric(15, 2), nullable=True),
        sa.Column('points_redeemed', sa.Numeric(15, 2), nullable=True),
        sa.Column('points_reversed', sa.Numeric(15, 2), nullable=True),
        sa.Column('description', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(['credit_account_id'], ['ccm_credit_accounts.id'], ),
        sa.ForeignKeyConstraint(['transaction_id'], ['ccm_card_transactions.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

    # 3. Add columns to existing tables
    op.add_column('ccm_card_transactions', sa.Column('idempotency_key', sa.String(), nullable=True))
    op.create_unique_constraint('uq_transaction_idempotency', 'ccm_card_transactions', ['idempotency_key'])
    op.add_column('ccm_card_transactions', sa.Column('reference_id', sa.String(), nullable=True))
    op.add_column('ccm_card_transactions', sa.Column('settlement_date', sa.DateTime(timezone=True), nullable=True))
    
    op.add_column('ccm_credit_accounts', sa.Column('version', sa.Integer(), server_default='1', nullable=False))

def downgrade():
    op.drop_column('ccm_credit_accounts', 'version')
    op.drop_column('ccm_card_transactions', 'settlement_date')
    op.drop_column('ccm_card_transactions', 'reference_id')
    op.drop_constraint('uq_transaction_idempotency', 'ccm_card_transactions', type_='unique')
    op.drop_column('ccm_card_transactions', 'idempotency_key')
    op.drop_table('rewards_ledger')
    op.drop_table('billing_statements')

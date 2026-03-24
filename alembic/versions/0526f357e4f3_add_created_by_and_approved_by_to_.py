"""add created_by and approved_by to credit_account

Revision ID: 0526f357e4f3
Revises: 75f26e65dd5c
Create Date: 2026-03-05 10:49:51.428045

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '0526f357e4f3'
down_revision: Union[str, Sequence[str], None] = '75f26e65dd5c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('credit_account', sa.Column('created_by', postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column('credit_account', sa.Column('approved_by', postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key('fk_credit_account_created_by_admins', 'credit_account', 'admins', ['created_by'], ['id'])
    op.create_foreign_key('fk_credit_account_approved_by_admins', 'credit_account', 'admins', ['approved_by'], ['id'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('fk_credit_account_approved_by_admins', 'credit_account', type_='foreignkey')
    op.drop_constraint('fk_credit_account_created_by_admins', 'credit_account', type_='foreignkey')
    op.drop_column('credit_account', 'approved_by')
    op.drop_column('credit_account', 'created_by')

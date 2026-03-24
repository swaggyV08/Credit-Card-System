"""add application_id to credit_account

Revision ID: 9a6429095aa2
Revises: 0f663910d6ac
Create Date: 2026-03-05 11:50:06.059470

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9a6429095aa2'
down_revision: Union[str, Sequence[str], None] = '0f663910d6ac'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('credit_account', sa.Column('application_id', sa.UUID(), nullable=True))
    op.create_foreign_key('fk_credit_account_application', 'credit_account', 'credit_card_application', ['application_id'], ['id'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('fk_credit_account_application', 'credit_account', type_='foreignkey')
    op.drop_column('credit_account', 'application_id')

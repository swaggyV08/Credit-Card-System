"""add card_product_id to credit_account

Revision ID: 0f663910d6ac
Revises: d4b560b8162f
Create Date: 2026-03-05 11:48:04.060413

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0f663910d6ac'
down_revision: Union[str, Sequence[str], None] = 'd4b560b8162f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('credit_account', sa.Column('card_product_id', sa.UUID(), nullable=True))
    # Make it nullable for now, or add a default/link later if needed. 
    # But since it's a new system, we can assume new ones will have it.
    # For safety with existing data, nullable=True then update then nullable=False.
    # But since it's a dev system, nullable=False with foreign key is fine if no data or if we can truncate.
    # User requested it to be generated at approval.
    op.create_foreign_key('fk_credit_account_card_product', 'credit_account', 'card_product_core', ['card_product_id'], ['id'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('fk_credit_account_card_product', 'credit_account', type_='foreignkey')
    op.drop_column('credit_account', 'card_product_id')

"""add rejection_reason to credit_card_application

Revision ID: d4b560b8162f
Revises: c5a0e3d93659
Create Date: 2026-03-05 11:46:37.165418

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd4b560b8162f'
down_revision: Union[str, Sequence[str], None] = 'c5a0e3d93659'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('credit_card_application', sa.Column('rejection_reason', sa.String(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('credit_card_application', 'rejection_reason')

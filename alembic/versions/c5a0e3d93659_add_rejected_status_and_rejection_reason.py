"""add rejected status and rejection_reason

Revision ID: c5a0e3d93659
Revises: 0526f357e4f3
Create Date: 2026-03-05 11:15:41.716851

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c5a0e3d93659'
down_revision: Union[str, Sequence[str], None] = '0526f357e4f3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('credit_product_governance', sa.Column('rejection_reason', sa.String(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('credit_product_governance', 'rejection_reason')

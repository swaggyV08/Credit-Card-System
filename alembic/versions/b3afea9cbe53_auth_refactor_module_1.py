"""auth_refactor_module_1

Revision ID: b3afea9cbe53
Revises: 28de87878dc9
Create Date: 2026-04-06 14:02:30.526862

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b3afea9cbe53'
down_revision: Union[str, Sequence[str], None] = '28de87878dc9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add full_name column to users
    op.add_column('users', sa.Column('full_name', sa.String(), nullable=True))
    
    # Backfill full_name from customer_profiles
    op.execute("""
        UPDATE users
        SET full_name = (
            SELECT COALESCE(first_name, '') || ' ' || COALESCE(last_name, '')
            FROM customer_profiles
            WHERE customer_profiles.user_id = users.id
        )
    """)
    
    # Trim the resulting string
    op.execute("UPDATE users SET full_name = TRIM(full_name)")
    
    # Change SUPER_ADMIN to SUPERADMIN in admins table
    op.execute("UPDATE admins SET role = 'SUPERADMIN' WHERE role = 'SUPER_ADMIN'")


def downgrade() -> None:
    # Revert SUPERADMIN to SUPER_ADMIN
    op.execute("UPDATE admins SET role = 'SUPER_ADMIN' WHERE role = 'SUPERADMIN'")
    
    # Drop full_name column
    op.drop_column('users', 'full_name')

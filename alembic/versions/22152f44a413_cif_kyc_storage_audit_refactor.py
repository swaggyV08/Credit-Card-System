"""cif_kyc_storage_audit_refactor

Revision ID: 22152f44a413
Revises: b3afea9cbe53
Create Date: 2026-04-06 14:14:04.759076

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '22152f44a413'
down_revision: Union[str, Sequence[str], None] = 'b3afea9cbe53'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Update kyc_document_submissions: replace file_content (bytea) with storage_path (string)
    op.add_column('kyc_document_submissions', sa.Column('storage_path', sa.String(), nullable=True))
    op.drop_column('kyc_document_submissions', 'file_content')

    # 2. Add auditing fields to child models
    for table_name in ['customer_addresses', 'employment_details', 'financial_information', 'fatca_declarations']:
        op.add_column(table_name, sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True))
        op.add_column(table_name, sa.Column('updated_by', sa.String(), nullable=True))


def downgrade() -> None:
    # Revert child model audit fields
    for table_name in ['customer_addresses', 'employment_details', 'financial_information', 'fatca_declarations']:
        op.drop_column(table_name, 'updated_by')
        op.drop_column(table_name, 'updated_at')

    # Revert kyc_document_submissions
    op.add_column('kyc_document_submissions', sa.Column('file_content', sa.LargeBinary(), nullable=True))
    op.drop_column('kyc_document_submissions', 'storage_path')

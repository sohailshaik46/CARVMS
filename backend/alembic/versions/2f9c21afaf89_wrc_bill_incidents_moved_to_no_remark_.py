"""wrc bill incidents moved_to_no_remark column

Revision ID: 2f9c21afaf89
Revises: cbcd5d2613fa
Create Date: 2026-08-13 22:51:35.502001

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2f9c21afaf89'
down_revision: Union[str, Sequence[str], None] = 'cbcd5d2613fa'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Adds moved_to_no_remark to weekly_revenue_bill_incidents -- a plain
    column add, no CHECK constraints touched, so a simple add_column is
    safe on SQLite (no batch_alter_table/table-recreate needed)."""
    op.add_column(
        "weekly_revenue_bill_incidents",
        sa.Column("moved_to_no_remark", sa.Boolean(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("weekly_revenue_bill_incidents", "moved_to_no_remark")

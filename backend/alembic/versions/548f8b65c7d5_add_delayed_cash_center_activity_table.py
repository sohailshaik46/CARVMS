"""add delayed cash center activity table

Revision ID: 548f8b65c7d5
Revises: 2f9c21afaf89
Create Date: 2026-08-14 11:36:50.779251

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '548f8b65c7d5'
down_revision: Union[str, Sequence[str], None] = '2f9c21afaf89'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """A fresh CREATE TABLE -- no existing table altered, so this is safe
    on SQLite without batch_alter_table."""
    op.create_table(
        "delayed_cash_center_activity",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("centre_code", sa.String(), nullable=False),
        sa.Column("centre_name", sa.String(), nullable=True),
        sa.Column("center_penalty_id", sa.Integer(), nullable=True),
        sa.Column("event_type", sa.String(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.CheckConstraint("event_type IN ('opened', 'submitted')", name="ck_dcb_activity_event_type_valid"),
        sa.ForeignKeyConstraint(["center_penalty_id"], ["delayed_cash_center_penalties.id"], name="fk_dcb_activity_center_penalty_id"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_delayed_cash_center_activity_centre_code"), "delayed_cash_center_activity", ["centre_code"])
    op.create_index(op.f("ix_delayed_cash_center_activity_center_penalty_id"), "delayed_cash_center_activity", ["center_penalty_id"])
    op.create_index(op.f("ix_delayed_cash_center_activity_id"), "delayed_cash_center_activity", ["id"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("delayed_cash_center_activity")

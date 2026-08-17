"""add half country manager role and dimension

Adds the top level of the confirmed real management chain:
Half Country Manager -> Zonal Manager -> Cluster Manager -> Center Manager.

Revision ID: ed77aceda547
Revises: efac288eda81
Create Date: 2026-08-13 17:09:55.915613

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ed77aceda547'
down_revision: Union[str, Sequence[str], None] = 'efac288eda81'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Shift the existing default dimensions down one to make room for the
    # new top level, then insert it -- matches the updated DEFAULT_DIMENSIONS
    # list in org_service.py (half_country=1, zone=2, cluster=3,
    # zonal_manager=4, center=5, employee=6).
    op.execute("UPDATE org_dimensions SET sort_order = 2 WHERE key = 'zone'")
    op.execute("UPDATE org_dimensions SET sort_order = 3 WHERE key = 'cluster'")
    op.execute("UPDATE org_dimensions SET sort_order = 4 WHERE key = 'zonal_manager'")
    op.execute("UPDATE org_dimensions SET sort_order = 5 WHERE key = 'center'")
    op.execute("UPDATE org_dimensions SET sort_order = 6 WHERE key = 'employee'")

    org_dimensions = sa.table(
        "org_dimensions",
        sa.column("key", sa.String),
        sa.column("label", sa.String),
        sa.column("sort_order", sa.Integer),
    )
    op.bulk_insert(
        org_dimensions,
        [{"key": "half_country", "label": "Half Country", "sort_order": 1}],
    )

    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_constraint('ck_users_role_valid', type_='check')
        batch_op.create_check_constraint(
            'ck_users_role_valid',
            "role IN ('Admin', 'Auditor', 'Finance', 'Center Manager', 'Cluster Manager', "
            "'Zonal Manager', 'Half Country Manager')",
        )


def downgrade() -> None:
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_constraint('ck_users_role_valid', type_='check')
        batch_op.create_check_constraint(
            'ck_users_role_valid',
            "role IN ('Admin', 'Auditor', 'Finance', 'Center Manager', 'Cluster Manager', 'Zonal Manager')",
        )

    op.execute(
        "DELETE FROM org_dimensions WHERE key = 'half_country' "
        "AND id NOT IN (SELECT DISTINCT dimension_id FROM org_nodes)"
    )
    op.execute("UPDATE org_dimensions SET sort_order = 1 WHERE key = 'zone'")
    op.execute("UPDATE org_dimensions SET sort_order = 2 WHERE key = 'cluster'")
    op.execute("UPDATE org_dimensions SET sort_order = 3 WHERE key = 'zonal_manager'")
    op.execute("UPDATE org_dimensions SET sort_order = 4 WHERE key = 'center'")
    op.execute("UPDATE org_dimensions SET sort_order = 5 WHERE key = 'employee'")

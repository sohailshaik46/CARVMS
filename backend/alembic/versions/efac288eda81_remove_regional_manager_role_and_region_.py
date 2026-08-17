"""remove regional manager role and region dimension

Regional Manager and the Region/Regional Manager org dimensions are removed
entirely -- the organization confirmed it has no Region level. Verified
before writing this migration that the live carvms.db has zero users with
role='Regional Manager' and zero org_nodes under the region/regional_manager
dimensions, so this is a clean removal with no orphaned rows and no role
reassignment needed (see chat: explicit user confirmation + a live DB check
prior to this migration).

Revision ID: efac288eda81
Revises: 229c43152f64
Create Date: 2026-08-13 17:07:00.032028

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'efac288eda81'
down_revision: Union[str, Sequence[str], None] = '229c43152f64'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Data: drop the region / regional_manager dimension rows. Safety-net
    # WHERE clauses (no nodes under them) even though this was independently
    # verified beforehand -- if that ever stops being true, this simply
    # deletes nothing rather than orphaning nodes.
    op.execute(
        "DELETE FROM org_dimensions WHERE key IN ('region', 'regional_manager') "
        "AND id NOT IN (SELECT DISTINCT dimension_id FROM org_nodes)"
    )
    # Renumber the remaining default dimensions to close the gap left by
    # the two deleted rows, matching the updated DEFAULT_DIMENSIONS list in
    # org_service.py (zone=1, cluster=2, zonal_manager=3, center=4, employee=5).
    op.execute("UPDATE org_dimensions SET sort_order = 3 WHERE key = 'zonal_manager'")
    op.execute("UPDATE org_dimensions SET sort_order = 4 WHERE key = 'center'")
    op.execute("UPDATE org_dimensions SET sort_order = 5 WHERE key = 'employee'")

    # Schema: tighten the users.role CHECK constraint. SQLite requires
    # recreating the table to alter a CHECK -- batch mode, named constraint
    # (see e0c78f322c92 for why an unnamed one here would break batch mode).
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_constraint('ck_users_role_valid', type_='check')
        batch_op.create_check_constraint(
            'ck_users_role_valid',
            "role IN ('Admin', 'Auditor', 'Finance', 'Center Manager', 'Cluster Manager', 'Zonal Manager')",
        )


def downgrade() -> None:
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_constraint('ck_users_role_valid', type_='check')
        batch_op.create_check_constraint(
            'ck_users_role_valid',
            "role IN ('Admin', 'Auditor', 'Finance', 'Center Manager', 'Cluster Manager', "
            "'Regional Manager', 'Zonal Manager')",
        )

    op.execute("UPDATE org_dimensions SET sort_order = 4 WHERE key = 'zonal_manager'")
    op.execute("UPDATE org_dimensions SET sort_order = 6 WHERE key = 'center'")
    op.execute("UPDATE org_dimensions SET sort_order = 7 WHERE key = 'employee'")

    org_dimensions = sa.table(
        "org_dimensions",
        sa.column("key", sa.String),
        sa.column("label", sa.String),
        sa.column("sort_order", sa.Integer),
    )
    op.bulk_insert(
        org_dimensions,
        [
            {"key": "region", "label": "Region", "sort_order": 3},
            {"key": "regional_manager", "label": "Regional Manager", "sort_order": 5},
        ],
    )

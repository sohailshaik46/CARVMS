"""fix zonal manager and cluster dimension order

Zonal Manager must sit at position 3 (right after Zone), with Cluster at 4
-- the earlier migration accidentally left Cluster before Zonal Manager.
Pure display-order fix: the actual node tree is built from real parent_id
relationships in org_nodes, not from OrgDimension.sort_order, so this has
no effect on existing hierarchy data.

Revision ID: 52e34c0c400c
Revises: 5ef7674c9920
Create Date: 2026-08-13 17:34:53.304549

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '52e34c0c400c'
down_revision: Union[str, Sequence[str], None] = '5ef7674c9920'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("UPDATE org_dimensions SET sort_order = 3 WHERE key = 'zonal_manager'")
    op.execute("UPDATE org_dimensions SET sort_order = 4 WHERE key = 'cluster'")


def downgrade() -> None:
    op.execute("UPDATE org_dimensions SET sort_order = 4 WHERE key = 'zonal_manager'")
    op.execute("UPDATE org_dimensions SET sort_order = 3 WHERE key = 'cluster'")

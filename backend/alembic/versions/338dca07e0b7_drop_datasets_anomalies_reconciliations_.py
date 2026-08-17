"""drop datasets anomalies reconciliations tables

The generic "Datasets" feature (upload/profile/reconcile/anomaly-scan any
CSV/Excel file) is removed entirely per explicit user request -- nav, page,
API routes, service code, and now its own data. This drops the four tables
that fully contained it: dataset_anomalies, reconciliations, dataset_columns,
datasets -- in that FK-safe (children-before-parent) order, since
dataset_columns/dataset_anomalies point at datasets.id and reconciliations
points at datasets.id twice (dataset_a_id/dataset_b_id).

Deliberately NOT touching anything else: no DCB, WRC, org, user, report, or
auto-validation table has ever had a foreign key into any of these four (see
the confirmed cross-reference audit in the commit message), so this is safe
to run without affecting any other domain's data. A real DROP TABLE (not an
`alembic downgrade` to before these tables existed) because ~20 unrelated
migrations have landed on top of the ones that created them -- downgrading
that far back would also revert all of that unrelated, currently-in-use
schema.

Revision ID: 338dca07e0b7
Revises: 24fa802b1040
Create Date: 2026-08-17 21:21:32.108607

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '338dca07e0b7'
down_revision: Union[str, Sequence[str], None] = '24fa802b1040'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Drop the Datasets feature's tables, children before parent."""
    op.drop_table("dataset_anomalies")
    op.drop_table("reconciliations")
    op.drop_table("dataset_columns")
    op.drop_table("datasets")


def downgrade() -> None:
    """Deliberately unsupported -- the Datasets feature's model/service/API
    code is gone, so there is nothing left to reconstruct these tables'
    rows against even if the tables were recreated empty. Recovering this
    data means restoring the pre-removal codebase and a DB backup taken
    before this migration ran, not an Alembic downgrade."""
    raise NotImplementedError(
        "Datasets feature was permanently removed -- restore from a backup taken before "
        "migration 338dca07e0b7 instead of downgrading."
    )

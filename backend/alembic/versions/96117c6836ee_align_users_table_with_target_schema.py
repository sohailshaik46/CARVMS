"""align users table with target schema

Renames password -> password_hash (preserves the existing bcrypt hash --
autogenerate wanted to drop+add, which would have destroyed it), converts
is_active from a 'Yes'/'No' string to a real Boolean via an explicit data
normalization step (a bare type cast would have stored the literal string
and made every row truthy), adds created_at/updated_at, and adds the
role CHECK constraint. Run only after backing up carvms.db.

Revision ID: 96117c6836ee
Revises: cfeced8a6088
Create Date: 2026-08-13 00:08:15.177952

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '96117c6836ee'
down_revision: Union[str, Sequence[str], None] = 'cfeced8a6088'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ROLE_CHECK_SQL = (
    "role IN ('Admin', 'Auditor', 'Finance', 'Center Manager', "
    "'Regional Manager', 'Zonal Manager')"
)


def upgrade() -> None:
    # Normalize is_active to '1'/'0' text *before* changing its column type,
    # so the batch-table-rebuild copies a value SQLite's INTEGER affinity
    # will store as a real 0/1 -- not the literal string 'Yes'/'No'.
    op.execute("UPDATE users SET is_active = CASE WHEN is_active = 'Yes' THEN '1' ELSE '0' END")

    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.alter_column(
            'password',
            new_column_name='password_hash',
            existing_type=sa.String(),
            existing_nullable=False,
        )
        batch_op.add_column(sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False))
        batch_op.add_column(sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False))
        # Drop the old 'Yes'/VARCHAR default FIRST, as its own statement --
        # Postgres tries to auto-cast a column's *existing* default to the
        # new type as part of ALTER COLUMN TYPE, separately from the row
        # data (which the USING clause below handles); it has no varchar
        # -> boolean cast for that and errors with "default for column
        # ... cannot be cast automatically to type boolean" if the old
        # default is still attached when the type change runs.
        batch_op.alter_column(
            'is_active',
            existing_type=sa.VARCHAR(),
            server_default=None,
        )
        batch_op.alter_column(
            'is_active',
            existing_type=sa.VARCHAR(),
            type_=sa.Boolean(),
            server_default=sa.true(),
            nullable=False,
            # Postgres won't implicitly cast varchar -> boolean on a plain
            # ALTER COLUMN TYPE; needs an explicit USING clause. The values
            # are guaranteed to be exactly '1'/'0' at this point (the
            # UPDATE above just normalized them), which Postgres's boolean
            # input parser accepts directly. SQLite ignores this kwarg
            # entirely (batch mode recreates the table there instead), so
            # this is a no-op on that dialect -- safe on both.
            postgresql_using="is_active::boolean",
        )
        batch_op.create_check_constraint('ck_users_role_valid', ROLE_CHECK_SQL)


def downgrade() -> None:
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_constraint('ck_users_role_valid', type_='check')
        batch_op.alter_column(
            'is_active',
            existing_type=sa.Boolean(),
            type_=sa.VARCHAR(),
            nullable=True,
            # Same reasoning as upgrade() above, reversed -- Postgres needs
            # an explicit cast for boolean -> varchar too.
            postgresql_using="is_active::varchar",
        )
        batch_op.drop_column('updated_at')
        batch_op.drop_column('created_at')
        batch_op.alter_column(
            'password_hash',
            new_column_name='password',
            existing_type=sa.String(),
            existing_nullable=False,
        )

    op.execute("UPDATE users SET is_active = CASE WHEN is_active = '1' THEN 'Yes' ELSE 'No' END")

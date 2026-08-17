"""genesis create users table pre-alembic shape

The real true beginning of this project's schema: a `users` table existed
before Alembic was introduced to manage migrations here (created by an
ad-hoc script, not tracked as a migration) -- the actual first tracked
migration, 96117c6836ee ("align users table with target schema"), only
ALTERs that pre-existing table (renames password -> password_hash,
converts is_active from a 'Yes'/'No' string to Boolean, etc.) and has
always assumed the table already exists.

That's fine for every database that's been running since before this repo
had Alembic at all, but it means `alembic upgrade head` from a genuinely
empty database (a brand-new deploy) has always failed at 96117c6836ee with
"no such table: users" -- there was never a migration that actually
creates it. This migration is that missing first step, inserted as the
new true base so a from-scratch deploy works; it changes nothing for any
database that already exists (its recorded alembic_version is already
past this point, so this step is simply a no-op ancestor for those).

Only creates the columns 96117c6836ee's ALTERs reference by name
(id/username/email/password/role/is_active) -- every other column
(org_node_id, phone_number, created_at, etc.) is added by its own later
migration exactly as it always was, regardless of whether the table was
freshly created here or pre-existed.

Revision ID: cfeced8a6088
Revises:
Create Date: 2026-08-17 22:05:00.185844

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'cfeced8a6088'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'users',
        sa.Column('id', sa.Integer(), primary_key=True, index=True),
        sa.Column('username', sa.String(), nullable=False, unique=True, index=True),
        sa.Column('email', sa.String(), nullable=False, unique=True),
        sa.Column('password', sa.String(), nullable=False),
        sa.Column('role', sa.String(), nullable=False, server_default='Auditor'),
        # Yes/No text, not yet Boolean -- 96117c6836ee is what converts this.
        sa.Column('is_active', sa.String(), nullable=True, server_default='Yes'),
    )


def downgrade() -> None:
    op.drop_table('users')

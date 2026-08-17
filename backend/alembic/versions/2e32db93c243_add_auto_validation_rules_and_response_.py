"""add auto validation rules and response columns

Revision ID: 2e32db93c243
Revises: 0da8141e7158
Create Date: 2026-08-17 13:01:01.806902

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2e32db93c243'
down_revision: Union[str, Sequence[str], None] = '0da8141e7158'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Seeded verbatim from the user's reference workbook
# ("Remarks.xlsx" -- "Consideration" + "No Consideration" sheets): 8 + 10
# categories, 16 + 33 keyword rows. Where a sheet cell listed several
# comma/slash-separated alternatives in one row (e.g. "Sukaran approval /
# Mahesh approval / CEO approval"), each alternative became its own rule row
# so the matcher can hit any one of them independently; parenthetical
# qualifiers that read as commentary rather than literal remark text (e.g.
# "(within 30 days)", "(if proof)") moved into `notes` instead of the
# matched keyword itself. These are ordinary rows in an editable table, not
# hardcoded logic -- Vigilance can add/disable/edit rules afterwards via
# the Auto Validation Rules screen without another migration.
_CONSIDERED_ROWS = [
    # (category, keyword_phrase, decision_label, notes)
    ("IP Bills Pending", "IP bills pending", "Consider", None),
    ("IP Bills Pending", "Insurance pending", "Consider", None),
    ("IP Bills Pending", "Hospital Partner not shared bill details", "Consider", None),
    ("Hospital Partner Delay", "HP not shared bill amount/rate plan", "Consider", None),
    ("Rebilling", "Wrong bill created", "Consider", "if proof"),
    ("Rebilling", "Price modification", "Consider", "if proof"),
    ("Rebilling", "Consultant tagging correction", "Consider", "if proof"),
    ("New Center", "Newly launched center", "Consider", "within 30 days of launch"),
    ("New CM / New Joining", "Newly joined CM/BE under training", "Consider (First Exception)", "3 months; first exception only"),
    ("Center Closure", "Permanently closed", "Consider", None),
    ("Center Closure", "Mutually terminated", "Consider", None),
    ("Approved Exception", "Sukaran approval", "Consider (Always)", None),
    ("Approved Exception", "Mahesh approval", "Consider (Always)", None),
    ("Approved Exception", "CEO approval", "Consider (Always)", None),
    ("DOC Billing Exception", "DOC approval", "Consider (with approval)", None),
    ("DOC Billing Exception", "Sukaran Approval", "Consider (with approval)", None),
]

_NOT_CONSIDERED_ROWS = [
    # (category, keyword_phrase, reason, notes)
    ("Staff Negligence", "Forgot to bill", "Internal lapse or Center lapse", None),
    ("Staff Negligence", "Missed billing", "Internal lapse or Center lapse", None),
    ("Staff Negligence", "Billing missed by staff", "Internal lapse or Center lapse", None),
    ("Staff Negligence", "Staff oversight", "Internal lapse or Center lapse", None),
    ("Delay", "Delayed billing", "Internal lapse or Center lapse", None),
    ("Delay", "Late update", "Internal lapse or Center lapse", None),
    ("Delay", "Delay due to busy schedule", "Internal lapse or Center lapse", None),
    ("Delay", "High patient load", "Internal lapse or Center lapse", None),
    ("Leave", "CM on leave", "Leaves & Holidays are not considered as per SOP", None),
    ("Leave", "Staff on leave", "Leaves & Holidays are not considered as per SOP", None),
    ("Leave", "Holiday", "Leaves & Holidays are not considered as per SOP", None),
    ("Leave", "Festival", "Leaves & Holidays are not considered as per SOP", None),
    ("Leave", "Weekly off", "Leaves & Holidays are not considered as per SOP", None),
    ("No Explanation", "Kindly consider", "No valid reason or No justification", None),
    ("No Explanation", "Please waive penalty", "No valid reason or No justification", None),
    ("No Explanation", "Sorry for delay", "No valid reason or No justification", None),
    ("No Explanation", "Will not repeat", "No valid reason or No justification", None),
    ("No Explanation", "Please approve", "No valid reason or No justification", None),
    ("No Proof", "Proof will be shared later", "Evidence or Proof unavailable", None),
    ("No Proof", "Mail will be shared", "Evidence or Proof unavailable", None),
    ("No Proof", "Awaiting confirmation", "Evidence or Proof unavailable", None),
    ("No Proof", "Under discussion", "Evidence or Proof unavailable", None),
    ("Process Failure", "Missed due to system check", "Internal lapse or Center lapse", None),
    ("Process Failure", "Billing pending from our side", "Internal lapse or Center lapse", None),
    ("Process Failure", "Delay in uploading", "Internal lapse or Center lapse", None),
    ("Credit", "Credit given without approval", "Policy violation", None),
    ("Credit", "Pending credit approval", "Approval should be obtained before billing", None),
    ("Generic", "Working on it", "Internal lapse or Center lapse", None),
    ("Generic", "Will update", "Internal lapse or Center lapse", None),
    ("Generic", "Team missed", "Internal lapse or Center lapse", None),
    ("Generic", "Communication gap", "Internal lapse or Center lapse", None),
    ("Generic", "Network issue", "Requires supporting proof", "without proof"),
    ("Generic", "System issue", "Requires supporting proof", "without IT ticket"),
]


def _seed_rules() -> None:
    table = sa.table(
        "auto_validation_rules",
        sa.column("bucket", sa.String),
        sa.column("category", sa.String),
        sa.column("keyword_phrase", sa.String),
        sa.column("decision_label", sa.String),
        sa.column("reason", sa.Text),
        sa.column("notes", sa.Text),
        sa.column("applies_to", sa.String),
        sa.column("is_active", sa.Boolean),
    )
    rows = [
        dict(
            bucket="considered", category=category, keyword_phrase=keyword_phrase, decision_label=decision_label,
            reason=None, notes=notes, applies_to="both", is_active=True,
        )
        for category, keyword_phrase, decision_label, notes in _CONSIDERED_ROWS
    ] + [
        dict(
            bucket="not_considered", category=category, keyword_phrase=keyword_phrase,
            decision_label="Not Considered", reason=reason, notes=notes, applies_to="both", is_active=True,
        )
        for category, keyword_phrase, reason, notes in _NOT_CONSIDERED_ROWS
    ]
    op.bulk_insert(table, rows)


def upgrade() -> None:
    """Upgrade schema."""
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('auto_validation_rules',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('bucket', sa.String(), nullable=False),
    sa.Column('category', sa.String(), nullable=False),
    sa.Column('keyword_phrase', sa.String(), nullable=False),
    sa.Column('decision_label', sa.String(), nullable=False),
    sa.Column('reason', sa.Text(), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('applies_to', sa.String(), nullable=False),
    sa.Column('is_active', sa.Boolean(), server_default='1', nullable=False),
    sa.Column('created_by_id', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.CheckConstraint("applies_to IN ('both', 'dcb', 'wrc')", name='ck_avr_applies_to_valid'),
    sa.CheckConstraint("bucket IN ('considered', 'not_considered')", name='ck_avr_bucket_valid'),
    sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('auto_validation_rules', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_auto_validation_rules_bucket'), ['bucket'], unique=False)
        batch_op.create_index(batch_op.f('ix_auto_validation_rules_id'), ['id'], unique=False)

    with op.batch_alter_table('delayed_cash_case_responses', schema=None) as batch_op:
        batch_op.add_column(sa.Column('auto_bucket', sa.String(), nullable=True))
        batch_op.add_column(sa.Column('auto_category', sa.String(), nullable=True))
        batch_op.add_column(sa.Column('auto_matched_keyword', sa.String(), nullable=True))
        batch_op.add_column(sa.Column('auto_decision_label', sa.String(), nullable=True))
        batch_op.add_column(sa.Column('auto_reason', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('auto_evaluated_at', sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column('admin_override_bucket', sa.String(), nullable=True))
        batch_op.add_column(sa.Column('admin_override_by_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('admin_override_at', sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column('admin_override_note', sa.Text(), nullable=True))
        batch_op.create_foreign_key(
            'fk_dcb_case_responses_admin_override_by_id_users', 'users', ['admin_override_by_id'], ['id']
        )

    with op.batch_alter_table('weekly_revenue_case_responses', schema=None) as batch_op:
        batch_op.add_column(sa.Column('auto_bucket', sa.String(), nullable=True))
        batch_op.add_column(sa.Column('auto_category', sa.String(), nullable=True))
        batch_op.add_column(sa.Column('auto_matched_keyword', sa.String(), nullable=True))
        batch_op.add_column(sa.Column('auto_decision_label', sa.String(), nullable=True))
        batch_op.add_column(sa.Column('auto_reason', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('auto_evaluated_at', sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column('admin_override_bucket', sa.String(), nullable=True))
        batch_op.add_column(sa.Column('admin_override_by_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('admin_override_at', sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column('admin_override_note', sa.Text(), nullable=True))
        batch_op.create_foreign_key(
            'fk_wrc_case_responses_admin_override_by_id_users', 'users', ['admin_override_by_id'], ['id']
        )

    # ### end Alembic commands ###

    _seed_rules()


def downgrade() -> None:
    """Downgrade schema."""
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('weekly_revenue_case_responses', schema=None) as batch_op:
        batch_op.drop_constraint('fk_wrc_case_responses_admin_override_by_id_users', type_='foreignkey')
        batch_op.drop_column('admin_override_note')
        batch_op.drop_column('admin_override_at')
        batch_op.drop_column('admin_override_by_id')
        batch_op.drop_column('admin_override_bucket')
        batch_op.drop_column('auto_evaluated_at')
        batch_op.drop_column('auto_reason')
        batch_op.drop_column('auto_decision_label')
        batch_op.drop_column('auto_matched_keyword')
        batch_op.drop_column('auto_category')
        batch_op.drop_column('auto_bucket')

    with op.batch_alter_table('delayed_cash_case_responses', schema=None) as batch_op:
        batch_op.drop_constraint('fk_dcb_case_responses_admin_override_by_id_users', type_='foreignkey')
        batch_op.drop_column('admin_override_note')
        batch_op.drop_column('admin_override_at')
        batch_op.drop_column('admin_override_by_id')
        batch_op.drop_column('admin_override_bucket')
        batch_op.drop_column('auto_evaluated_at')
        batch_op.drop_column('auto_reason')
        batch_op.drop_column('auto_decision_label')
        batch_op.drop_column('auto_matched_keyword')
        batch_op.drop_column('auto_category')
        batch_op.drop_column('auto_bucket')

    with op.batch_alter_table('auto_validation_rules', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_auto_validation_rules_id'))
        batch_op.drop_index(batch_op.f('ix_auto_validation_rules_bucket'))

    op.drop_table('auto_validation_rules')
    # ### end Alembic commands ###

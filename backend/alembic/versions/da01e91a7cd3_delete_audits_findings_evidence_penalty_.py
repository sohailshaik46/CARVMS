"""delete audits findings evidence penalty domain

The Audits/Findings/Evidence/PenaltyRule/Penalty/Recovery case-management
domain is deleted in full, per explicit user request (2026-08-14):
"please delete this complete audit section and its related data from this
project as iam not performing any audits from here" -- confirmed via an
explicit follow-up choice of "Delete Audits fully, rebuild the rest around
Billing data". This is a genuine, permanent data loss for any existing
audits/findings/evidence/penalties/recoveries rows -- the user was told
this in chat before this migration was written.

audit_logs (the generic cross-cutting governance trail) and Anomalies
(dataset-scoped forensic detection) are explicitly NOT part of this
domain and are kept -- only the one coupling point between them
(DatasetAnomaly.escalated_finding_id, which pointed at the now-deleted
findings table) is removed.

Also updates two CHECK constraints that referenced the old domain's
values: center_scoring_weights.component_key (old financial_exposure/
recovery_rate/open_findings/repeat_findings -> new non_compliance_rate/
repeat_violations/outstanding_penalty/unresolved_cases, re-seeded equal)
and report_history.format (adds docx/pptx for the new Word/PowerPoint
export formats).

Revision ID: da01e91a7cd3
Revises: 548f8b65c7d5
Create Date: 2026-08-14 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'da01e91a7cd3'
down_revision: Union[str, Sequence[str], None] = '548f8b65c7d5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


OLD_CENTER_SCORE_COMPONENTS = ('financial_exposure', 'recovery_rate', 'open_findings', 'repeat_findings')
NEW_CENTER_SCORE_COMPONENTS = ('non_compliance_rate', 'repeat_violations', 'outstanding_penalty', 'unresolved_cases')


def upgrade() -> None:
    # 0. Any anomaly already escalated has no valid status left once
    # "Escalated" is removed below -- carry its history forward as a
    # dismissal note rather than leaving it in a status the new CHECK
    # constraint would reject outright.
    op.execute(
        "UPDATE dataset_anomalies SET status = 'Dismissed', "
        "dismissed_reason = COALESCE(dismissed_reason, '') || "
        "'[Auto-migrated 2026-08-14: was Escalated to finding #' || escalated_finding_id || "
        "', but the Audits/Findings domain was deleted -- see migration da01e91a7cd3.]' "
        "WHERE status = 'Escalated'"
    )

    # 1. Sever the one coupling point from Anomalies (kept) into Findings
    # (being deleted) before Findings itself goes away.
    with op.batch_alter_table('dataset_anomalies', schema=None) as batch_op:
        batch_op.drop_constraint('ck_anomalies_status_valid', type_='check')
        batch_op.create_check_constraint(
            'ck_anomalies_status_valid', "status IN ('Open', 'Dismissed')"
        )
        batch_op.drop_column('escalated_finding_id')
        batch_op.drop_column('escalated_by_id')
        batch_op.drop_column('escalated_at')

    # 2. Drop the domain's tables, child-to-parent (evidence/recoveries
    # reference audits/findings/penalties; penalties references
    # findings+penalty_rules; findings references audits).
    op.drop_table('evidence')
    op.drop_table('recoveries')
    op.drop_table('penalties')
    op.drop_table('findings')
    op.drop_table('penalty_rules')
    op.drop_table('audits')

    # 3. Center Rankings' scoring components are renamed to reflect
    # SOP-non-compliance analysis instead of Audits/Findings terms --
    # delete the old rows (their component_keys no longer exist) and
    # re-seed equal weights under the new keys.
    op.execute("DELETE FROM center_scoring_weights")
    with op.batch_alter_table('center_scoring_weights', schema=None) as batch_op:
        batch_op.drop_constraint('ck_center_scoring_component_valid', type_='check')
        batch_op.create_check_constraint(
            'ck_center_scoring_component_valid',
            f"component_key IN {NEW_CENTER_SCORE_COMPONENTS}",
        )
    center_scoring_weights = sa.table(
        'center_scoring_weights',
        sa.column('component_key', sa.String),
        sa.column('weight', sa.Float),
    )
    op.bulk_insert(
        center_scoring_weights,
        [{"component_key": key, "weight": 0.25} for key in NEW_CENTER_SCORE_COMPONENTS],
    )

    # 4. Reports gained Word/PowerPoint export alongside CSV/Excel/PDF.
    with op.batch_alter_table('report_history', schema=None) as batch_op:
        batch_op.drop_constraint('ck_report_history_format_valid', type_='check')
        batch_op.create_check_constraint(
            'ck_report_history_format_valid', "format IN ('csv', 'xlsx', 'pdf', 'docx', 'pptx')"
        )


def downgrade() -> None:
    # Reverse order of upgrade(). Recreates the SCHEMA only -- the actual
    # audits/findings/evidence/penalties/recoveries rows deleted in
    # upgrade() are gone for good; this does not restore data.
    with op.batch_alter_table('report_history', schema=None) as batch_op:
        batch_op.drop_constraint('ck_report_history_format_valid', type_='check')
        batch_op.create_check_constraint(
            'ck_report_history_format_valid', "format IN ('csv', 'xlsx', 'pdf')"
        )

    op.execute("DELETE FROM center_scoring_weights")
    with op.batch_alter_table('center_scoring_weights', schema=None) as batch_op:
        batch_op.drop_constraint('ck_center_scoring_component_valid', type_='check')
        batch_op.create_check_constraint(
            'ck_center_scoring_component_valid',
            f"component_key IN {OLD_CENTER_SCORE_COMPONENTS}",
        )
    center_scoring_weights = sa.table(
        'center_scoring_weights',
        sa.column('component_key', sa.String),
        sa.column('weight', sa.Float),
    )
    op.bulk_insert(
        center_scoring_weights,
        [{"component_key": key, "weight": 0.25} for key in OLD_CENTER_SCORE_COMPONENTS],
    )

    op.create_table(
        'audits',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('audit_number', sa.String(), nullable=False),
        sa.Column('title', sa.String(), nullable=False),
        sa.Column('type', sa.String(), nullable=False),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('priority', sa.String(), nullable=False),
        sa.Column('center_node_id', sa.Integer(), nullable=True),
        sa.Column('assigned_to_id', sa.Integer(), nullable=True),
        sa.Column('created_by_id', sa.Integer(), nullable=False),
        sa.Column('opened_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('due_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('closed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.CheckConstraint("priority IN ('Low', 'Medium', 'High', 'Critical')", name='ck_audits_priority_valid'),
        sa.CheckConstraint("status IN ('Draft', 'Assigned', 'In Progress', 'Under Review', 'Action Required', 'Closed', 'Cancelled')", name='ck_audits_status_valid'),
        sa.ForeignKeyConstraint(['assigned_to_id'], ['users.id']),
        sa.ForeignKeyConstraint(['center_node_id'], ['org_nodes.id']),
        sa.ForeignKeyConstraint(['created_by_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('audits', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_audits_assigned_to_id'), ['assigned_to_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_audits_audit_number'), ['audit_number'], unique=True)
        batch_op.create_index(batch_op.f('ix_audits_center_node_id'), ['center_node_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_audits_created_by_id'), ['created_by_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_audits_id'), ['id'], unique=False)

    op.create_table(
        'findings',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('audit_id', sa.Integer(), nullable=False),
        sa.Column('finding_number', sa.String(), nullable=False),
        sa.Column('category', sa.String(), nullable=False),
        sa.Column('severity', sa.String(), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('financial_exposure', sa.Numeric(precision=14, scale=2), nullable=True),
        sa.Column('recoverable_amount', sa.Numeric(precision=14, scale=2), nullable=True),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('owner_id', sa.Integer(), nullable=True),
        sa.Column('due_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_by_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.CheckConstraint("severity IN ('Low', 'Medium', 'High', 'Critical')", name='ck_findings_severity_valid'),
        sa.CheckConstraint("status IN ('Open', 'Under Review', 'Action Required', 'Resolved', 'Closed')", name='ck_findings_status_valid'),
        sa.ForeignKeyConstraint(['audit_id'], ['audits.id']),
        sa.ForeignKeyConstraint(['created_by_id'], ['users.id']),
        sa.ForeignKeyConstraint(['owner_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('findings', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_findings_audit_id'), ['audit_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_findings_created_by_id'), ['created_by_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_findings_finding_number'), ['finding_number'], unique=True)
        batch_op.create_index(batch_op.f('ix_findings_id'), ['id'], unique=False)
        batch_op.create_index(batch_op.f('ix_findings_owner_id'), ['owner_id'], unique=False)

    op.create_table(
        'evidence',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('audit_id', sa.Integer(), nullable=True),
        sa.Column('finding_id', sa.Integer(), nullable=True),
        sa.Column('original_filename', sa.String(), nullable=False),
        sa.Column('mime_type', sa.String(), nullable=False),
        sa.Column('size_bytes', sa.Integer(), nullable=False),
        sa.Column('checksum', sa.String(), nullable=False),
        sa.Column('storage_path', sa.String(), nullable=False),
        sa.Column('uploaded_by_id', sa.Integer(), nullable=False),
        sa.Column('uploaded_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.CheckConstraint('audit_id IS NOT NULL OR finding_id IS NOT NULL', name='ck_evidence_has_owner'),
        sa.ForeignKeyConstraint(['audit_id'], ['audits.id']),
        sa.ForeignKeyConstraint(['finding_id'], ['findings.id']),
        sa.ForeignKeyConstraint(['uploaded_by_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('evidence', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_evidence_audit_id'), ['audit_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_evidence_finding_id'), ['finding_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_evidence_id'), ['id'], unique=False)
        batch_op.create_index(batch_op.f('ix_evidence_uploaded_by_id'), ['uploaded_by_id'], unique=False)

    op.create_table(
        'penalty_rules',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('code', sa.String(), nullable=False),
        sa.Column('description', sa.String(), nullable=False),
        sa.Column('formula_config', sa.JSON(), nullable=False),
        sa.Column('effective_from', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('effective_to', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_by_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['created_by_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('penalty_rules', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_penalty_rules_code'), ['code'], unique=True)
        batch_op.create_index(batch_op.f('ix_penalty_rules_id'), ['id'], unique=False)

    op.create_table(
        'penalties',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('finding_id', sa.Integer(), nullable=False),
        sa.Column('rule_id', sa.Integer(), nullable=False),
        sa.Column('base_amount', sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column('penalty_amount', sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('proposed_by_id', sa.Integer(), nullable=False),
        sa.Column('approved_by_id', sa.Integer(), nullable=True),
        sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.CheckConstraint("status IN ('Proposed', 'Approved', 'Rejected', 'Recovered')", name='ck_penalties_status_valid'),
        sa.ForeignKeyConstraint(['approved_by_id'], ['users.id']),
        sa.ForeignKeyConstraint(['finding_id'], ['findings.id']),
        sa.ForeignKeyConstraint(['proposed_by_id'], ['users.id']),
        sa.ForeignKeyConstraint(['rule_id'], ['penalty_rules.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('penalties', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_penalties_finding_id'), ['finding_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_penalties_id'), ['id'], unique=False)
        batch_op.create_index(batch_op.f('ix_penalties_rule_id'), ['rule_id'], unique=False)

    op.create_table(
        'recoveries',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('penalty_id', sa.Integer(), nullable=False),
        sa.Column('amount', sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column('reference', sa.String(), nullable=True),
        sa.Column('recorded_by_id', sa.Integer(), nullable=False),
        sa.Column('recorded_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['penalty_id'], ['penalties.id']),
        sa.ForeignKeyConstraint(['recorded_by_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('recoveries', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_recoveries_id'), ['id'], unique=False)
        batch_op.create_index(batch_op.f('ix_recoveries_penalty_id'), ['penalty_id'], unique=False)

    with op.batch_alter_table('dataset_anomalies', schema=None) as batch_op:
        batch_op.add_column(sa.Column('escalated_finding_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('escalated_by_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('escalated_at', sa.DateTime(timezone=True), nullable=True))
        batch_op.create_foreign_key('fk_dataset_anomalies_escalated_finding_id_findings', 'findings', ['escalated_finding_id'], ['id'])
        batch_op.create_foreign_key('fk_dataset_anomalies_escalated_by_id_users', 'users', ['escalated_by_id'], ['id'])
        batch_op.drop_constraint('ck_anomalies_status_valid', type_='check')
        batch_op.create_check_constraint(
            'ck_anomalies_status_valid', "status IN ('Open', 'Dismissed', 'Escalated')"
        )

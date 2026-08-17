"""Weekly Revenue Closure penalty domain.

A deliberately separate engine from Delayed Cash Billing -- different
formula, different role hierarchy. Center Manager AND Cluster Manager
penalties DO apply here (Zonal Manager too, conditionally -- see below),
where Delayed Cash Billing explicitly excludes Center/Cluster Manager
penalties by design. The two must never be merged.

The formula (flat 6.25% per delinquent center per week, escalating to
Cluster/Zonal Manager as 6.25% x count of distinct centers under them) was
reverse-engineered from two real reference workbooks (Week 2 and Week 3,
Jul'26) and proven to reproduce every reconstructible figure in both with
zero mismatches. See
docs/CARVMS_WEEKLY_REVENUE_CLOSURE_FORMULA_ANALYSIS.md for the full proof,
including which two escalation rules were confirmed by the user directly
(rather than inferred from a single ambiguous data point) and which parts
(the raw daily ingestion format) are still not provable from what's been
supplied and remain unbuilt.
"""

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import relationship

from app.database.database import Base

WRC_RULE_STATUSES = ("draft", "approved")
WRC_BATCH_STATUSES = ("open", "closed")

# The two MIS categories confirmed present in real "remark received" rows,
# plus the third seen only in the "no remark" section's own column headers
# (never as an actual MIS Final Remarks value in the Data sheet -- see
# formula analysis doc S:6.4). Kept as one vocabulary since both incident
# tables use it.
WRC_INCIDENT_TYPES = ("bill_pending", "daily_report_not_sent", "no_billing_no_daily_report")

# Verdict on a WeeklyRevenueBillIncident -- human-decided (see formula
# analysis doc S:1), mirrors DelayedCashBill.considered's vocabulary.
WRC_CONSIDERED_STATUSES = ("considered", "not_considered")

WRC_ROLE_TYPES = ("cluster_manager", "zonal_manager")
WRC_SECTIONS = ("not_considered", "no_remark")

# "opened"/"submitted" -- same vocabulary and same reasoning as
# DCB_ACTIVITY_EVENT_TYPES in app/models/delayed_cash_billing.py.
WRC_ACTIVITY_EVENT_TYPES = ("opened", "submitted")


class WeeklyRevenueClosureRule(Base):
    """A versioned snapshot of the proven 6.25% penalty rate. Historical
    batches keep referencing the rule active when computed -- changing the
    rate later must never rewrite past penalties (same pattern as
    DelayedCashPenaltyRule)."""

    __tablename__ = "weekly_revenue_closure_rules"
    __table_args__ = (
        CheckConstraint(f"status IN {WRC_RULE_STATUSES}", name="ck_wrc_rules_status_valid"),
    )

    id = Column(Integer, primary_key=True, index=True)
    rule_version = Column(String, unique=True, nullable=False, index=True)
    # Proven: flat 6.25% per delinquent center, and the per-role escalation
    # multiplier's unit rate. External base (monthly gross salary) this
    # multiplies against is never fabricated here -- same caveat as
    # Delayed Cash Billing's monthly cap.
    penalty_rate = Column(Numeric(6, 4), nullable=False, default=0.0625)

    status = Column(String, nullable=False, default="draft")
    effective_from = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    effective_to = Column(DateTime(timezone=True), nullable=True)

    created_by_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    approved_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    created_by = relationship("User", foreign_keys=[created_by_id])
    approved_by = relationship("User", foreign_keys=[approved_by_id])


class WeeklyRevenueClosureBatch(Base):
    """One week's closure run (e.g. "Week 2 - Jul'26")."""

    __tablename__ = "weekly_revenue_closure_batches"
    __table_args__ = (
        CheckConstraint(f"status IN {WRC_BATCH_STATUSES}", name="ck_wrc_batches_status_valid"),
    )

    id = Column(Integer, primary_key=True, index=True)
    period_start = Column(Date, nullable=False)
    period_end = Column(Date, nullable=False)
    week_label = Column(String, nullable=False)  # e.g. "Week 2 - Jul'26", as-given, never reformatted
    rule_id = Column(Integer, ForeignKey("weekly_revenue_closure_rules.id"), nullable=False)
    status = Column(String, nullable=False, default="open")

    created_by_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    rule = relationship("WeeklyRevenueClosureRule")
    created_by = relationship("User")
    bill_incidents = relationship(
        "WeeklyRevenueBillIncident", back_populates="batch", cascade="all, delete-orphan"
    )
    no_remark_incidents = relationship(
        "WeeklyRevenueNoRemarkIncident", back_populates="batch", cascade="all, delete-orphan"
    )
    center_penalties = relationship(
        "WeeklyRevenueCenterPenalty", back_populates="batch", cascade="all, delete-orphan"
    )
    role_penalties = relationship(
        "WeeklyRevenueRolePenalty", back_populates="batch", cascade="all, delete-orphan"
    )


class WeeklyRevenueBillIncident(Base):
    """One delayed-billing incident that received a center remark -- mirrors
    the proven 'Data' sheet exactly (S.No, Zone, Cluster, Center Code,
    Center Name, Date, Billed Sessions, Daily Report, Variance, Remark,
    MIS Final Remarks, Center remarks, Penalty Remarks, Week). Day-level
    granularity preserved for audit/evidence even though the penalty
    calculation itself only cares about "did this center have >=1
    not_considered incident this week" (flat per center, never scaled by
    count -- proven in the formula analysis doc)."""

    __tablename__ = "weekly_revenue_bill_incidents"
    __table_args__ = (
        CheckConstraint(f"mis_final_remark IN {WRC_INCIDENT_TYPES}", name="ck_wrc_bill_incidents_mis_remark_valid"),
        CheckConstraint(
            f"considered IS NULL OR considered IN {WRC_CONSIDERED_STATUSES}",
            name="ck_wrc_bill_incidents_considered_valid",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    batch_id = Column(Integer, ForeignKey("weekly_revenue_closure_batches.id"), nullable=False, index=True)

    centre_code = Column(String, nullable=False, index=True)
    centre_name = Column(String, nullable=False)
    zone = Column(String, nullable=True)
    cluster = Column(String, nullable=True)  # Cluster Manager's name, as the source sheet names the column
    zonal_manager = Column(String, nullable=True)
    center_manager = Column(String, nullable=True)
    center_manager_npid = Column(String, nullable=True)

    incident_date = Column(Date, nullable=False)
    billed_sessions = Column(Integer, nullable=True)
    daily_report = Column(Integer, nullable=True)
    variance = Column(Integer, nullable=True)
    raw_remark = Column(String, nullable=True)  # e.g. "3 Bills Pending" / "Daily Report was not sent"
    mis_final_remark = Column(String, nullable=False)  # bill_pending | daily_report_not_sent
    center_remarks = Column(Text, nullable=True)  # free text explanation from the center

    # The human verdict, e.g. "Considered - HP Billing" / "Not Considered -
    # Center Lapse" -- stored verbatim (never overwritten) alongside the
    # structured `considered` field derived from its prefix, same pattern
    # as DelayedCashBill.penalty_remarks / .considered.
    penalty_remarks = Column(Text, nullable=True)
    considered = Column(String, nullable=True)
    # Who/when set `considered` -- mirrors DelayedCashBill.reviewed_by_id/
    # reviewed_at, added so Action Taken can sort by actual decision time
    # rather than ingest order.
    reviewed_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)

    # Set when Vigilance overrides this incident via mark_no_remark_received
    # -- the row is kept (audit trail of what was actually ingested) but is
    # no longer treated as "remark-received": excluded from the review
    # queue, the Data-sheet export, and the pending/considered/not_considered
    # summary counts (see weekly_revenue_closure_service.mark_no_remark_received).
    moved_to_no_remark = Column(Boolean, nullable=False, default=False, server_default="0")

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    batch = relationship("WeeklyRevenueClosureBatch", back_populates="bill_incidents")
    reviewed_by = relationship("User", foreign_keys=[reviewed_by_id])


class WeeklyRevenueNoRemarkIncident(Base):
    """One center's delinquency for a week where NO remark was ever
    submitted at all -- the "Remarks Not Received" section's source. Unlike
    WeeklyRevenueBillIncident, no day-level detail is provable from the two
    reference workbooks (only aggregate incident-type flags per center per
    week are in the proven output) -- see formula analysis doc S:6.4 for why
    a day-level version of this table isn't built yet."""

    __tablename__ = "weekly_revenue_no_remark_incidents"
    __table_args__ = (
        UniqueConstraint(
            "batch_id", "centre_code", "incident_type", name="uq_wrc_no_remark_batch_centre_type"
        ),
        CheckConstraint(f"incident_type IN {WRC_INCIDENT_TYPES}", name="ck_wrc_no_remark_incident_type_valid"),
    )

    id = Column(Integer, primary_key=True, index=True)
    batch_id = Column(Integer, ForeignKey("weekly_revenue_closure_batches.id"), nullable=False, index=True)

    centre_code = Column(String, nullable=False, index=True)
    centre_name = Column(String, nullable=False)
    zone = Column(String, nullable=True)
    cluster = Column(String, nullable=True)
    zonal_manager = Column(String, nullable=True)
    center_manager = Column(String, nullable=True)
    center_manager_npid = Column(String, nullable=True)

    incident_type = Column(String, nullable=False)
    incident_count = Column(Integer, nullable=False, default=1)  # informational only -- penalty never scales by this

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    batch = relationship("WeeklyRevenueClosureBatch", back_populates="no_remark_incidents")


class WeeklyRevenueCenterPenalty(Base):
    """One center's penalty for one week -- computed, never hand-entered.
    A center can be penalized under BOTH sections independently in the same
    week (not observed in either reference file, but nothing in the proven
    structure rules it out -- see formula analysis doc S:3), so the two
    amounts are tracked separately rather than pre-summed into one opaque
    total."""

    __tablename__ = "weekly_revenue_center_penalties"
    __table_args__ = (
        UniqueConstraint("batch_id", "centre_code", name="uq_wrc_center_penalties_batch_centre"),
    )

    id = Column(Integer, primary_key=True, index=True)
    batch_id = Column(Integer, ForeignKey("weekly_revenue_closure_batches.id"), nullable=False, index=True)

    centre_code = Column(String, nullable=False, index=True)
    centre_name = Column(String, nullable=False)
    center_manager = Column(String, nullable=True)
    center_manager_npid = Column(String, nullable=True)

    # Flat rate (e.g. 0.0625) if this center had >=1 qualifying incident in
    # that section this week, else 0 -- never scaled by incident count
    # (proven flat in the formula analysis doc).
    not_considered_penalty = Column(Numeric(6, 4), nullable=False, default=0)
    no_remark_penalty = Column(Numeric(6, 4), nullable=False, default=0)

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    batch = relationship("WeeklyRevenueClosureBatch", back_populates="center_penalties")


class WeeklyRevenueRolePenalty(Base):
    """One Cluster or Zonal Manager's escalated penalty for one week, one
    section -- rate x count of distinct centers under them with a
    qualifying incident in that section. Confirmed rules (see formula
    analysis doc S:6.2/6.3, resolved by the user directly rather than
    inferred from one ambiguous data point):
      - "not_considered" section: Cluster Manager escalates, counting only
        bill_pending-type incidents. Zonal Manager NEVER escalates here.
      - "no_remark" section: both Cluster and Zonal Manager escalate,
        counting every incident type."""

    __tablename__ = "weekly_revenue_role_penalties"
    __table_args__ = (
        UniqueConstraint(
            "batch_id", "role", "person_npid", "section", name="uq_wrc_role_penalties_batch_role_person_section"
        ),
        CheckConstraint(f"role IN {WRC_ROLE_TYPES}", name="ck_wrc_role_penalties_role_valid"),
        CheckConstraint(f"section IN {WRC_SECTIONS}", name="ck_wrc_role_penalties_section_valid"),
    )

    id = Column(Integer, primary_key=True, index=True)
    batch_id = Column(Integer, ForeignKey("weekly_revenue_closure_batches.id"), nullable=False, index=True)

    role = Column(String, nullable=False)
    section = Column(String, nullable=False)
    person_name = Column(String, nullable=False)
    person_npid = Column(String, nullable=True)
    distinct_center_count = Column(Integer, nullable=False)
    penalty_amount = Column(Numeric(8, 4), nullable=False)

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    batch = relationship("WeeklyRevenueClosureBatch", back_populates="role_penalties")


class WeeklyRevenueCenterCase(Base):
    """The public response-portal's per-center-per-batch case handle --
    deliberately independent of WeeklyRevenueCenterPenalty, which only
    exists once compute_center_penalties runs at close_batch time (i.e.
    after every incident is already reviewed). A center needs to be able
    to open its case and respond WHILE incidents are still pending review,
    not only after the batch closes -- so this case handle exists from the
    first response-link mint, keyed by (batch_id, centre_code) the same
    way DelayedCashCenterPenalty is for Delayed Cash Billing, but without
    coupling to the penalty computation's own lifecycle."""

    __tablename__ = "weekly_revenue_center_cases"
    __table_args__ = (
        UniqueConstraint("batch_id", "centre_code", name="uq_wrc_center_cases_batch_centre"),
    )

    id = Column(Integer, primary_key=True, index=True)
    batch_id = Column(Integer, ForeignKey("weekly_revenue_closure_batches.id"), nullable=False, index=True)

    centre_code = Column(String, nullable=False, index=True)
    centre_name = Column(String, nullable=False)

    # Public, unauthenticated response-portal access -- same pattern as
    # DelayedCashCenterPenalty.response_token: a center manager opens
    # {FRONTEND_URL}/respond/weekly-revenue/{response_token} from the
    # notification email, with no CARVMS login. expires_at is informational
    # (the 48h TAT boundary) -- a late submission is still accepted.
    response_token = Column(String, unique=True, nullable=True, index=True)
    response_token_expires_at = Column(DateTime(timezone=True), nullable=True)

    # See DelayedCashCenterPenalty.escalation_sms_sent_at -- same meaning,
    # same "never reset once set" rule.
    escalation_sms_sent_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    batch = relationship("WeeklyRevenueClosureBatch")
    responses = relationship(
        "WeeklyRevenueCaseResponse", back_populates="case", cascade="all, delete-orphan"
    )


class WeeklyRevenueCaseResponse(Base):
    """One center's submission through the public response portal --
    mirrors DelayedCashCaseResponse exactly (same mandatory fields, same
    append-only reasoning, same metadata-only evidence storage)."""

    __tablename__ = "weekly_revenue_case_responses"

    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(Integer, ForeignKey("weekly_revenue_center_cases.id"), nullable=False, index=True)

    responder_name = Column(String, nullable=False)
    responder_npid = Column(String, nullable=False)
    responder_email = Column(String, nullable=True)
    reason = Column(Text, nullable=False)

    # See DelayedCashCaseResponse.selected_center_code/selected_center_name
    # for why this is stored as-given rather than validated against the
    # case's own centre_code.
    selected_center_code = Column(String, nullable=True)
    selected_center_name = Column(String, nullable=True)

    evidence_original_filename = Column(String, nullable=False)
    evidence_mime_type = Column(String, nullable=False)
    evidence_size_bytes = Column(Integer, nullable=False)
    evidence_checksum = Column(String, nullable=False)
    evidence_storage_path = Column(String, nullable=False)

    submitted_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    was_within_tat = Column(String, nullable=True)  # "within_window" | "overdue" | unknown (None)

    # ---- auto-validation -- mirrors DelayedCashCaseResponse's fields exactly
    # (see app/models/auto_validation.py and app/models/delayed_cash_billing.py
    # for the full reasoning) ----
    auto_bucket = Column(String, nullable=True)
    auto_category = Column(String, nullable=True)
    auto_matched_keyword = Column(String, nullable=True)
    auto_decision_label = Column(String, nullable=True)
    auto_reason = Column(Text, nullable=True)
    auto_evaluated_at = Column(DateTime(timezone=True), nullable=True)

    admin_override_bucket = Column(String, nullable=True)
    admin_override_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    admin_override_at = Column(DateTime(timezone=True), nullable=True)
    admin_override_note = Column(Text, nullable=True)

    case = relationship("WeeklyRevenueCenterCase", back_populates="responses")
    admin_override_by = relationship("User", foreign_keys=[admin_override_by_id])


class WeeklyRevenueCenterActivity(Base):
    """Every time a center manager's browser touches the public portal --
    mirrors DelayedCashCenterActivity exactly."""

    __tablename__ = "weekly_revenue_center_activity"
    __table_args__ = (
        CheckConstraint(f"event_type IN {WRC_ACTIVITY_EVENT_TYPES}", name="ck_wrc_activity_event_type_valid"),
    )

    id = Column(Integer, primary_key=True, index=True)
    centre_code = Column(String, nullable=False, index=True)
    centre_name = Column(String, nullable=True)
    case_id = Column(Integer, ForeignKey("weekly_revenue_center_cases.id"), nullable=True, index=True)
    event_type = Column(String, nullable=False)
    occurred_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    case = relationship("WeeklyRevenueCenterCase")

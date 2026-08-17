"""Delayed Cash Billing penalty domain.

The formula implemented here (penalty per bill = day_difference x rate_per_day,
summed per center) was reverse-engineered from a real reference workbook and
proven to reproduce it exactly -- 94/94 centers, 585/585 bills, Rs.137,900 total,
zero mismatches. See docs/CARVMS_DELAYED_CASH_PENALTY_FORMULA_ANALYSIS.md for the
full proof. Nothing in this module invents a rate, a slab, or a center-specific
exception -- the rate lives in DelayedCashPenaltyRule, versioned, so a future
change never rewrites history.

This is a deliberately separate engine from Weekly Revenue Closure's penalty
model (different formula, different role hierarchy -- Center Manager and
Cluster Manager penalties are explicitly not applicable here) and must not be
merged with it.
"""

from sqlalchemy import (
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

DCB_RULE_STATUSES = ("draft", "approved")

# "opened" = a center manager viewed a case (either via a per-case token
# link, or by picking their center on the single shared link -- which may
# surface more than one open case, each viewed as its own "opened" row).
# "submitted" = they actually filed a response. Both are logged even for
# centers just browsing without ever submitting, per the requirement to
# capture every case a manager opens, not only the ones they act on.
DCB_ACTIVITY_EVENT_TYPES = ("opened", "submitted")

# "match" = calculated_day_difference (created_date - BILLDATE) agrees with the
# uploaded source_day_difference. "mismatch" means the record is flagged for
# review -- the source value is never silently overwritten or silently trusted.
DCB_DIFFERENCE_CHECK_STATUSES = ("match", "mismatch")
DCB_DATA_QUALITY_STATUSES = ("ok", "flagged")

DCB_BATCH_STATUSES = ("uploaded", "published", "closed")

# Publishing = every delayed bill, unfiltered by remark. Validated = recomputed
# over only the bills whose remark was NOT accepted as a valid exception.
# Capped = validated_penalty compared against a monthly cap; the cap itself
# needs an external salary figure this codebase must never fabricate, so
# "awaiting_cap_input" is a first-class state, not a silent fallback to
# validated_penalty.
DCB_PENALTY_STATUSES = ("published", "validated", "awaiting_cap_input", "capped")

# Vigilance's per-bill review verdict, set one bill at a time from the review
# queue. Only "considered"/"not_considered" are TERMINAL -- they're what
# recompute_validated_penalty sums over. "needs_more_detail"/"needs_proof"
# mean "kick this back to the center for more information" -- the bill isn't
# ready for a financial decision yet, so it's treated the same as "not yet
# reviewed" (null) by the calculator, but it's a distinct, visible state so
# Vigilance and the center both know a follow-up is expected, not silence.
DCB_BILL_REVIEW_DECISIONS = ("considered", "not_considered", "needs_more_detail", "needs_proof")


class DelayedCashPenaltyRule(Base):
    """A versioned snapshot of the delayed-cash formula's two proven
    constants: the per-day rate and the monthly cap rate. Historical cases
    keep referencing the rule version active when they were computed --
    changing the rate later must never rewrite past penalties."""

    __tablename__ = "delayed_cash_penalty_rules"
    __table_args__ = (
        CheckConstraint(f"status IN {DCB_RULE_STATUSES}", name="ck_dcb_rules_status_valid"),
    )

    id = Column(Integer, primary_key=True, index=True)
    rule_version = Column(String, unique=True, nullable=False, index=True)

    # Proven: Rs.100 per day of delay, per bill (see formula analysis doc).
    rate_per_day = Column(Numeric(10, 2), nullable=False, default=100)
    # Proven: 6.25% monthly cap RATE. The base it multiplies (a monthly gross
    # salary component) is external HR/payroll data, never fabricated here.
    monthly_cap_percentage = Column(Numeric(6, 4), nullable=False, default=0.0625)

    status = Column(String, nullable=False, default="draft")
    effective_from = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    effective_to = Column(DateTime(timezone=True), nullable=True)

    created_by_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    approved_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    created_by = relationship("User", foreign_keys=[created_by_id])
    approved_by = relationship("User", foreign_keys=[approved_by_id])


class DelayedCashUploadBatch(Base):
    """One weekly/monthly Excel upload of raw delayed-cash bills."""

    __tablename__ = "delayed_cash_upload_batches"
    __table_args__ = (
        CheckConstraint(f"status IN {DCB_BATCH_STATUSES}", name="ck_dcb_batches_status_valid"),
    )

    id = Column(Integer, primary_key=True, index=True)
    period_start = Column(Date, nullable=False)
    period_end = Column(Date, nullable=False)
    source_filename = Column(String, nullable=False)
    rule_id = Column(Integer, ForeignKey("delayed_cash_penalty_rules.id"), nullable=False)
    status = Column(String, nullable=False, default="uploaded")

    uploaded_by_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    uploaded_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    rule = relationship("DelayedCashPenaltyRule")
    uploaded_by = relationship("User")
    bills = relationship("DelayedCashBill", back_populates="batch", cascade="all, delete-orphan")
    center_penalties = relationship(
        "DelayedCashCenterPenalty", back_populates="batch", cascade="all, delete-orphan"
    )


class DelayedCashBill(Base):
    """One raw delayed bill record. Source columns (sales_bill, bill_date,
    bill_created_time, created_date, source_day_difference) are preserved
    exactly as uploaded and never overwritten -- calculated_day_difference and
    calculated_penalty are separate, derived columns."""

    __tablename__ = "delayed_cash_bills"
    __table_args__ = (
        UniqueConstraint("batch_id", "sales_bill", name="uq_dcb_bills_batch_salesbill"),
        CheckConstraint(f"difference_check IN {DCB_DIFFERENCE_CHECK_STATUSES}", name="ck_dcb_bills_diff_check_valid"),
        CheckConstraint(f"data_quality_status IN {DCB_DATA_QUALITY_STATUSES}", name="ck_dcb_bills_quality_valid"),
        CheckConstraint(
            f"considered IS NULL OR considered IN {DCB_BILL_REVIEW_DECISIONS}",
            name="ck_dcb_bills_considered_valid",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    batch_id = Column(Integer, ForeignKey("delayed_cash_upload_batches.id"), nullable=False, index=True)

    centre_code = Column(String, nullable=False, index=True)
    centre_name = Column(String, nullable=False)

    # ---- raw source columns, preserved exactly as uploaded ----
    sales_bill = Column(String, nullable=False)
    bill_date = Column(Date, nullable=False)
    bill_created_time = Column(DateTime(timezone=True), nullable=False)
    created_date = Column(Date, nullable=False)
    source_day_difference = Column(Integer, nullable=False)
    center_remarks = Column(Text, nullable=True)
    # Historical/back-filled uploads may already carry a
    # "Considered - ..." / "Not Considered - ..." verdict; a fresh weekly
    # upload will leave this null until the response workflow decides it.
    penalty_remarks = Column(Text, nullable=True)

    # ---- derived columns, computed at ingest, never overwriting the above ----
    calculated_day_difference = Column(Integer, nullable=False)
    difference_check = Column(String, nullable=False, default="match")
    data_quality_status = Column(String, nullable=False, default="ok")
    # per-bill penalty = calculated_day_difference x rule.rate_per_day
    calculated_penalty = Column(Numeric(10, 2), nullable=False)
    # The review verdict, one of DCB_BILL_REVIEW_DECISIONS, or null = not yet
    # reviewed. Only "considered" (excluded from validated_penalty) and
    # "not_considered" (counted) are TERMINAL -- recompute_validated_penalty
    # treats "needs_more_detail"/"needs_proof" the same as null (not ready
    # yet), since both mean the center still owes something before this bill
    # can be finally decided. Distinct from penalty_remarks (the free-text
    # reason) -- this is the structured verdict Vigilance sets, one bill at a
    # time, from the review queue.
    considered = Column(String, nullable=True)
    reviewed_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    batch = relationship("DelayedCashUploadBatch", back_populates="bills")
    reviewed_by = relationship("User", foreign_keys=[reviewed_by_id])


class DelayedCashCenterPenalty(Base):
    """One center's aggregate penalty for one upload batch -- the same
    granularity as the reference workbook's Penalty Data / Final penalty
    sheets. calculated_penalty is written once at publishing and never
    overwritten; validated_penalty and final_penalty are separate fields
    filled in later in the workflow, per the two-stage distinction proven in
    the formula analysis doc."""

    __tablename__ = "delayed_cash_center_penalties"
    __table_args__ = (
        UniqueConstraint("batch_id", "centre_code", name="uq_dcb_center_penalties_batch_centre"),
        CheckConstraint(f"penalty_status IN {DCB_PENALTY_STATUSES}", name="ck_dcb_center_penalties_status_valid"),
    )

    id = Column(Integer, primary_key=True, index=True)
    batch_id = Column(Integer, ForeignKey("delayed_cash_upload_batches.id"), nullable=False, index=True)

    centre_code = Column(String, nullable=False, index=True)
    centre_name = Column(String, nullable=False)
    total_bills = Column(Integer, nullable=False)

    # Publishing stage -- sum over ALL bills, regardless of remark status.
    calculated_penalty = Column(Numeric(14, 2), nullable=False)

    # Post-remark-validation stage -- sum over Not-Considered bills only.
    # Null until every bill in this center has a "considered" verdict.
    validated_penalty = Column(Numeric(14, 2), nullable=True)

    # External input -- 6.25% of the responsible person's monthly gross
    # salary component. Null means "not yet configured", never defaulted to
    # validated_penalty or to 0.
    monthly_cap_amount = Column(Numeric(14, 2), nullable=True)

    # min(validated_penalty, monthly_cap_amount) once both are known.
    final_penalty = Column(Numeric(14, 2), nullable=True)

    penalty_status = Column(String, nullable=False, default="published")

    # Public, unauthenticated response-portal access -- a center manager
    # opens {FRONTEND_URL}/respond/delayed-cash/{response_token} from the
    # notification email, with no CARVMS login. Single-use-per-case token,
    # not tied to a CARVMS user account. expires_at is informational (marks
    # the 48h TAT boundary) -- a late submission is still accepted and
    # recorded as overdue, never silently rejected, since Vigilance still
    # reviews it manually either way.
    response_token = Column(String, unique=True, nullable=True, index=True)
    response_token_expires_at = Column(DateTime(timezone=True), nullable=True)

    # Set once an escalation SMS has actually gone out for this case's
    # deadline having passed with no response -- see escalation_alert_service.
    # Never reset: a center that later DOES respond keeps this set, since
    # the alert already fired and re-alerting on the same deadline would be
    # noise. Genuinely distinct from response_token_expires_at (that's the
    # deadline itself; this is "did we already tell someone it passed").
    escalation_sms_sent_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    batch = relationship("DelayedCashUploadBatch", back_populates="center_penalties")
    responses = relationship(
        "DelayedCashCaseResponse", back_populates="center_penalty", cascade="all, delete-orphan"
    )


class DelayedCashCaseResponse(Base):
    """One center's submission through the public response portal --
    name/NPID/reason are mandatory per the requirement; evidence is
    mandatory too (enforced both client-side and here, never trusted from
    the client alone). Append-only: a center may submit more than once
    (e.g. after Vigilance asks for further proof), so this is never
    updated in place -- each submission is its own row, oldest to newest."""

    __tablename__ = "delayed_cash_case_responses"

    id = Column(Integer, primary_key=True, index=True)
    center_penalty_id = Column(
        Integer, ForeignKey("delayed_cash_center_penalties.id"), nullable=False, index=True
    )

    responder_name = Column(String, nullable=False)
    responder_npid = Column(String, nullable=False)
    # Mandatory per the requirement -- also the raw input to the contact-
    # change-request workflow (see org.OrgNodeContactChangeRequest): this
    # value is proposed for the center's OrgNode.manager_email, never written
    # there directly, only after an Admin approves it. Nullable at the DB
    # layer (historical/test rows predate this field) -- the API layer is
    # what actually enforces "mandatory" for new submissions.
    responder_email = Column(String, nullable=True)
    reason = Column(Text, nullable=False)

    # The center the responder picked from the Center Code/Name dropdowns
    # (sourced from the Org Master's center directory), independent of the
    # case's own centre_code derived from the token. Stored so a mismatch
    # is visible to Vigilance -- e.g. a wrong link, or a manager filling in
    # on behalf of the wrong center -- rather than silently trusting either
    # side. NOT required to equal center_penalty.centre_code.
    selected_center_code = Column(String, nullable=True)
    selected_center_name = Column(String, nullable=True)

    # Mandatory evidence attachment -- mirrors the metadata-only storage
    # pattern used by app/models/evidence.py (never a DB blob).
    evidence_original_filename = Column(String, nullable=False)
    evidence_mime_type = Column(String, nullable=False)
    evidence_size_bytes = Column(Integer, nullable=False)
    evidence_checksum = Column(String, nullable=False)
    evidence_storage_path = Column(String, nullable=False)

    submitted_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    # Whether this submission landed before or after the case's TAT deadline
    # -- computed once at submission time and stored, so it never changes
    # retroactively if the deadline field is later adjusted.
    was_within_tat = Column(String, nullable=True)  # "within_window" | "overdue" | unknown (None)

    # ---- auto-validation (advisory only -- see app/models/auto_validation.py) ----
    # Set by auto_validation_service.evaluate_remark() against `reason` above,
    # either right after submission or on a later manual re-run. Never sets
    # DelayedCashBill.considered and never feeds the penalty calculation --
    # Vigilance's own review-queue click remains the only official decision.
    auto_bucket = Column(String, nullable=True)  # "considered" | "not_considered" | "manual_check"
    auto_category = Column(String, nullable=True)
    auto_matched_keyword = Column(String, nullable=True)
    auto_decision_label = Column(String, nullable=True)
    auto_reason = Column(Text, nullable=True)  # only populated for not_considered
    auto_evaluated_at = Column(DateTime(timezone=True), nullable=True)

    # Vigilance can override the auto bucket from the Auto Validation tab --
    # kept as a SEPARATE set of columns (never overwrites auto_bucket itself)
    # so the original auto result stays visible for reporting even after a
    # human corrects it. See auto_validation_service.override_dcb_response,
    # which also writes an AuditLog row for the before/after trail.
    admin_override_bucket = Column(String, nullable=True)
    admin_override_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    admin_override_at = Column(DateTime(timezone=True), nullable=True)
    admin_override_note = Column(Text, nullable=True)

    center_penalty = relationship("DelayedCashCenterPenalty", back_populates="responses")
    admin_override_by = relationship("User", foreign_keys=[admin_override_by_id])


class DelayedCashCenterActivity(Base):
    """Every time a center manager's browser touches the public portal --
    "opened" (viewed a case, via either access path) or "submitted" (filed
    a response) -- logged even when they never act on what they open, per
    the requirement to see everything a center browsed, not just what it
    acted on. Deliberately append-only, no update/delete path -- this is
    an activity trail, not mutable state."""

    __tablename__ = "delayed_cash_center_activity"
    __table_args__ = (
        CheckConstraint(f"event_type IN {DCB_ACTIVITY_EVENT_TYPES}", name="ck_dcb_activity_event_type_valid"),
    )

    id = Column(Integer, primary_key=True, index=True)
    centre_code = Column(String, nullable=False, index=True)
    centre_name = Column(String, nullable=True)
    # Nullable: an "opened" event from the single-shared-link centre-code
    # lookup (before any specific case is chosen) has no one case yet if
    # the center has none open -- still worth logging that they looked.
    center_penalty_id = Column(
        Integer, ForeignKey("delayed_cash_center_penalties.id"), nullable=True, index=True
    )
    event_type = Column(String, nullable=False)
    occurred_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    center_penalty = relationship("DelayedCashCenterPenalty")

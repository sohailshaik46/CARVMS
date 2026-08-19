from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, EmailStr, Field


class DelayedCashRuleOut(BaseModel):
    id: int
    rule_version: str
    rate_per_day: Decimal
    monthly_cap_percentage: Decimal
    status: str
    effective_from: datetime

    model_config = {"from_attributes": True}


class DelayedCashCenterPenaltyOut(BaseModel):
    id: int
    batch_id: int
    centre_code: str
    centre_name: str
    total_bills: int
    calculated_penalty: Decimal
    validated_penalty: Optional[Decimal]
    monthly_cap_amount: Optional[Decimal]
    final_penalty: Optional[Decimal]
    penalty_status: str
    created_at: datetime
    # Read-only passthrough of this center's own response-portal link, if
    # one has ever been minted (via Publish links) -- lets the "View
    # centers" table show/copy each center's link directly, without a
    # separate endpoint or re-minting anything. Null until Publish links
    # has been used at least once for this batch.
    response_token: Optional[str] = None
    response_token_expires_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class ResponseLinkOut(BaseModel):
    response_token: str
    response_url: str
    expires_at: datetime


# ---------- upload + publishing pipeline ----------


class UploadBatchOut(BaseModel):
    id: int
    period_start: date
    period_end: date
    source_filename: str
    status: str
    uploaded_at: datetime

    model_config = {"from_attributes": True}


class SkippedBillRowOut(BaseModel):
    row_number: int
    reason: str


class UploadBatchResultOut(BaseModel):
    batch: UploadBatchOut
    center_penalties: list[DelayedCashCenterPenaltyOut]
    # Rows whose own BILLDATE fell outside this batch's period_start/
    # period_end -- excluded from ingestion (already covered by a prior
    # week's upload), never added to skipped_rows since this is an
    # expected exclusion, not a data error. Mirrors WRC's identical field.
    out_of_period_row_count: int = 0
    skipped_rows: list[SkippedBillRowOut]


class DcbBatchSummaryOut(BaseModel):
    """KPI-style aggregate for one batch -- mirrors WRC's BatchSummaryOut,
    adapted to DCB's own decision model."""

    batch: UploadBatchOut
    total_bills: int
    pending_review_count: int
    considered_count: int
    not_considered_count: int
    needs_more_detail_count: int
    needs_proof_count: int
    centers_in_batch: int
    total_calculated_penalty: Decimal
    total_validated_penalty: Decimal


class DcbCenterBreakdownOut(BaseModel):
    """One center's presence in this batch, with zone/cluster (resolved via
    the Org Master -- "Unknown" for a center not yet linked there) and
    all-time repeat-non-compliance + considered/not-considered history."""

    centre_code: str
    centre_name: str
    zone: Optional[str]
    cluster: Optional[str]
    this_batch_bill_count: int
    this_batch_considered_count: int
    this_batch_not_considered_count: int
    this_batch_pending_count: int
    all_time_batch_count: int
    all_time_considered_count: int
    all_time_not_considered_count: int


class ResponseLinkDetailOut(BaseModel):
    center_penalty_id: int
    centre_code: str
    centre_name: str
    response_token: str
    response_url: str
    expires_at: datetime


class BatchPublishResultOut(BaseModel):
    batch_id: int
    links: list[ResponseLinkDetailOut]


# ---------- public response portal (no auth) ----------


class PublicBillSummaryOut(BaseModel):
    """One bill in the case, shown to the center so they know exactly
    which bill(s) they're being asked to explain -- a bare total count
    left them guessing which specific sales bill needed a remark."""

    sales_bill: str
    bill_date: date
    calculated_day_difference: int
    calculated_penalty: Decimal
    considered: Optional[str]


class PublicCaseOut(BaseModel):
    centre_code: str
    centre_name: str
    period_start: date
    period_end: date
    total_bills: int
    calculated_penalty: Decimal
    tat_status: str
    deadline: Optional[datetime]
    already_responded: bool
    bills: list[PublicBillSummaryOut] = []


class PublicOpenCaseOut(PublicCaseOut):
    """Same shape as PublicCaseOut, plus the case's own id -- needed by the
    single shared link (no token) so the responder's browser has something
    to submit against once they've picked their center."""

    id: int


class CaseResponseSubmit(BaseModel):
    responder_name: str = Field(min_length=1, max_length=200)
    responder_npid: str = Field(min_length=1, max_length=50)
    responder_email: EmailStr
    reason: str = Field(min_length=1, max_length=5000)
    selected_center_code: Optional[str] = None
    selected_center_name: Optional[str] = None


class CaseResponseOut(BaseModel):
    id: int
    responder_name: str
    responder_npid: str
    responder_email: Optional[str]
    reason: str
    evidence_original_filename: str
    submitted_at: datetime
    was_within_tat: Optional[str]
    selected_center_code: Optional[str]
    selected_center_name: Optional[str]

    model_config = {"from_attributes": True}


class CenterActivityOut(BaseModel):
    id: int
    centre_code: str
    centre_name: Optional[str]
    center_penalty_id: Optional[int]
    event_type: str
    occurred_at: datetime

    model_config = {"from_attributes": True}


# ---------- bill review queue ----------


class BillOut(BaseModel):
    id: int
    batch_id: int
    centre_code: str
    centre_name: str
    sales_bill: str
    bill_date: date
    calculated_day_difference: int
    calculated_penalty: Decimal
    considered: Optional[str]
    reviewed_at: Optional[datetime]
    # Not a real column on DelayedCashBill (the bill<->case link is by
    # batch_id+centre_code, no FK) -- populated by the API layer so the
    # frontend can fetch this bill's case responses/evidence without a
    # second lookup round-trip.
    center_penalty_id: Optional[int] = None

    model_config = {"from_attributes": True}


class BillReviewIn(BaseModel):
    decision: str = Field(description="One of: considered, not_considered, needs_more_detail, needs_proof")


class BillReviewOut(BaseModel):
    bill: BillOut
    # Populated only for needs_more_detail/needs_proof -- a fresh (or
    # refreshed) per-case link, in case Vigilance wants to copy/send it
    # manually instead of (or in addition to) using POST .../notify.
    response_link: Optional[ResponseLinkDetailOut] = None


class BillNotifyIn(BaseModel):
    # Required for needs_more_detail/needs_proof (Vigilance's own typed
    # remark, emailed to the center alongside a fresh response link);
    # ignored for considered/not_considered, which send a fixed notice.
    comment: Optional[str] = None


class BillNotifyOut(BaseModel):
    sent: bool
    reason: Optional[str] = None


class DcbRemoteSyncReportOut(BaseModel):
    rules_created: int
    rules_updated: int
    rules_unchanged: int
    batches_created: int
    batches_updated: int
    batches_unchanged: int
    bills_created: int
    bills_updated: int
    bills_unchanged: int
    center_penalties_created: int
    center_penalties_updated: int
    center_penalties_unchanged: int
    changed_summary: list[str]
    committed: bool
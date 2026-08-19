from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, EmailStr, Field


class WeeklyRevenueClosureRuleOut(BaseModel):
    id: int
    rule_version: str
    penalty_rate: Decimal
    status: str
    effective_from: datetime

    model_config = {"from_attributes": True}


class WeeklyRevenueClosureBatchOut(BaseModel):
    id: int
    period_start: date
    period_end: date
    week_label: str
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class BillIncidentOut(BaseModel):
    id: int
    batch_id: int
    centre_code: str
    centre_name: str
    zone: Optional[str]
    cluster: Optional[str]
    zonal_manager: Optional[str]
    center_manager: Optional[str]
    center_manager_npid: Optional[str]
    incident_date: date
    mis_final_remark: str
    raw_remark: Optional[str]
    center_remarks: Optional[str]
    penalty_remarks: Optional[str]
    considered: Optional[str]
    reviewed_at: Optional[datetime]
    # Not a real column on WeeklyRevenueBillIncident (mirrors DCB's
    # BillOut.center_penalty_id) -- populated by the API layer from
    # WeeklyRevenueCenterCase, when one has been minted for this
    # batch+centre_code. Null until Vigilance (or a center opening the
    # single shared link) first triggers a case/link.
    case_id: Optional[int] = None

    model_config = {"from_attributes": True}


class SkippedPendingRowOut(BaseModel):
    row_number: int
    reason: str


class UploadBatchResultOut(BaseModel):
    batch: WeeklyRevenueClosureBatchOut
    incidents_ingested: int
    excess_billed_row_count: int
    # Rows whose own Date fell outside this batch's period_start/
    # period_end -- the source file repeatedly turned out to still carry
    # a prior week's rows too; those are excluded here rather than
    # double-counted against the wrong week (see
    # weekly_revenue_closure_upload_service.parse_pending_workbook).
    out_of_period_row_count: int = 0
    skipped_rows: list[SkippedPendingRowOut]


class BillReviewIn(BaseModel):
    decision: str = Field(description="'considered' or 'not_considered'")
    center_remarks: Optional[str] = None


class NoRemarkIncidentOut(BaseModel):
    id: int
    batch_id: int
    centre_code: str
    centre_name: str
    incident_type: str
    incident_count: int

    model_config = {"from_attributes": True}


class CenterPenaltyOut(BaseModel):
    id: int
    batch_id: int
    centre_code: str
    centre_name: str
    center_manager: Optional[str]
    center_manager_npid: Optional[str]
    not_considered_penalty: Decimal
    no_remark_penalty: Decimal

    model_config = {"from_attributes": True}


class RolePenaltyOut(BaseModel):
    id: int
    batch_id: int
    role: str
    section: str
    person_name: str
    person_npid: Optional[str]
    distinct_center_count: int
    penalty_amount: Decimal

    model_config = {"from_attributes": True}


class CloseBatchResultOut(BaseModel):
    batch: WeeklyRevenueClosureBatchOut
    center_penalties: list[CenterPenaltyOut]
    role_penalties: list[RolePenaltyOut]


class BatchSummaryOut(BaseModel):
    """KPI-style aggregate for one batch -- powers the dashboard without
    the frontend needing to re-derive totals from raw rows."""

    batch: WeeklyRevenueClosureBatchOut
    total_incidents: int
    pending_review_count: int
    considered_count: int
    not_considered_count: int
    no_remark_center_count: int
    centers_penalized: int
    total_center_penalty_rate: Decimal
    total_role_penalty_rate: Decimal


class CenterBreakdownOut(BaseModel):
    """One center's presence in this batch, enriched with all-time history
    for the repeat-non-compliance and considered/not-considered totals --
    powers the "View centers" screen's raw table and its By Cluster/By Zone
    rollups (computed client-side from this same list)."""

    centre_code: str
    centre_name: str
    zone: Optional[str]
    cluster: Optional[str]
    zonal_manager: Optional[str]
    this_batch_incident_count: int
    this_batch_considered_count: int
    this_batch_not_considered_count: int
    this_batch_pending_count: int
    all_time_batch_count: int
    all_time_considered_count: int
    all_time_not_considered_count: int
    # Read-only passthrough of this center's own response-portal link for
    # this batch, if one has ever been minted -- see the identical
    # comment on the CenterBreakdown dataclass this is built from.
    response_token: Optional[str] = None
    response_token_expires_at: Optional[datetime] = None


# ---------- response portal (mirrors app/schemas/delayed_cash_billing.py) ----------


class ResponseLinkDetailOut(BaseModel):
    case_id: int
    centre_code: str
    centre_name: str
    response_token: str
    response_url: str
    expires_at: datetime


class BatchPublishResultOut(BaseModel):
    batch_id: int
    links: list[ResponseLinkDetailOut]


class PublicIncidentSummaryOut(BaseModel):
    """One incident in the case, shown to the center so they know exactly
    which incident(s) they're being asked to explain -- mirrors DCB's
    PublicBillSummaryOut for the same reason."""

    incident_date: date
    mis_final_remark: str
    raw_remark: Optional[str]
    considered: Optional[str]


class PublicCaseOut(BaseModel):
    centre_code: str
    centre_name: str
    period_start: date
    period_end: date
    week_label: str
    pending_incident_count: int
    tat_status: str
    deadline: Optional[datetime]
    already_responded: bool
    incidents: list[PublicIncidentSummaryOut] = []


class PublicOpenCaseOut(PublicCaseOut):
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
    case_id: Optional[int]
    event_type: str
    occurred_at: datetime

    model_config = {"from_attributes": True}


class IncidentReviewOut(BaseModel):
    incident: BillIncidentOut
    response_link: Optional[ResponseLinkDetailOut] = None


class IncidentNotifyIn(BaseModel):
    comment: Optional[str] = None


class IncidentNotifyOut(BaseModel):
    sent: bool
    reason: Optional[str] = None


class WrcRemoteSyncReportOut(BaseModel):
    rules_created: int
    rules_updated: int
    rules_unchanged: int
    batches_created: int
    batches_updated: int
    batches_unchanged: int
    bill_incidents_created: int
    bill_incidents_updated: int
    bill_incidents_unchanged: int
    no_remark_incidents_created: int
    no_remark_incidents_updated: int
    no_remark_incidents_unchanged: int
    center_penalties_created: int
    center_penalties_updated: int
    center_penalties_unchanged: int
    role_penalties_created: int
    role_penalties_updated: int
    role_penalties_unchanged: int
    center_cases_created: int
    center_cases_updated: int
    center_cases_unchanged: int
    changed_summary: list[str]
    committed: bool

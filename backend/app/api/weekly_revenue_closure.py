"""Weekly Revenue Closure -- a deliberately separate engine from Delayed
Cash Billing (different formula, different role hierarchy: Center Manager
AND Cluster Manager penalties apply here). See
docs/CARVMS_WEEKLY_REVENUE_CLOSURE_FORMULA_ANALYSIS.md for the proof this
was built against.
"""

from datetime import date

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from sqlalchemy.orm import Session

from app.auth import roles
from app.auth.dependencies import require_role
from app.config.settings import settings
from app.database.database import get_db
from app.models.user import User
from app.models.weekly_revenue_closure import (
    WeeklyRevenueBillIncident,
    WeeklyRevenueCaseResponse,
    WeeklyRevenueCenterCase,
)
from app.schemas.weekly_revenue_closure import (
    BatchPublishResultOut,
    BatchSummaryOut,
    BillIncidentOut,
    BillReviewIn,
    CaseResponseOut,
    CenterActivityOut,
    CenterBreakdownOut,
    CenterPenaltyOut,
    CloseBatchResultOut,
    IncidentNotifyIn,
    IncidentNotifyOut,
    NoRemarkIncidentOut,
    ResponseLinkDetailOut,
    RolePenaltyOut,
    SkippedPendingRowOut,
    UploadBatchResultOut,
    WeeklyRevenueClosureBatchOut,
    WeeklyRevenueClosureRuleOut,
)
from app.services import storage_service
from app.services import weekly_revenue_closure_export_service as export_service
from app.services import weekly_revenue_closure_service as calc_service
from app.services import weekly_revenue_closure_upload_service as upload_service
from app.services import weekly_revenue_notification_service as notification_service
from app.services import weekly_revenue_response_service as response_service

router = APIRouter(prefix="/weekly-revenue-closure", tags=["Weekly Revenue Closure"])

# Same "Vigilance-equivalent" gate as Delayed Cash Billing, for the same
# reason -- no dedicated Vigilance role exists yet.
VIGILANCE_ROLES = (roles.ADMIN, roles.AUDITOR)


def _get_batch_or_404(db: Session, batch_id: int):
    batch = calc_service.get_batch(db, batch_id)
    if batch is None:
        raise HTTPException(status_code=404, detail="Batch not found")
    return batch


def _get_incident_or_404(db: Session, incident_id: int) -> WeeklyRevenueBillIncident:
    try:
        return calc_service.get_bill_incident_or_raise(db, incident_id)
    except calc_service.BillIncidentNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


def _get_case_or_404(db: Session, case_id: int) -> WeeklyRevenueCenterCase:
    case = db.query(WeeklyRevenueCenterCase).filter(WeeklyRevenueCenterCase.id == case_id).first()
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")
    return case


def _incidents_with_case_ids(db: Session, incidents: list[WeeklyRevenueBillIncident]) -> list[BillIncidentOut]:
    """A WRC incident has no FK to its case -- the link is (batch_id,
    centre_code), same non-relationship as DCB's bill<->center_penalty --
    mirrors _bills_with_center_penalty_ids in app/api/delayed_cash.py."""
    if not incidents:
        return []
    pairs = {(i.batch_id, i.centre_code) for i in incidents}
    cases = (
        db.query(WeeklyRevenueCenterCase)
        .filter(
            WeeklyRevenueCenterCase.batch_id.in_({p[0] for p in pairs}),
            WeeklyRevenueCenterCase.centre_code.in_({p[1] for p in pairs}),
        )
        .all()
    )
    id_by_pair = {(c.batch_id, c.centre_code): c.id for c in cases}
    return [
        BillIncidentOut(
            **BillIncidentOut.model_validate(i).model_dump(exclude={"case_id"}),
            case_id=id_by_pair.get((i.batch_id, i.centre_code)),
        )
        for i in incidents
    ]


@router.get("/rules/active", response_model=WeeklyRevenueClosureRuleOut)
def get_active_rule(db: Session = Depends(get_db), _user: User = Depends(require_role(*VIGILANCE_ROLES))):
    try:
        return calc_service.get_active_rule(db)
    except calc_service.NoApprovedRuleError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/rules/activate-default", response_model=WeeklyRevenueClosureRuleOut)
def activate_default_rule(db: Session = Depends(get_db), user: User = Depends(require_role(roles.ADMIN))):
    """Creates AND approves the proven-default rule in one step if none is
    active yet -- idempotent, returns the existing rule if one already is.
    See weekly_revenue_closure_service.activate_default_rule for why this
    doesn't weaken the versioned-rule governance model."""
    return calc_service.activate_default_rule(db, actor=user)


@router.get("/batches", response_model=list[WeeklyRevenueClosureBatchOut])
def list_batches(db: Session = Depends(get_db), _user: User = Depends(require_role(*VIGILANCE_ROLES))):
    return calc_service.list_batches(db)


@router.get("/batches/{batch_id}", response_model=WeeklyRevenueClosureBatchOut)
def get_batch(
    batch_id: int, db: Session = Depends(get_db), _user: User = Depends(require_role(*VIGILANCE_ROLES))
):
    return _get_batch_or_404(db, batch_id)


@router.delete("/batches/{batch_id}", status_code=204)
def delete_batch(
    batch_id: int, db: Session = Depends(get_db), _user: User = Depends(require_role(*VIGILANCE_ROLES))
):
    """Deletes a closure batch and everything computed from it (incidents,
    center/role penalties, center cases, case responses + their evidence
    files on disk, centers activity) -- lets Vigilance correct a bad upload
    by deleting and re-uploading rather than being stuck with it. See
    weekly_revenue_closure_service.delete_batch for the exact deletion order
    and why it can't just rely on ORM cascade."""
    batch = _get_batch_or_404(db, batch_id)
    calc_service.delete_batch(db, batch=batch)


@router.get("/batches/{batch_id}/summary", response_model=BatchSummaryOut)
def get_batch_summary(
    batch_id: int, db: Session = Depends(get_db), _user: User = Depends(require_role(*VIGILANCE_ROLES))
):
    """KPI aggregate for the dashboard -- one number, computed once (see
    weekly_revenue_closure_service.get_batch_summary)."""
    batch = _get_batch_or_404(db, batch_id)
    summary = calc_service.get_batch_summary(db, batch=batch)
    return BatchSummaryOut(batch=WeeklyRevenueClosureBatchOut.model_validate(batch), **summary.__dict__)


@router.get("/batches/{batch_id}/centers-breakdown", response_model=list[CenterBreakdownOut])
def get_batch_centers_breakdown(
    batch_id: int, db: Session = Depends(get_db), _user: User = Depends(require_role(*VIGILANCE_ROLES))
):
    """Every center with an incident in this batch, with zone/cluster (read
    straight off the incident rows) plus all-time repeat-non-compliance and
    considered/not-considered history -- see
    weekly_revenue_closure_service.get_batch_centers_breakdown."""
    batch = _get_batch_or_404(db, batch_id)
    breakdown = calc_service.get_batch_centers_breakdown(db, batch=batch)
    return [CenterBreakdownOut(**b.__dict__) for b in breakdown]


@router.post("/batches/upload", response_model=UploadBatchResultOut, status_code=201)
async def upload_batch(
    period_start: date = Form(...),
    period_end: date = Form(...),
    week_label: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_role(*VIGILANCE_ROLES)),
):
    """Uploads the weekly "closure pending list" workbook (the `Center
    wise` sheet -- see the upload service's own docstring for the proven
    format) and ingests every penalty-eligible incident as PENDING (no
    remark or verdict yet -- see the Review Queue endpoints below). The
    "Excess billed/Incorrect Daily report" category is parsed, counted,
    and reported, but never turned into a penalty-eligible incident --
    proven out of scope for this engine."""
    try:
        rule = calc_service.get_active_rule(db)
    except calc_service.NoApprovedRuleError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    raw = await file.read()
    try:
        raw_incidents, excess_billed_count, skipped = upload_service.parse_pending_workbook(raw)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    batch = calc_service.create_batch(
        db, period_start=period_start, period_end=period_end, week_label=week_label, rule=rule, created_by=user,
    )
    created = calc_service.record_bill_incidents(db, batch=batch, raw_incidents=raw_incidents)

    return UploadBatchResultOut(
        batch=WeeklyRevenueClosureBatchOut.model_validate(batch),
        incidents_ingested=len(created),
        excess_billed_row_count=excess_billed_count,
        skipped_rows=[SkippedPendingRowOut(row_number=s.row_number, reason=s.reason) for s in skipped],
    )


@router.post("/batches/{batch_id}/close", response_model=CloseBatchResultOut)
def close_batch(
    batch_id: int, db: Session = Depends(get_db), _user: User = Depends(require_role(*VIGILANCE_ROLES))
):
    """Finalizes the batch: computes every center's and role's penalty
    from whatever's been reviewed so far. Safe to call again after a late
    correction -- each call recomputes from scratch (see
    weekly_revenue_closure_service.close_batch)."""
    batch = _get_batch_or_404(db, batch_id)
    rule = calc_service.get_active_rule(db)
    batch, center_penalties, role_penalties = calc_service.close_batch(db, batch=batch, rule=rule)
    return CloseBatchResultOut(
        batch=WeeklyRevenueClosureBatchOut.model_validate(batch),
        center_penalties=[CenterPenaltyOut.model_validate(cp) for cp in center_penalties],
        role_penalties=[RolePenaltyOut.model_validate(rp) for rp in role_penalties],
    )


@router.get("/batches/{batch_id}/center-penalties", response_model=list[CenterPenaltyOut])
def list_center_penalties(
    batch_id: int, db: Session = Depends(get_db), _user: User = Depends(require_role(*VIGILANCE_ROLES))
):
    _get_batch_or_404(db, batch_id)
    from app.models.weekly_revenue_closure import WeeklyRevenueCenterPenalty

    return (
        db.query(WeeklyRevenueCenterPenalty)
        .filter(WeeklyRevenueCenterPenalty.batch_id == batch_id)
        .order_by(WeeklyRevenueCenterPenalty.centre_name)
        .all()
    )


@router.get("/batches/{batch_id}/role-penalties", response_model=list[RolePenaltyOut])
def list_role_penalties(
    batch_id: int, db: Session = Depends(get_db), _user: User = Depends(require_role(*VIGILANCE_ROLES))
):
    _get_batch_or_404(db, batch_id)
    from app.models.weekly_revenue_closure import WeeklyRevenueRolePenalty

    return (
        db.query(WeeklyRevenueRolePenalty)
        .filter(WeeklyRevenueRolePenalty.batch_id == batch_id)
        .order_by(WeeklyRevenueRolePenalty.person_name)
        .all()
    )


@router.get("/batches/{batch_id}/export.xlsx")
def export_batch_workbook(
    batch_id: int, db: Session = Depends(get_db), _user: User = Depends(require_role(*VIGILANCE_ROLES))
):
    """Regenerates the multi-sheet Penalty workbook from this batch's own
    data (see weekly_revenue_closure_export_service) -- never from a
    hand-maintained pivot, so it can't drift into the same arithmetic
    errors documented in the real Week 3 reference file."""
    batch = _get_batch_or_404(db, batch_id)
    content = export_service.generate_penalty_workbook(db, batch=batch)
    filename = f"{batch.week_label.replace(' ', '_').replace('/', '-')}-Penalty.xlsx"
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/batches/{batch_id}/no-remark-incidents", response_model=list[NoRemarkIncidentOut])
def list_no_remark_incidents(
    batch_id: int, db: Session = Depends(get_db), _user: User = Depends(require_role(*VIGILANCE_ROLES))
):
    _get_batch_or_404(db, batch_id)
    from app.models.weekly_revenue_closure import WeeklyRevenueNoRemarkIncident

    return (
        db.query(WeeklyRevenueNoRemarkIncident)
        .filter(WeeklyRevenueNoRemarkIncident.batch_id == batch_id)
        .order_by(WeeklyRevenueNoRemarkIncident.centre_name)
        .all()
    )


# ---------------------------------------------------------------------------
# Review queue -- one incident at a time, mirroring the pattern already
# built for Delayed Cash Billing.
# ---------------------------------------------------------------------------


@router.get("/bills/review-queue", response_model=list[BillIncidentOut])
def get_review_queue(
    batch_id: int | None = None,
    db: Session = Depends(get_db),
    _user: User = Depends(require_role(*VIGILANCE_ROLES)),
):
    """Every remark-received incident still awaiting a Vigilance verdict."""
    return _incidents_with_case_ids(db, calc_service.list_bill_incidents(db, batch_id=batch_id, pending_only=True))


@router.get("/bills/action-taken", response_model=list[BillIncidentOut])
def get_action_taken(
    batch_id: int | None = None,
    db: Session = Depends(get_db),
    _user: User = Depends(require_role(*VIGILANCE_ROLES)),
):
    """Every incident with a terminal considered/not_considered verdict --
    the "Action Taken" log, complementing the pending review queue."""
    return _incidents_with_case_ids(db, calc_service.list_bill_incidents_action_taken(db, batch_id=batch_id))


@router.post("/bills/{incident_id}/review", response_model=BillIncidentOut)
def review_bill_incident(
    incident_id: int,
    payload: BillReviewIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(*VIGILANCE_ROLES)),
):
    incident = _get_incident_or_404(db, incident_id)
    try:
        incident = calc_service.set_bill_incident_review(
            db, incident=incident, decision=payload.decision, center_remarks=payload.center_remarks, reviewed_by=user,
        )
    except calc_service.InvalidReviewDecisionError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return _incidents_with_case_ids(db, [incident])[0]


@router.post("/bills/{incident_id}/revoke-review", response_model=BillIncidentOut)
def revoke_bill_incident_review(
    incident_id: int,
    db: Session = Depends(get_db),
    _user: User = Depends(require_role(*VIGILANCE_ROLES)),
):
    """Undoes a mistaken Considered/Not Considered click -- clears the
    verdict so the incident drops back out of Action Taken and back into
    the Review Queue for a fresh decision. 400s if the incident was never
    reviewed (nothing to undo). Mirrors DCB's revoke_bill_review exactly."""
    incident = _get_incident_or_404(db, incident_id)
    try:
        incident = calc_service.revoke_bill_incident_review(db, incident=incident)
    except calc_service.BillIncidentNotReviewedError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return _incidents_with_case_ids(db, [incident])[0]


@router.post("/bills/{incident_id}/mark-no-remark-received", response_model=NoRemarkIncidentOut)
def mark_no_remark_received(
    incident_id: int, db: Session = Depends(get_db), _user: User = Depends(require_role(*VIGILANCE_ROLES))
):
    """For a pending incident whose center never responded -- moves it
    into the "Remarks Not Received" section without deleting the original
    ingested row (kept as the audit trail)."""
    incident = _get_incident_or_404(db, incident_id)
    return calc_service.mark_no_remark_received(db, incident=incident)


# ---------------------------------------------------------------------------
# Response portal (Vigilance side) + Centers Activity + notifications --
# mirrors the equivalent section of app/api/delayed_cash.py.
# ---------------------------------------------------------------------------


@router.get("/batches/{batch_id}/links", response_model=BatchPublishResultOut)
def get_links_for_batch(
    batch_id: int,
    db: Session = Depends(get_db),
    _user: User = Depends(require_role(*VIGILANCE_ROLES)),
):
    """Read-only -- returns whichever centers in this batch already have a
    response-portal link, WITHOUT minting or invalidating anything (unlike
    publish-links below). Backs the Batches table's quick "View links"
    action, so copying a link doesn't require re-publishing (and doesn't
    invalidate every other center's already-shared link) just to look."""
    batch = _get_batch_or_404(db, batch_id)
    cases = response_service.get_published_links_for_batch(db, batch=batch)
    return BatchPublishResultOut(
        batch_id=batch.id,
        links=[
            ResponseLinkDetailOut(
                case_id=c.id,
                centre_code=c.centre_code,
                centre_name=c.centre_name,
                response_token=c.response_token,
                response_url=f"{settings.FRONTEND_URL}/respond/weekly-revenue/{c.response_token}",
                expires_at=c.response_token_expires_at,
            )
            for c in cases
        ],
    )


@router.post("/batches/{batch_id}/publish-links", response_model=BatchPublishResultOut)
def publish_links_for_batch(
    batch_id: int,
    db: Session = Depends(get_db),
    _user: User = Depends(require_role(*VIGILANCE_ROLES)),
):
    """Bulk-issues a fresh response-portal link for every center with an
    incident in this batch -- see weekly_revenue_response_service.
    mint_links_for_batch. Safe to call again; always mints fresh tokens."""
    batch = _get_batch_or_404(db, batch_id)
    cases = response_service.mint_links_for_batch(db, batch=batch)
    return BatchPublishResultOut(
        batch_id=batch.id,
        links=[
            ResponseLinkDetailOut(
                case_id=c.id,
                centre_code=c.centre_code,
                centre_name=c.centre_name,
                response_token=c.response_token,
                response_url=f"{settings.FRONTEND_URL}/respond/weekly-revenue/{c.response_token}",
                expires_at=c.response_token_expires_at,
            )
            for c in cases
        ],
    )


@router.post("/batches/{batch_id}/centers/{centre_code}/response-link", response_model=ResponseLinkDetailOut)
def generate_response_link(
    batch_id: int,
    centre_code: str,
    db: Session = Depends(get_db),
    _user: User = Depends(require_role(*VIGILANCE_ROLES)),
):
    """(Re)issues the public response-portal link for this center's case in
    this batch -- mints the case on first use. Share the returned URL with
    the center (e.g. in the notification email)."""
    batch = _get_batch_or_404(db, batch_id)
    incident = (
        db.query(WeeklyRevenueBillIncident)
        .filter(WeeklyRevenueBillIncident.batch_id == batch_id, WeeklyRevenueBillIncident.centre_code == centre_code)
        .first()
    )
    if incident is None:
        raise HTTPException(status_code=404, detail=f"No incidents found for {centre_code} in this batch")
    case = response_service.get_or_create_case(db, batch=batch, centre_code=centre_code, centre_name=incident.centre_name)
    case = response_service.generate_response_link_token(db, case=case)
    return ResponseLinkDetailOut(
        case_id=case.id,
        centre_code=case.centre_code,
        centre_name=case.centre_name,
        response_token=case.response_token,
        response_url=f"{settings.FRONTEND_URL}/respond/weekly-revenue/{case.response_token}",
        expires_at=case.response_token_expires_at,
    )


@router.get("/centers-activity", response_model=list[CenterActivityOut])
def get_centers_activity(
    batch_id: int | None = None,
    db: Session = Depends(get_db),
    _user: User = Depends(require_role(*VIGILANCE_ROLES)),
):
    return response_service.list_activity(db, batch_id=batch_id)


@router.get("/cases/{case_id}/responses", response_model=list[CaseResponseOut])
def get_case_responses(
    case_id: int,
    db: Session = Depends(get_db),
    _user: User = Depends(require_role(*VIGILANCE_ROLES)),
):
    case = _get_case_or_404(db, case_id)
    return response_service.list_responses(db, case=case)


@router.get("/cases/{case_id}/incidents", response_model=list[BillIncidentOut])
def get_case_incidents(
    case_id: int,
    db: Session = Depends(get_db),
    _user: User = Depends(require_role(*VIGILANCE_ROLES)),
):
    """Every incident tied to this case (batch_id + centre_code), reviewed
    or not -- backs the Auto Validation tab's "open the relevant incidents
    to reverify" click-through, since there's no direct FK from a case to
    its incidents (same batch_id+centre_code join as everywhere else)."""
    case = _get_case_or_404(db, case_id)
    return response_service.list_incidents_for_case(db, case=case)


@router.get("/case-responses/{response_id}/evidence")
def download_case_response_evidence(
    response_id: int,
    db: Session = Depends(get_db),
    _user: User = Depends(require_role(*VIGILANCE_ROLES)),
):
    case_response = db.query(WeeklyRevenueCaseResponse).filter(WeeklyRevenueCaseResponse.id == response_id).first()
    if case_response is None:
        raise HTTPException(status_code=404, detail="Response not found")
    path = storage_service.absolute_path_for(case_response.evidence_storage_path)
    return FileResponse(path, media_type=case_response.evidence_mime_type, filename=case_response.evidence_original_filename)


@router.post("/bills/{incident_id}/notify", response_model=IncidentNotifyOut)
def notify_incident(
    incident_id: int,
    _payload: IncidentNotifyIn,
    db: Session = Depends(get_db),
    _user: User = Depends(require_role(*VIGILANCE_ROLES)),
):
    """Emails the center about this incident's already-recorded decision.
    Always returns 200 with {sent, reason} -- see
    weekly_revenue_notification_service's module docstring."""
    incident = _get_incident_or_404(db, incident_id)
    try:
        result = notification_service.notify_incident_decision(db, incident=incident)
    except notification_service.InvalidNotifyRequestError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return IncidentNotifyOut(sent=result.sent, reason=result.reason)

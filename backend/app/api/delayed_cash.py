from datetime import date

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from sqlalchemy.orm import Session

from app.auth import roles
from app.auth.dependencies import require_role
from app.config.settings import settings
from app.database.database import get_db
from app.models.delayed_cash_billing import (
    DelayedCashBill,
    DelayedCashCaseResponse,
    DelayedCashCenterPenalty,
    DelayedCashUploadBatch,
)
from app.services import storage_service
from app.models.user import User
from app.schemas.delayed_cash_billing import (
    BatchPublishResultOut,
    BillNotifyIn,
    BillNotifyOut,
    BillOut,
    BillReviewIn,
    BillReviewOut,
    CaseResponseOut,
    CenterActivityOut,
    DelayedCashCenterPenaltyOut,
    DelayedCashRuleOut,
    ResponseLinkDetailOut,
    ResponseLinkOut,
    SkippedBillRowOut,
    UploadBatchOut,
    UploadBatchResultOut,
)
from app.services import delayed_cash_export_service as export_service
from app.services import delayed_cash_notification_service as notification_service
from app.services import delayed_cash_penalty_service as calc_service
from app.services import delayed_cash_response_service as response_service
from app.services import delayed_cash_upload_service as upload_service

router = APIRouter(prefix="/delayed-cash", tags=["Delayed Cash Billing"])

# Vigilance-equivalent access for now -- Admin and Auditor. Revisit once a
# dedicated Vigilance role exists (see docs/CARVMS_IMPLEMENTATION_PLAN.md).
VIGILANCE_ROLES = (roles.ADMIN, roles.AUDITOR)


def _get_center_penalty_or_404(db: Session, center_penalty_id: int) -> DelayedCashCenterPenalty:
    cp = (
        db.query(DelayedCashCenterPenalty)
        .filter(DelayedCashCenterPenalty.id == center_penalty_id)
        .first()
    )
    if cp is None:
        raise HTTPException(status_code=404, detail="Center penalty case not found")
    return cp


def _get_batch_or_404(db: Session, batch_id: int) -> DelayedCashUploadBatch:
    batch = db.query(DelayedCashUploadBatch).filter(DelayedCashUploadBatch.id == batch_id).first()
    if batch is None:
        raise HTTPException(status_code=404, detail="Upload batch not found")
    return batch


@router.get("/rules/active", response_model=DelayedCashRuleOut)
def get_active_rule(db: Session = Depends(get_db), _user: User = Depends(require_role(*VIGILANCE_ROLES))):
    try:
        return calc_service.get_active_rule(db)
    except calc_service.NoApprovedRuleError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/rules/activate-default", response_model=DelayedCashRuleOut)
def activate_default_rule(db: Session = Depends(get_db), user: User = Depends(require_role(roles.ADMIN))):
    """Creates AND approves the proven-default rule in one step if none is
    active yet -- idempotent, returns the existing rule if one already is.
    See delayed_cash_penalty_service.activate_default_rule for why this
    doesn't weaken the versioned-rule governance model."""
    return calc_service.activate_default_rule(db, actor=user)


@router.get("/batches", response_model=list[UploadBatchOut])
def list_batches(
    db: Session = Depends(get_db),
    _user: User = Depends(require_role(*VIGILANCE_ROLES)),
):
    return db.query(DelayedCashUploadBatch).order_by(DelayedCashUploadBatch.uploaded_at.desc()).all()


@router.get("/batches/{batch_id}", response_model=UploadBatchOut)
def get_batch(
    batch_id: int,
    db: Session = Depends(get_db),
    _user: User = Depends(require_role(*VIGILANCE_ROLES)),
):
    return _get_batch_or_404(db, batch_id)


@router.delete("/batches/{batch_id}", status_code=204)
def delete_batch(
    batch_id: int,
    db: Session = Depends(get_db),
    _user: User = Depends(require_role(*VIGILANCE_ROLES)),
):
    """Deletes an upload batch and everything computed from it (bills,
    center penalties, case responses + their evidence files on disk,
    centers activity) -- lets Vigilance correct a bad upload by deleting and
    re-uploading rather than being stuck with it. See
    delayed_cash_penalty_service.delete_batch for the exact deletion order
    and why it can't just rely on ORM cascade."""
    batch = _get_batch_or_404(db, batch_id)
    calc_service.delete_batch(db, batch=batch)


@router.get("/batches/{batch_id}/export.xlsx")
def export_batch_workbook(
    batch_id: int, db: Session = Depends(get_db), _user: User = Depends(require_role(*VIGILANCE_ROLES))
):
    """Regenerates the Data + Penalty workbook from this batch's own
    computed rows -- never from a hand-maintained pivot (see
    delayed_cash_export_service)."""
    batch = _get_batch_or_404(db, batch_id)
    content = export_service.generate_penalty_workbook(db, batch=batch)
    filename = f"delayed-cash-batch-{batch.id}-penalty.xlsx"
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/batches/upload", response_model=UploadBatchResultOut, status_code=201)
async def upload_batch_endpoint(
    period_start: date = Form(...),
    period_end: date = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_role(*VIGILANCE_ROLES)),
):
    """Upload the weekly 'Bills Data' workbook. Ingests every delayed bill,
    computes each one's penalty (day_difference x rate_per_day) via the
    already-proven calculator, and aggregates the publishing-stage total per
    center. A bad row (missing fields, unparseable date, duplicate sales
    bill) is skipped and reported -- never allowed to abort the whole
    batch."""
    try:
        rule = calc_service.get_active_rule(db)
    except calc_service.NoApprovedRuleError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    raw = await file.read()
    try:
        batch, center_penalties, skipped = upload_service.upload_batch(
            db,
            raw_bytes=raw,
            source_filename=file.filename or "upload.xlsx",
            period_start=period_start,
            period_end=period_end,
            rule=rule,
            uploaded_by=user,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return UploadBatchResultOut(
        batch=UploadBatchOut.model_validate(batch),
        center_penalties=[DelayedCashCenterPenaltyOut.model_validate(cp) for cp in center_penalties],
        skipped_rows=[SkippedBillRowOut(row_number=s.row_number, reason=s.reason) for s in skipped],
    )


@router.post("/batches/{batch_id}/publish", response_model=BatchPublishResultOut)
def publish_batch_endpoint(
    batch_id: int,
    db: Session = Depends(get_db),
    _user: User = Depends(require_role(*VIGILANCE_ROLES)),
):
    """Bulk-issues a fresh response-portal link for every center in this
    batch -- share the returned URLs in the notification run/email. Safe to
    call again; always mints fresh tokens, invalidating any previous
    links (same contract as the single-case endpoint below)."""
    batch = _get_batch_or_404(db, batch_id)
    center_penalties = upload_service.publish_batch(db, batch=batch)
    return BatchPublishResultOut(
        batch_id=batch.id,
        links=[
            ResponseLinkDetailOut(
                center_penalty_id=cp.id,
                centre_code=cp.centre_code,
                centre_name=cp.centre_name,
                response_token=cp.response_token,
                response_url=f"{settings.FRONTEND_URL}/respond/delayed-cash/{cp.response_token}",
                expires_at=cp.response_token_expires_at,
            )
            for cp in center_penalties
        ],
    )


@router.get("/center-penalties", response_model=list[DelayedCashCenterPenaltyOut])
def list_center_penalties(
    batch_id: int | None = None,
    db: Session = Depends(get_db),
    _user: User = Depends(require_role(*VIGILANCE_ROLES)),
):
    query = db.query(DelayedCashCenterPenalty)
    if batch_id is not None:
        query = query.filter(DelayedCashCenterPenalty.batch_id == batch_id)
    return query.order_by(DelayedCashCenterPenalty.centre_name).all()


@router.get("/center-penalties/{center_penalty_id}", response_model=DelayedCashCenterPenaltyOut)
def get_center_penalty(
    center_penalty_id: int,
    db: Session = Depends(get_db),
    _user: User = Depends(require_role(*VIGILANCE_ROLES)),
):
    return _get_center_penalty_or_404(db, center_penalty_id)


@router.post("/center-penalties/{center_penalty_id}/response-link", response_model=ResponseLinkOut)
def generate_response_link(
    center_penalty_id: int,
    db: Session = Depends(get_db),
    _user: User = Depends(require_role(*VIGILANCE_ROLES)),
):
    """(Re)issues the public response-portal link for this case -- share the
    returned URL with the center (e.g. in the notification email). Calling
    this again always mints a fresh token, invalidating any previous link."""
    cp = _get_center_penalty_or_404(db, center_penalty_id)
    cp = response_service.generate_response_link_token(db, center_penalty=cp)
    return ResponseLinkOut(
        response_token=cp.response_token,
        response_url=f"{settings.FRONTEND_URL}/respond/delayed-cash/{cp.response_token}",
        expires_at=cp.response_token_expires_at,
    )


@router.get("/centers-activity", response_model=list[CenterActivityOut])
def get_centers_activity(
    batch_id: int | None = None,
    db: Session = Depends(get_db),
    _user: User = Depends(require_role(*VIGILANCE_ROLES)),
):
    """Every time a center manager's browser touched the public portal --
    "opened" or "submitted" -- newest first. Includes centers that only
    browsed and never submitted anything."""
    return response_service.list_activity(db, batch_id=batch_id)


@router.get("/center-penalties/{center_penalty_id}/responses", response_model=list[CaseResponseOut])
def get_case_responses(
    center_penalty_id: int,
    db: Session = Depends(get_db),
    _user: User = Depends(require_role(*VIGILANCE_ROLES)),
):
    """Every submission a center manager has made for this case, oldest to
    newest -- shown under the review-queue decision buttons so Vigilance
    can read the remark (and download the proof) before deciding."""
    cp = _get_center_penalty_or_404(db, center_penalty_id)
    return response_service.list_responses(db, center_penalty=cp)


@router.get("/case-responses/{response_id}/evidence")
def download_case_response_evidence(
    response_id: int,
    db: Session = Depends(get_db),
    _user: User = Depends(require_role(*VIGILANCE_ROLES)),
):
    """Streams back exactly the file the center manager uploaded -- never
    re-derived, never re-encoded."""
    case_response = (
        db.query(DelayedCashCaseResponse).filter(DelayedCashCaseResponse.id == response_id).first()
    )
    if case_response is None:
        raise HTTPException(status_code=404, detail="Response not found")
    path = storage_service.absolute_path_for(case_response.evidence_storage_path)
    return FileResponse(
        path,
        media_type=case_response.evidence_mime_type,
        filename=case_response.evidence_original_filename,
    )


# ---------------------------------------------------------------------------
# Bill-level review queue -- "one place to review remarks", per-bill verdicts.
# ---------------------------------------------------------------------------


def _get_bill_or_404(db: Session, bill_id: int) -> DelayedCashBill:
    bill = db.query(DelayedCashBill).filter(DelayedCashBill.id == bill_id).first()
    if bill is None:
        raise HTTPException(status_code=404, detail="Bill not found")
    return bill


def _bills_with_center_penalty_ids(db: Session, bills: list[DelayedCashBill]) -> list[BillOut]:
    """A bill has no FK to its case -- the link is (batch_id, centre_code)
    -- so this resolves it once per call rather than making the frontend
    do a second lookup per row."""
    if not bills:
        return []
    pairs = {(b.batch_id, b.centre_code) for b in bills}
    penalties = (
        db.query(DelayedCashCenterPenalty)
        .filter(
            DelayedCashCenterPenalty.batch_id.in_({p[0] for p in pairs}),
            DelayedCashCenterPenalty.centre_code.in_({p[1] for p in pairs}),
        )
        .all()
    )
    id_by_pair = {(cp.batch_id, cp.centre_code): cp.id for cp in penalties}
    return [
        BillOut(**BillOut.model_validate(b).model_dump(exclude={"center_penalty_id"}),
                center_penalty_id=id_by_pair.get((b.batch_id, b.centre_code)))
        for b in bills
    ]


@router.get("/bills/review-queue", response_model=list[BillOut])
def get_review_queue(
    db: Session = Depends(get_db),
    _user: User = Depends(require_role(*VIGILANCE_ROLES)),
):
    """Every bill without a terminal considered/not_considered verdict yet
    -- includes bills never reviewed at all, and bills already kicked back
    (needs_more_detail/needs_proof) awaiting the center's follow-up."""
    return _bills_with_center_penalty_ids(db, calc_service.list_bills_pending_review(db))


@router.get("/bills/action-taken", response_model=list[BillOut])
def get_action_taken(
    batch_id: int | None = None,
    db: Session = Depends(get_db),
    _user: User = Depends(require_role(*VIGILANCE_ROLES)),
):
    """Every bill with a terminal considered/not_considered verdict --
    the "Action Taken" log, complementing the pending review queue."""
    return _bills_with_center_penalty_ids(db, calc_service.list_bills_action_taken(db, batch_id=batch_id))


@router.get("/center-penalties/{center_penalty_id}/bills", response_model=list[BillOut])
def get_center_penalty_bills(
    center_penalty_id: int,
    db: Session = Depends(get_db),
    _user: User = Depends(require_role(*VIGILANCE_ROLES)),
):
    """Every bill in one case, reviewed or not -- context for reviewing a
    single bill next to its siblings in the same case."""
    cp = _get_center_penalty_or_404(db, center_penalty_id)
    return calc_service.list_bills_for_center_penalty(db, center_penalty=cp)


@router.post("/bills/{bill_id}/review", response_model=BillReviewOut)
def review_bill(
    bill_id: int,
    payload: BillReviewIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(*VIGILANCE_ROLES)),
):
    """Sets one bill's review verdict. For needs_more_detail/needs_proof,
    also (re)mints that bill's case response-link token and returns it --
    there's no automatic email send yet (no center email list configured),
    so this gives Vigilance something to copy and send manually today."""
    bill = _get_bill_or_404(db, bill_id)
    try:
        bill = calc_service.set_bill_review_decision(db, bill=bill, decision=payload.decision, reviewed_by=user)
    except calc_service.InvalidReviewDecisionError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    response_link = None
    if payload.decision in ("needs_more_detail", "needs_proof"):
        cp = (
            db.query(DelayedCashCenterPenalty)
            .filter(
                DelayedCashCenterPenalty.batch_id == bill.batch_id,
                DelayedCashCenterPenalty.centre_code == bill.centre_code,
            )
            .first()
        )
        if cp is not None:
            cp = response_service.generate_response_link_token(db, center_penalty=cp)
            response_link = ResponseLinkDetailOut(
                center_penalty_id=cp.id,
                centre_code=cp.centre_code,
                centre_name=cp.centre_name,
                response_token=cp.response_token,
                response_url=f"{settings.FRONTEND_URL}/respond/delayed-cash/{cp.response_token}",
                expires_at=cp.response_token_expires_at,
            )

    return BillReviewOut(bill=BillOut.model_validate(bill), response_link=response_link)


@router.post("/bills/{bill_id}/notify", response_model=BillNotifyOut)
def notify_bill(
    bill_id: int,
    payload: BillNotifyIn,
    db: Session = Depends(get_db),
    _user: User = Depends(require_role(*VIGILANCE_ROLES)),
):
    """Emails the center about this bill's already-recorded decision --
    a fixed notice for considered/not_considered, or Vigilance's typed
    comment plus a fresh response link for needs_more_detail/needs_proof.
    Always returns 200 with {sent, reason}: a failed send (no mailbox
    connected, no email on file, Gmail rejects it) is reported back, never
    raised, since the decision itself is already saved and must not be
    blocked by this best-effort side effect."""
    bill = _get_bill_or_404(db, bill_id)
    try:
        result = notification_service.notify_bill_decision(db, bill=bill, comment=payload.comment)
    except notification_service.InvalidNotifyRequestError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return BillNotifyOut(sent=result.sent, reason=result.reason)

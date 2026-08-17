"""Public (unauthenticated) Delayed Cash Billing response portal.

No get_current_user dependency anywhere in this file, deliberately -- a
center manager reaches this from an emailed link, or from the single
shared link, never a CARVMS login. See delayed_cash_response_service's
module docstring for the two supported access paths (per-case token vs
single shared link) and the deliberate security trade-off of the latter.
"""

from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session

from app.database.database import get_db
from app.schemas.delayed_cash_billing import CaseResponseOut, PublicBillSummaryOut, PublicCaseOut, PublicOpenCaseOut
from app.schemas.org import CenterDirectoryEntry
from app.services import delayed_cash_penalty_service as calc_service
from app.services import delayed_cash_response_service as response_service
from app.services import org_sheet_sync_service

router = APIRouter(prefix="/public/delayed-cash", tags=["Delayed Cash Billing (Public Portal)"])


@router.get("/centers-directory", response_model=list[CenterDirectoryEntry])
def get_centers_directory(db: Session = Depends(get_db)):
    """Powers the Center Code/Name dropdowns on the response form -- every
    active center, sourced from the Org Master (kept current via
    POST /org/sync/center-directory or /org/sync/centers-master)."""
    entries = org_sheet_sync_service.list_active_center_directory(db)
    return [CenterDirectoryEntry(code=e["code"], name=e["name"]) for e in entries]


def _get_case_or_404(db: Session, token: str):
    cp = response_service.get_case_by_token(db, token)
    if cp is None:
        # Deliberately identical to any other lookup failure -- an invalid
        # token must not distinguish "never existed" from "expired" or
        # leak whether a case exists at all.
        raise HTTPException(status_code=404, detail="This response link is invalid.")
    return cp


def _build_public_case(cp, db: Session) -> PublicCaseOut:
    responses = response_service.list_responses(db, center_penalty=cp)
    bills = calc_service.list_bills_for_center_penalty(db, center_penalty=cp)
    return PublicCaseOut(
        centre_code=cp.centre_code,
        centre_name=cp.centre_name,
        period_start=cp.batch.period_start,
        period_end=cp.batch.period_end,
        total_bills=cp.total_bills,
        calculated_penalty=cp.calculated_penalty,
        tat_status=response_service.tat_status(cp),
        deadline=cp.response_token_expires_at,
        already_responded=len(responses) > 0,
        # Every bill in the case, not just the still-pending ones -- so the
        # center can see exactly which sales bill(s) it's being asked to
        # explain, instead of guessing from a bare total count.
        bills=[
            PublicBillSummaryOut(
                sales_bill=b.sales_bill,
                bill_date=b.bill_date,
                calculated_day_difference=b.calculated_day_difference,
                calculated_penalty=b.calculated_penalty,
                considered=b.considered,
            )
            for b in bills
        ],
    )


@router.get("/cases/{token}", response_model=PublicCaseOut)
def get_case(token: str, db: Session = Depends(get_db)):
    cp = _get_case_or_404(db, token)
    response_service.record_activity(
        db, centre_code=cp.centre_code, centre_name=cp.centre_name, center_penalty=cp, event_type="opened"
    )
    return _build_public_case(cp, db)


@router.get("/open-cases", response_model=list[PublicOpenCaseOut])
def get_open_cases(
    centre_code: str = Query(..., min_length=1),
    db: Session = Depends(get_db),
):
    """Powers the single shared link (no token): the responder picks their
    center from the centers-directory dropdown, then this returns every
    case still open for that exact code -- validated_penalty is still null,
    meaning at least one bill hasn't reached a terminal review decision.
    Empty list is a normal, valid result (nothing currently needs a
    response from this center), not an error."""
    cases = response_service.list_open_cases_for_centre_code(db, centre_code)
    if cases:
        for cp in cases:
            response_service.record_activity(
                db, centre_code=cp.centre_code, centre_name=cp.centre_name, center_penalty=cp, event_type="opened"
            )
    else:
        # Still worth logging -- a manager checked this center and had
        # nothing pending, which is different from never checking at all.
        response_service.record_activity(db, centre_code=centre_code, event_type="opened")
    out = []
    for cp in cases:
        base = _build_public_case(cp, db)
        out.append(PublicOpenCaseOut(**base.model_dump(), id=cp.id))
    return out


@router.post("/cases/{token}/respond", response_model=CaseResponseOut, status_code=201)
def respond(
    token: str,
    responder_name: str = Form(...),
    responder_npid: str = Form(...),
    responder_email: str = Form(...),
    reason: str = Form(...),
    evidence: UploadFile | None = File(default=None),
    selected_center_code: Optional[str] = Form(default=None),
    selected_center_name: Optional[str] = Form(default=None),
    db: Session = Depends(get_db),
):
    cp = _get_case_or_404(db, token)
    try:
        result = response_service.submit_response(
            db,
            center_penalty=cp,
            responder_name=responder_name,
            responder_npid=responder_npid,
            responder_email=responder_email,
            reason=reason,
            evidence_file=evidence,
            selected_center_code=selected_center_code,
            selected_center_name=selected_center_name,
        )
    except response_service.MissingEvidenceError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    response_service.record_activity(
        db, centre_code=cp.centre_code, centre_name=cp.centre_name, center_penalty=cp, event_type="submitted"
    )
    return result


def _get_case_by_id_or_404(db: Session, center_penalty_id: int):
    cp = response_service.get_case_by_id(db, center_penalty_id)
    if cp is None:
        raise HTTPException(status_code=404, detail="This case was not found.")
    return cp


@router.post("/cases/by-id/{center_penalty_id}/respond", response_model=CaseResponseOut, status_code=201)
def respond_by_id(
    center_penalty_id: int,
    responder_name: str = Form(...),
    responder_npid: str = Form(...),
    responder_email: str = Form(...),
    reason: str = Form(...),
    evidence: UploadFile | None = File(default=None),
    selected_center_code: Optional[str] = Form(default=None),
    selected_center_name: Optional[str] = Form(default=None),
    db: Session = Depends(get_db),
):
    """Same submission as /cases/{token}/respond, reached from the single
    shared link instead of a per-case token -- see get_open_cases above for
    how the responder's browser learns this ID."""
    cp = _get_case_by_id_or_404(db, center_penalty_id)
    try:
        result = response_service.submit_response(
            db,
            center_penalty=cp,
            responder_name=responder_name,
            responder_npid=responder_npid,
            responder_email=responder_email,
            reason=reason,
            evidence_file=evidence,
            selected_center_code=selected_center_code,
            selected_center_name=selected_center_name,
        )
    except response_service.MissingEvidenceError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    response_service.record_activity(
        db, centre_code=cp.centre_code, centre_name=cp.centre_name, center_penalty=cp, event_type="submitted"
    )
    return result

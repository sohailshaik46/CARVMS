"""Public (unauthenticated) Weekly Revenue Closure response portal.

Mirrors app/api/delayed_cash_public.py exactly -- no get_current_user
dependency anywhere in this file, deliberately. See
weekly_revenue_response_service's module docstring for the one real
structural difference from the DCB version (WeeklyRevenueCenterCase vs
the post-review WeeklyRevenueCenterPenalty).
"""

from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session

from app.database.database import get_db
from app.schemas.org import CenterDirectoryEntry
from app.schemas.weekly_revenue_closure import CaseResponseOut, PublicCaseOut, PublicIncidentSummaryOut, PublicOpenCaseOut
from app.services import org_sheet_sync_service
from app.services import weekly_revenue_response_service as response_service

router = APIRouter(prefix="/public/weekly-revenue", tags=["Weekly Revenue Closure (Public Portal)"])


@router.get("/centers-directory", response_model=list[CenterDirectoryEntry])
def get_centers_directory(db: Session = Depends(get_db)):
    entries = org_sheet_sync_service.list_active_center_directory(db)
    return [CenterDirectoryEntry(code=e["code"], name=e["name"]) for e in entries]


def _get_case_or_404(db: Session, token: str):
    case = response_service.get_case_by_token(db, token)
    if case is None:
        raise HTTPException(status_code=404, detail="This response link is invalid.")
    return case


def _build_public_case(case, db: Session) -> PublicCaseOut:
    responses = response_service.list_responses(db, case=case)
    pending = response_service.pending_incident_count(db, batch_id=case.batch_id, centre_code=case.centre_code)
    incidents = response_service.list_incidents_for_case(db, case=case)
    return PublicCaseOut(
        centre_code=case.centre_code,
        centre_name=case.centre_name,
        period_start=case.batch.period_start,
        period_end=case.batch.period_end,
        week_label=case.batch.week_label,
        pending_incident_count=pending,
        tat_status=response_service.tat_status(case),
        deadline=case.response_token_expires_at,
        already_responded=len(responses) > 0,
        # Every incident in the case, reviewed or not -- so the center can
        # see exactly which incident(s) it's being asked to explain,
        # instead of guessing from a bare pending count.
        incidents=[
            PublicIncidentSummaryOut(
                incident_date=i.incident_date,
                mis_final_remark=i.mis_final_remark,
                raw_remark=i.raw_remark,
                considered=i.considered,
            )
            for i in incidents
        ],
    )


@router.get("/cases/{token}", response_model=PublicCaseOut)
def get_case(token: str, db: Session = Depends(get_db)):
    case = _get_case_or_404(db, token)
    response_service.record_activity(
        db, centre_code=case.centre_code, centre_name=case.centre_name, case=case, event_type="opened"
    )
    return _build_public_case(case, db)


@router.get("/open-cases", response_model=list[PublicOpenCaseOut])
def get_open_cases(
    centre_code: str = Query(..., min_length=1),
    db: Session = Depends(get_db),
):
    cases = response_service.list_open_cases_for_centre_code(db, centre_code)
    if cases:
        for case in cases:
            response_service.record_activity(
                db, centre_code=case.centre_code, centre_name=case.centre_name, case=case, event_type="opened"
            )
    else:
        response_service.record_activity(db, centre_code=centre_code, event_type="opened")
    out = []
    for case in cases:
        base = _build_public_case(case, db)
        out.append(PublicOpenCaseOut(**base.model_dump(), id=case.id))
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
    case = _get_case_or_404(db, token)
    try:
        result = response_service.submit_response(
            db,
            case=case,
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
        db, centre_code=case.centre_code, centre_name=case.centre_name, case=case, event_type="submitted"
    )
    return result


def _get_case_by_id_or_404(db: Session, case_id: int):
    case = response_service.get_case_by_id(db, case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="This case was not found.")
    return case


@router.post("/cases/by-id/{case_id}/respond", response_model=CaseResponseOut, status_code=201)
def respond_by_id(
    case_id: int,
    responder_name: str = Form(...),
    responder_npid: str = Form(...),
    responder_email: str = Form(...),
    reason: str = Form(...),
    evidence: UploadFile | None = File(default=None),
    selected_center_code: Optional[str] = Form(default=None),
    selected_center_name: Optional[str] = Form(default=None),
    db: Session = Depends(get_db),
):
    case = _get_case_by_id_or_404(db, case_id)
    try:
        result = response_service.submit_response(
            db,
            case=case,
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
        db, centre_code=case.centre_code, centre_name=case.centre_name, case=case, event_type="submitted"
    )
    return result

"""Auto-validation: rule management (shared across DCB + WRC) and the
per-engine list/reevaluate/override/export surface. See
app/services/auto_validation_service.py's module docstring for the full
advisory-only design -- nothing here ever sets a bill/incident's real
`considered` decision.
"""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.auth import roles
from app.auth.dependencies import require_role
from app.database.database import get_db
from app.models.delayed_cash_billing import DelayedCashCaseResponse
from app.models.user import User
from app.models.weekly_revenue_closure import WeeklyRevenueCaseResponse
from app.schemas.auto_validation import (
    AutoValidationOverrideIn,
    AutoValidationResponseOut,
    AutoValidationRuleActiveIn,
    AutoValidationRuleIn,
    AutoValidationRuleOut,
)
from app.services import auto_validation_export_service as export_service
from app.services import auto_validation_service as service

router = APIRouter(tags=["Auto Validation"])

VIGILANCE_ROLES = (roles.ADMIN, roles.AUDITOR)


# ---------------------------------------------------------------------------
# Rule management -- shared vocabulary, editable without a code change.
# ---------------------------------------------------------------------------


@router.get("/auto-validation-rules", response_model=list[AutoValidationRuleOut])
def list_rules(
    active_only: bool = False,
    db: Session = Depends(get_db),
    _user: User = Depends(require_role(*VIGILANCE_ROLES)),
):
    return service.list_rules(db, active_only=active_only)


@router.post("/auto-validation-rules", response_model=AutoValidationRuleOut, status_code=201)
def create_rule(
    payload: AutoValidationRuleIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(*VIGILANCE_ROLES)),
):
    try:
        return service.create_rule(db, created_by=user, **payload.model_dump())
    except service.InvalidBucketError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.patch("/auto-validation-rules/{rule_id}/active", response_model=AutoValidationRuleOut)
def set_rule_active(
    rule_id: int,
    payload: AutoValidationRuleActiveIn,
    db: Session = Depends(get_db),
    _user: User = Depends(require_role(*VIGILANCE_ROLES)),
):
    from app.models.auto_validation import AutoValidationRule

    rule = db.query(AutoValidationRule).filter(AutoValidationRule.id == rule_id).first()
    if rule is None:
        raise HTTPException(status_code=404, detail="Rule not found")
    return service.set_rule_active(db, rule=rule, is_active=payload.is_active)


# ---------------------------------------------------------------------------
# DCB surface
# ---------------------------------------------------------------------------


def _dcb_out(r: DelayedCashCaseResponse) -> AutoValidationResponseOut:
    cp = r.center_penalty
    return AutoValidationResponseOut(
        id=r.id,
        engine="dcb",
        case_or_penalty_id=cp.id,
        batch_id=cp.batch_id,
        centre_code=cp.centre_code,
        centre_name=cp.centre_name,
        reason=r.reason,
        submitted_at=r.submitted_at,
        auto_bucket=r.auto_bucket,
        auto_category=r.auto_category,
        auto_matched_keyword=r.auto_matched_keyword,
        auto_decision_label=r.auto_decision_label,
        auto_reason=r.auto_reason,
        auto_evaluated_at=r.auto_evaluated_at,
        admin_override_bucket=r.admin_override_bucket,
        admin_override_by_name=(r.admin_override_by.username if r.admin_override_by else None),
        admin_override_at=r.admin_override_at,
        admin_override_note=r.admin_override_note,
        effective_bucket=service.effective_bucket(r),
    )


def _get_dcb_response_or_404(db: Session, response_id: int) -> DelayedCashCaseResponse:
    r = db.query(DelayedCashCaseResponse).filter(DelayedCashCaseResponse.id == response_id).first()
    if r is None:
        raise HTTPException(status_code=404, detail="Response not found")
    return r


@router.get("/delayed-cash/auto-validation", response_model=list[AutoValidationResponseOut])
def list_dcb_auto_validation(
    bucket: str | None = None,
    db: Session = Depends(get_db),
    _user: User = Depends(require_role(*VIGILANCE_ROLES)),
):
    return [_dcb_out(r) for r in service.list_dcb_responses(db, bucket=bucket)]


@router.post("/delayed-cash/auto-validation/{response_id}/reevaluate", response_model=AutoValidationResponseOut)
def reevaluate_dcb_response(
    response_id: int,
    db: Session = Depends(get_db),
    _user: User = Depends(require_role(*VIGILANCE_ROLES)),
):
    r = _get_dcb_response_or_404(db, response_id)
    return _dcb_out(service.evaluate_dcb_response(db, response=r))


@router.post("/delayed-cash/auto-validation/reevaluate-all", response_model=list[AutoValidationResponseOut])
def reevaluate_all_dcb(
    db: Session = Depends(get_db),
    _user: User = Depends(require_role(*VIGILANCE_ROLES)),
):
    """On-demand re-run for every response Vigilance hasn't already
    overridden -- e.g. after editing the rules above."""
    return [_dcb_out(r) for r in service.reevaluate_all_dcb(db)]


@router.post("/delayed-cash/auto-validation/{response_id}/override", response_model=AutoValidationResponseOut)
def override_dcb_response(
    response_id: int,
    payload: AutoValidationOverrideIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(*VIGILANCE_ROLES)),
):
    r = _get_dcb_response_or_404(db, response_id)
    try:
        r = service.override_dcb_response(db, response=r, admin=user, new_bucket=payload.bucket, note=payload.note)
    except service.InvalidBucketError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return _dcb_out(r)


# ---------------------------------------------------------------------------
# WRC surface
# ---------------------------------------------------------------------------


def _wrc_out(r: WeeklyRevenueCaseResponse) -> AutoValidationResponseOut:
    case = r.case
    return AutoValidationResponseOut(
        id=r.id,
        engine="wrc",
        case_or_penalty_id=case.id,
        batch_id=case.batch_id,
        centre_code=case.centre_code,
        centre_name=case.centre_name,
        reason=r.reason,
        submitted_at=r.submitted_at,
        auto_bucket=r.auto_bucket,
        auto_category=r.auto_category,
        auto_matched_keyword=r.auto_matched_keyword,
        auto_decision_label=r.auto_decision_label,
        auto_reason=r.auto_reason,
        auto_evaluated_at=r.auto_evaluated_at,
        admin_override_bucket=r.admin_override_bucket,
        admin_override_by_name=(r.admin_override_by.username if r.admin_override_by else None),
        admin_override_at=r.admin_override_at,
        admin_override_note=r.admin_override_note,
        effective_bucket=service.effective_bucket(r),
    )


def _get_wrc_response_or_404(db: Session, response_id: int) -> WeeklyRevenueCaseResponse:
    r = db.query(WeeklyRevenueCaseResponse).filter(WeeklyRevenueCaseResponse.id == response_id).first()
    if r is None:
        raise HTTPException(status_code=404, detail="Response not found")
    return r


@router.get("/weekly-revenue-closure/auto-validation", response_model=list[AutoValidationResponseOut])
def list_wrc_auto_validation(
    bucket: str | None = None,
    db: Session = Depends(get_db),
    _user: User = Depends(require_role(*VIGILANCE_ROLES)),
):
    return [_wrc_out(r) for r in service.list_wrc_responses(db, bucket=bucket)]


@router.post("/weekly-revenue-closure/auto-validation/{response_id}/reevaluate", response_model=AutoValidationResponseOut)
def reevaluate_wrc_response(
    response_id: int,
    db: Session = Depends(get_db),
    _user: User = Depends(require_role(*VIGILANCE_ROLES)),
):
    r = _get_wrc_response_or_404(db, response_id)
    return _wrc_out(service.evaluate_wrc_response(db, response=r))


@router.post("/weekly-revenue-closure/auto-validation/reevaluate-all", response_model=list[AutoValidationResponseOut])
def reevaluate_all_wrc(
    db: Session = Depends(get_db),
    _user: User = Depends(require_role(*VIGILANCE_ROLES)),
):
    return [_wrc_out(r) for r in service.reevaluate_all_wrc(db)]


@router.post("/weekly-revenue-closure/auto-validation/{response_id}/override", response_model=AutoValidationResponseOut)
def override_wrc_response(
    response_id: int,
    payload: AutoValidationOverrideIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(*VIGILANCE_ROLES)),
):
    r = _get_wrc_response_or_404(db, response_id)
    try:
        r = service.override_wrc_response(db, response=r, admin=user, new_bucket=payload.bucket, note=payload.note)
    except service.InvalidBucketError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return _wrc_out(r)


# ---------------------------------------------------------------------------
# Combined export -- one workbook covers both engines (see
# auto_validation_export_service: an "Engine" column on every sheet already
# discriminates DCB vs WRC rows, so one download satisfies "in excel for
# WRC and DCB" without forcing two separate files).
# ---------------------------------------------------------------------------


@router.get("/auto-validation/export.xlsx")
def export_auto_validation(
    db: Session = Depends(get_db),
    _user: User = Depends(require_role(*VIGILANCE_ROLES)),
):
    dcb_rows = export_service.build_dcb_rows(db)
    wrc_rows = export_service.build_wrc_rows(db)
    content = export_service.render_xlsx(dcb_rows, wrc_rows)
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="auto_validation_report.xlsx"'},
    )

"""Public response-portal service for Weekly Revenue Closure cases.

Mirrors app/services/delayed_cash_response_service.py's design exactly --
same two access paths (per-case token vs single shared link), same
security trade-off on the latter, same TAT/evidence rules. The one real
difference: WeeklyRevenueCenterPenalty only exists after compute_center_
penalties runs at close_batch time (post-review), so it can't double as
the "case" a center responds to WHILE incidents are still pending review.
WeeklyRevenueCenterCase exists specifically to not couple this portal to
that later lifecycle stage -- see its model docstring.
"""

import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import UploadFile
from sqlalchemy.orm import Session

from app.models.weekly_revenue_closure import (
    WeeklyRevenueBillIncident,
    WeeklyRevenueCaseResponse,
    WeeklyRevenueCenterActivity,
    WeeklyRevenueCenterCase,
    WeeklyRevenueClosureBatch,
)
from app.services import org_contact_change_service, storage_service

RESPONSE_TAT_HOURS = 48


class MissingEvidenceError(Exception):
    """Raised when a submission has no attachment -- never accepted."""


def mint_links_for_batch(db: Session, *, batch: WeeklyRevenueClosureBatch) -> list[WeeklyRevenueCenterCase]:
    """Bulk-issues a fresh response-portal link for every distinct center
    that has at least one incident in this batch -- mirrors DCB's
    publish_batch link-minting half, without DCB's "compute the
    publishing-stage penalty" half (WRC has no equivalent pre-review
    penalty to compute; see WeeklyRevenueCenterCase's model docstring).
    Safe to call again -- always mints fresh tokens."""
    rows = (
        db.query(WeeklyRevenueBillIncident.centre_code, WeeklyRevenueBillIncident.centre_name)
        .filter(WeeklyRevenueBillIncident.batch_id == batch.id)
        .distinct()
        .all()
    )
    cases = []
    for centre_code, centre_name in rows:
        case = get_or_create_case(db, batch=batch, centre_code=centre_code, centre_name=centre_name)
        case = generate_response_link_token(db, case=case)
        cases.append(case)
    return cases


def get_or_create_case(
    db: Session, *, batch: WeeklyRevenueClosureBatch, centre_code: str, centre_name: str
) -> WeeklyRevenueCenterCase:
    case = (
        db.query(WeeklyRevenueCenterCase)
        .filter(WeeklyRevenueCenterCase.batch_id == batch.id, WeeklyRevenueCenterCase.centre_code == centre_code)
        .first()
    )
    if case is not None:
        return case
    case = WeeklyRevenueCenterCase(batch_id=batch.id, centre_code=centre_code, centre_name=centre_name)
    db.add(case)
    db.commit()
    db.refresh(case)
    return case


def generate_response_link_token(
    db: Session, *, case: WeeklyRevenueCenterCase, ttl_hours: int = RESPONSE_TAT_HOURS
) -> WeeklyRevenueCenterCase:
    """(Re)issues this case's public response token and TAT deadline --
    always a fresh token, same reasoning as the DCB equivalent."""
    case.response_token = secrets.token_urlsafe(32)
    case.response_token_expires_at = datetime.now(timezone.utc) + timedelta(hours=ttl_hours)
    db.commit()
    db.refresh(case)
    return case


def get_published_links_for_batch(
    db: Session, *, batch: WeeklyRevenueClosureBatch
) -> list[WeeklyRevenueCenterCase]:
    """Read-only counterpart to mint_links_for_batch above -- returns
    whichever cases in this batch already have a response token, WITHOUT
    minting or invalidating anything. Backs the Batches table's quick
    "View links" action, so copying a link doesn't require re-publishing
    (and so doesn't invalidate every other center's already-shared link)
    just to look. Mirrors DCB's get_published_links in
    delayed_cash_upload_service.py."""
    return (
        db.query(WeeklyRevenueCenterCase)
        .filter(
            WeeklyRevenueCenterCase.batch_id == batch.id,
            WeeklyRevenueCenterCase.response_token.isnot(None),
        )
        .all()
    )


def get_case_by_token(db: Session, token: str) -> Optional[WeeklyRevenueCenterCase]:
    return db.query(WeeklyRevenueCenterCase).filter(WeeklyRevenueCenterCase.response_token == token).first()


def get_case_by_id(db: Session, case_id: int) -> Optional[WeeklyRevenueCenterCase]:
    """Backs the single shared response link -- see get_case_by_id in
    delayed_cash_response_service.py for the full security-tradeoff
    rationale, identical here."""
    return db.query(WeeklyRevenueCenterCase).filter(WeeklyRevenueCenterCase.id == case_id).first()


def pending_incident_count(db: Session, *, batch_id: int, centre_code: str) -> int:
    return (
        db.query(WeeklyRevenueBillIncident)
        .filter(
            WeeklyRevenueBillIncident.batch_id == batch_id,
            WeeklyRevenueBillIncident.centre_code == centre_code,
            WeeklyRevenueBillIncident.considered.is_(None),
        )
        .count()
    )


def list_incidents_for_case(db: Session, *, case: WeeklyRevenueCenterCase) -> list[WeeklyRevenueBillIncident]:
    """Every incident in this case (batch_id, centre_code), reviewed or
    not -- shown to the center so they know exactly which incident(s) they
    are being asked to explain, mirroring
    delayed_cash_penalty_service.list_bills_for_center_penalty."""
    return (
        db.query(WeeklyRevenueBillIncident)
        .filter(
            WeeklyRevenueBillIncident.batch_id == case.batch_id,
            WeeklyRevenueBillIncident.centre_code == case.centre_code,
        )
        .order_by(WeeklyRevenueBillIncident.incident_date)
        .all()
    )


def list_open_cases_for_centre_code(db: Session, centre_code: str) -> list[WeeklyRevenueCenterCase]:
    """"Open" = this center has at least one incident, in an open (not yet
    closed) batch, with no review verdict yet. A case with zero pending
    incidents (everything already reviewed) naturally drops off this list
    -- nothing further for the center to usefully add right now. Newest
    period first."""
    rows = (
        db.query(WeeklyRevenueBillIncident.batch_id, WeeklyRevenueBillIncident.centre_name)
        .join(WeeklyRevenueClosureBatch, WeeklyRevenueBillIncident.batch_id == WeeklyRevenueClosureBatch.id)
        .filter(
            WeeklyRevenueBillIncident.centre_code == centre_code,
            WeeklyRevenueBillIncident.considered.is_(None),
            WeeklyRevenueClosureBatch.status == "open",
        )
        .distinct()
        .all()
    )
    if not rows:
        return []

    cases = []
    for batch_id, centre_name in rows:
        batch = db.query(WeeklyRevenueClosureBatch).filter(WeeklyRevenueClosureBatch.id == batch_id).first()
        case = get_or_create_case(db, batch=batch, centre_code=centre_code, centre_name=centre_name)
        cases.append(case)

    cases.sort(key=lambda c: c.batch.period_start, reverse=True)
    return cases


def tat_status(case: WeeklyRevenueCenterCase) -> str:
    """Same naive-datetime-as-UTC fix as the DCB/email-connection equivalents."""
    if case.response_token_expires_at is None:
        return "unknown"
    deadline = case.response_token_expires_at
    if deadline.tzinfo is None:
        deadline = deadline.replace(tzinfo=timezone.utc)
    return "within_window" if datetime.now(timezone.utc) <= deadline else "overdue"


def submit_response(
    db: Session,
    *,
    case: WeeklyRevenueCenterCase,
    responder_name: str,
    responder_npid: str,
    responder_email: Optional[str],
    reason: str,
    evidence_file: Optional[UploadFile],
    selected_center_code: Optional[str] = None,
    selected_center_name: Optional[str] = None,
) -> WeeklyRevenueCaseResponse:
    if evidence_file is None or not evidence_file.filename:
        raise MissingEvidenceError("Supporting attachment is mandatory.")

    saved = storage_service.save_upload(evidence_file, subdir=f"weekly_revenue_case_{case.id}")

    response = WeeklyRevenueCaseResponse(
        case_id=case.id,
        responder_name=responder_name,
        responder_npid=responder_npid,
        responder_email=responder_email,
        reason=reason,
        evidence_original_filename=evidence_file.filename,
        evidence_mime_type=evidence_file.content_type or "application/octet-stream",
        evidence_size_bytes=saved.size_bytes,
        evidence_checksum=saved.checksum,
        evidence_storage_path=saved.storage_path,
        was_within_tat=tat_status(case),
        selected_center_code=selected_center_code,
        selected_center_name=selected_center_name,
    )
    db.add(response)
    db.commit()
    db.refresh(response)

    org_contact_change_service.propose_contact_change(
        db,
        centre_code=selected_center_code or case.centre_code,
        manager_name=responder_name,
        manager_npid=responder_npid,
        manager_email=responder_email,
        source="weekly_revenue_response",
        source_reference_id=response.id,
    )

    return response


def list_responses(db: Session, *, case: WeeklyRevenueCenterCase) -> list[WeeklyRevenueCaseResponse]:
    return (
        db.query(WeeklyRevenueCaseResponse)
        .filter(WeeklyRevenueCaseResponse.case_id == case.id)
        .order_by(WeeklyRevenueCaseResponse.submitted_at)
        .all()
    )


# ---------------------------------------------------------------------------
# Centers Activity


def record_activity(
    db: Session,
    *,
    centre_code: str,
    event_type: str,
    centre_name: Optional[str] = None,
    case: Optional[WeeklyRevenueCenterCase] = None,
) -> WeeklyRevenueCenterActivity:
    activity = WeeklyRevenueCenterActivity(
        centre_code=centre_code,
        centre_name=centre_name,
        case_id=case.id if case else None,
        event_type=event_type,
    )
    db.add(activity)
    db.commit()
    db.refresh(activity)
    return activity


def list_activity(db: Session, *, batch_id: Optional[int] = None) -> list[WeeklyRevenueCenterActivity]:
    query = db.query(WeeklyRevenueCenterActivity)
    if batch_id is not None:
        query = query.join(
            WeeklyRevenueCenterCase, WeeklyRevenueCenterActivity.case_id == WeeklyRevenueCenterCase.id
        ).filter(WeeklyRevenueCenterCase.batch_id == batch_id)
    return query.order_by(WeeklyRevenueCenterActivity.occurred_at.desc(), WeeklyRevenueCenterActivity.id.desc()).all()

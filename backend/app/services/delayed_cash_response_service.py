"""Public response-portal service for Delayed Cash Billing cases.

Two ways to reach a case without ever logging into CARVMS, both supported
deliberately (per the user's explicit choice to keep both rather than
replace one with the other):

1. A per-case link with an opaque, unguessable response_token (get_case_by_token)
   -- minted one at a time or in bulk per batch, invalidated by re-minting.
2. The single shared link (get_case_by_id / list_open_cases_for_centre_code)
   -- one fixed URL for every center; the responder identifies their own
   case by picking their center from the public centers directory instead
   of holding a token. This is a real, accepted security trade-off: it's
   soft-flag, not hard-block -- anyone who knows a (public) center code can
   view/submit for that center's open case. The alternative (a hard NPID
   check against the Org Master) was deliberately rejected because a
   stale/wrong record for even one center would lock out a legitimate
   manager; a mismatch is recorded for Vigilance to see, same as the
   existing selected_center_code/centre_code mismatch tracking, never
   silently corrected or rejected.
"""

import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import UploadFile
from sqlalchemy.orm import Session

from app.models.delayed_cash_billing import (
    DelayedCashCaseResponse,
    DelayedCashCenterActivity,
    DelayedCashCenterPenalty,
    DelayedCashUploadBatch,
)
from app.services import org_contact_change_service, storage_service

RESPONSE_TAT_HOURS = 48


class MissingEvidenceError(Exception):
    """Raised when a submission has no attachment -- never accepted, client
    or server side. The API layer turns this into the exact required
    message: "Supporting attachment is mandatory."."""


def generate_response_link_token(
    db: Session, *, center_penalty: DelayedCashCenterPenalty, ttl_hours: int = RESPONSE_TAT_HOURS
) -> DelayedCashCenterPenalty:
    """(Re)issues this case's public response token and TAT deadline.
    Safe to call again to refresh an expired link -- always mints a fresh
    token rather than extending the old one, so a stale, possibly-leaked
    link stops working."""
    center_penalty.response_token = secrets.token_urlsafe(32)
    center_penalty.response_token_expires_at = datetime.now(timezone.utc) + timedelta(hours=ttl_hours)
    db.commit()
    db.refresh(center_penalty)
    return center_penalty


def get_case_by_token(db: Session, token: str) -> Optional[DelayedCashCenterPenalty]:
    return (
        db.query(DelayedCashCenterPenalty)
        .filter(DelayedCashCenterPenalty.response_token == token)
        .first()
    )


def get_case_by_id(db: Session, center_penalty_id: int) -> Optional[DelayedCashCenterPenalty]:
    """Public, unauthenticated lookup by raw ID -- deliberately different
    from get_case_by_token above. This backs the single shared response
    link (one URL for every center, per the user's explicit choice): the
    responder identifies their case by picking their center from the public
    centers directory, not by holding an unguessable per-case token. That is
    a real, accepted trade-off -- soft-flag rather than hard-block, chosen
    over an NPID-matching hard gate specifically so a stale/wrong Org Master
    record can never lock out a legitimate manager. The per-case token flow
    above is kept fully intact as a fallback for anyone who still wants a
    one-off private link for a specific case."""
    return (
        db.query(DelayedCashCenterPenalty)
        .filter(DelayedCashCenterPenalty.id == center_penalty_id)
        .first()
    )


def list_open_cases_for_centre_code(db: Session, centre_code: str) -> list[DelayedCashCenterPenalty]:
    """"Open" = validated_penalty is still null -- i.e. at least one bill in
    the case hasn't reached a terminal review decision yet (see
    delayed_cash_penalty_service.recompute_validated_penalty). Once every
    bill is considered/not_considered and validated_penalty is computed,
    the case naturally drops off this list -- there's nothing further for
    the center to usefully add. Newest period first."""
    return (
        db.query(DelayedCashCenterPenalty)
        .join(DelayedCashUploadBatch, DelayedCashCenterPenalty.batch_id == DelayedCashUploadBatch.id)
        .filter(
            DelayedCashCenterPenalty.centre_code == centre_code,
            DelayedCashCenterPenalty.validated_penalty.is_(None),
        )
        .order_by(DelayedCashUploadBatch.period_start.desc())
        .all()
    )


def tat_status(center_penalty: DelayedCashCenterPenalty) -> str:
    """"within_window" / "overdue" / "unknown" (no deadline set yet).
    SQLite doesn't retain tzinfo on read-back -- treat a naive value as UTC,
    same fix as the email-connection state-token expiry check."""
    if center_penalty.response_token_expires_at is None:
        return "unknown"
    deadline = center_penalty.response_token_expires_at
    if deadline.tzinfo is None:
        deadline = deadline.replace(tzinfo=timezone.utc)
    return "within_window" if datetime.now(timezone.utc) <= deadline else "overdue"


def submit_response(
    db: Session,
    *,
    center_penalty: DelayedCashCenterPenalty,
    responder_name: str,
    responder_npid: str,
    responder_email: Optional[str],
    reason: str,
    evidence_file: Optional[UploadFile],
    selected_center_code: Optional[str] = None,
    selected_center_name: Optional[str] = None,
) -> DelayedCashCaseResponse:
    if evidence_file is None or not evidence_file.filename:
        raise MissingEvidenceError("Supporting attachment is mandatory.")

    saved = storage_service.save_upload(
        evidence_file, subdir=f"delayed_cash_case_{center_penalty.id}"
    )

    response = DelayedCashCaseResponse(
        center_penalty_id=center_penalty.id,
        responder_name=responder_name,
        responder_npid=responder_npid,
        responder_email=responder_email,
        reason=reason,
        evidence_original_filename=evidence_file.filename,
        evidence_mime_type=evidence_file.content_type or "application/octet-stream",
        evidence_size_bytes=saved.size_bytes,
        evidence_checksum=saved.checksum,
        evidence_storage_path=saved.storage_path,
        was_within_tat=tat_status(center_penalty),
        # Stored as-given, never validated against center_penalty.centre_code
        # here -- a mismatch is a real signal for Vigilance to see, not
        # something this function should silently correct or reject.
        selected_center_code=selected_center_code,
        selected_center_name=selected_center_name,
    )
    db.add(response)
    db.commit()
    db.refresh(response)

    # The name/NPID/email above are self-reported by whoever opened the
    # link -- never written into the Org Master directly. This proposes a
    # pending change instead; an Admin must explicitly approve it (see
    # org_contact_change_service) before OrgNode.manager_* actually changes.
    # Keyed off the center the responder actually claimed to represent
    # (selected_center_code), falling back to the case's own center if they
    # didn't pick one.
    org_contact_change_service.propose_contact_change(
        db,
        centre_code=selected_center_code or center_penalty.centre_code,
        manager_name=responder_name,
        manager_npid=responder_npid,
        manager_email=responder_email,
        source="delayed_cash_response",
        source_reference_id=response.id,
    )

    return response


def list_responses(db: Session, *, center_penalty: DelayedCashCenterPenalty) -> list[DelayedCashCaseResponse]:
    return (
        db.query(DelayedCashCaseResponse)
        .filter(DelayedCashCaseResponse.center_penalty_id == center_penalty.id)
        .order_by(DelayedCashCaseResponse.submitted_at)
        .all()
    )


# ---------------------------------------------------------------------------
# Centers Activity -- "opened" and "submitted" events, logged even for
# cases a manager only browsed and never acted on.
# ---------------------------------------------------------------------------


def record_activity(
    db: Session,
    *,
    centre_code: str,
    event_type: str,
    centre_name: Optional[str] = None,
    center_penalty: Optional[DelayedCashCenterPenalty] = None,
) -> DelayedCashCenterActivity:
    activity = DelayedCashCenterActivity(
        centre_code=centre_code,
        centre_name=centre_name,
        center_penalty_id=center_penalty.id if center_penalty else None,
        event_type=event_type,
    )
    db.add(activity)
    db.commit()
    db.refresh(activity)
    return activity


def list_activity(db: Session, *, batch_id: Optional[int] = None) -> list[DelayedCashCenterActivity]:
    query = db.query(DelayedCashCenterActivity)
    if batch_id is not None:
        query = query.join(
            DelayedCashCenterPenalty, DelayedCashCenterActivity.center_penalty_id == DelayedCashCenterPenalty.id
        ).filter(DelayedCashCenterPenalty.batch_id == batch_id)
    # id DESC as a tiebreaker: SQLite's CURRENT_TIMESTAMP only has 1-second
    # resolution, so two events logged within the same second (e.g. an
    # "opened" immediately followed by a "submitted") would otherwise sort
    # in an undefined order relative to each other.
    return query.order_by(DelayedCashCenterActivity.occurred_at.desc(), DelayedCashCenterActivity.id.desc()).all()

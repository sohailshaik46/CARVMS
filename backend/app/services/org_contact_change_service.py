"""Center-manager contact-change-request workflow.

A public response-portal submission's name/NPID/email is NEVER written
straight into OrgNode -- per the user's explicit instruction, it becomes a
pending OrgNodeContactChangeRequest instead, and org_service.update_node()
is only ever called once an Admin explicitly approves it from the
notifications queue. See app/models/org.py:OrgNodeContactChangeRequest for
the full rationale.
"""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.models.org import OrgNodeContactChangeRequest
from app.models.user import User
from app.services import org_service


class ContactChangeRequestNotFoundError(Exception):
    pass


class AlreadyReviewedError(Exception):
    """Raised when approving/rejecting a request that isn't pending anymore
    -- never silently re-applied or re-reviewed."""


class NoMatchingOrgNodeError(Exception):
    """Raised when trying to approve a request whose submitted center code
    never resolved to a real OrgNode -- that has to be fixed in Org
    Hierarchy first; approval never creates a node on the fly."""


def _normalized_equal(a: Optional[str], b: Optional[str]) -> bool:
    return (a or "").strip() == (b or "").strip()


def propose_contact_change(
    db: Session,
    *,
    centre_code: str,
    manager_name: Optional[str],
    manager_npid: Optional[str],
    manager_email: Optional[str],
    source: str,
    source_reference_id: Optional[int] = None,
) -> Optional[OrgNodeContactChangeRequest]:
    """Called from a response workflow right after a submission is
    recorded. Returns the created/refreshed pending request, or None if
    there's nothing to propose (no contact fields were actually submitted,
    or the submitted values already match what's already on file for that
    center -- no point notifying anyone about a no-op)."""
    if not (manager_name or manager_npid or manager_email):
        return None

    node = org_service.get_node_by_external_code(db, centre_code)
    if node is not None and (
        _normalized_equal(node.manager_name, manager_name)
        and _normalized_equal(node.manager_npid, manager_npid)
        and _normalized_equal(node.manager_email, manager_email)
    ):
        return None

    existing_pending = (
        db.query(OrgNodeContactChangeRequest)
        .filter(
            OrgNodeContactChangeRequest.centre_code_hint == centre_code,
            OrgNodeContactChangeRequest.status == "pending",
        )
        .first()
    )
    if existing_pending is not None:
        # One pending request per center at a time -- refresh it in place so
        # a center that submits again before the first request is reviewed
        # doesn't pile up duplicate notifications for the same change.
        existing_pending.proposed_manager_name = manager_name
        existing_pending.proposed_manager_npid = manager_npid
        existing_pending.proposed_manager_email = manager_email
        existing_pending.source = source
        existing_pending.source_reference_id = source_reference_id
        db.commit()
        db.refresh(existing_pending)
        return existing_pending

    request = OrgNodeContactChangeRequest(
        org_node_id=node.id if node else None,
        centre_code_hint=centre_code,
        proposed_manager_name=manager_name,
        proposed_manager_npid=manager_npid,
        proposed_manager_email=manager_email,
        source=source,
        source_reference_id=source_reference_id,
        status="pending",
    )
    db.add(request)
    db.commit()
    db.refresh(request)
    return request


def list_requests(db: Session, *, status: Optional[str] = None) -> list[OrgNodeContactChangeRequest]:
    query = db.query(OrgNodeContactChangeRequest)
    if status is not None:
        query = query.filter(OrgNodeContactChangeRequest.status == status)
    return query.order_by(OrgNodeContactChangeRequest.created_at.desc()).all()


def get_request_or_raise(db: Session, request_id: int) -> OrgNodeContactChangeRequest:
    request = (
        db.query(OrgNodeContactChangeRequest)
        .filter(OrgNodeContactChangeRequest.id == request_id)
        .first()
    )
    if request is None:
        raise ContactChangeRequestNotFoundError(f"Contact change request {request_id} not found")
    return request


def approve_request(
    db: Session, *, request: OrgNodeContactChangeRequest, approver: User
) -> OrgNodeContactChangeRequest:
    if request.status != "pending":
        raise AlreadyReviewedError(f"Request {request.id} is already {request.status}")
    if request.org_node_id is None:
        raise NoMatchingOrgNodeError(
            f"No center node matches code '{request.centre_code_hint}' -- create or fix that center in "
            "Org Hierarchy first, then have the center re-submit."
        )
    node = org_service.get_node(db, request.org_node_id)
    org_service.update_node(
        db,
        node=node,
        manager_name=request.proposed_manager_name,
        manager_npid=request.proposed_manager_npid,
        manager_email=request.proposed_manager_email,
    )
    request.status = "approved"
    request.reviewed_by_id = approver.id
    request.reviewed_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(request)
    return request


def reject_request(
    db: Session, *, request: OrgNodeContactChangeRequest, approver: User
) -> OrgNodeContactChangeRequest:
    if request.status != "pending":
        raise AlreadyReviewedError(f"Request {request.id} is already {request.status}")
    request.status = "rejected"
    request.reviewed_by_id = approver.id
    request.reviewed_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(request)
    return request

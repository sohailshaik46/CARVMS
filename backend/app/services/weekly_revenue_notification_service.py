"""Decision-triggered center notification for Weekly Revenue Closure.

Mirrors app/services/delayed_cash_notification_service.py, simplified to
match WRC's real decision model: only "considered"/"not_considered" exist
here (no needs_more_detail/needs_proof stage -- proven in the formula
analysis doc, not an arbitrary omission), so there is only one notice
shape, always fixed, never requiring a Vigilance-typed comment. Sending
is still always best-effort -- a missing mailbox or missing center email
never blocks the decision itself, same discipline as the DCB version.
"""

from dataclasses import dataclass
from typing import Optional

from sqlalchemy.orm import Session

from app.models.weekly_revenue_closure import WeeklyRevenueBillIncident
from app.services import email_connection_service, email_send_service, org_service

TERMINAL_DECISION_LABELS = {
    "considered": "Considered",
    "not_considered": "Not Considered",
}


@dataclass
class NotifyResult:
    sent: bool
    reason: Optional[str] = None


class InvalidNotifyRequestError(Exception):
    """Raised for a caller mistake (no decision recorded yet) -- the API
    layer turns this into a 400."""


def resolve_center_email(db: Session, centre_code: str) -> Optional[str]:
    node = org_service.get_node_by_external_code(db, centre_code)
    if node is None or not node.manager_email:
        return None
    return node.manager_email


def _send(db: Session, *, to: str, subject: str, body_text: str) -> NotifyResult:
    connection = email_connection_service.get_any_send_capable_connection(db)
    if connection is None:
        return NotifyResult(
            sent=False,
            reason=(
                "No Gmail account is connected with permission to send email -- connect (or reconnect) Gmail in "
                "Settings and grant the send permission."
            ),
        )
    try:
        access_token = email_connection_service.get_valid_access_token(db, connection)
    except email_connection_service.NotConnectedError as exc:
        return NotifyResult(sent=False, reason=str(exc))

    try:
        email_send_service.send_email(
            access_token=access_token,
            sender=connection.user.email,
            to=to,
            subject=subject,
            body_text=body_text,
        )
    except email_send_service.EmailSendError as exc:
        return NotifyResult(sent=False, reason=str(exc))

    return NotifyResult(sent=True)


def notify_incident_decision(db: Session, *, incident: WeeklyRevenueBillIncident) -> NotifyResult:
    decision = incident.considered
    if decision is None:
        raise InvalidNotifyRequestError("This incident has not been reviewed yet -- record a decision before notifying the center.")
    if decision not in TERMINAL_DECISION_LABELS:
        raise InvalidNotifyRequestError(f"'{decision}' is not a decision this feature knows how to notify for.")

    to = resolve_center_email(db, incident.centre_code)
    if to is None:
        return NotifyResult(
            sent=False,
            reason=f"No email on file for center {incident.centre_code} in the Org Master -- add manager_email there first.",
        )

    subject = f"Weekly Revenue Closure -- {incident.centre_name} ({incident.centre_code}): {TERMINAL_DECISION_LABELS[decision]}"
    body_text = (
        f"Your remark for the {incident.incident_date.isoformat()} incident ({incident.mis_final_remark}) has been reviewed.\n\n"
        f"Decision: {TERMINAL_DECISION_LABELS[decision]}\n\n"
        "No further action is required from you at this time.\n\n"
        "-- Vigilance"
    )
    return _send(db, to=to, subject=subject, body_text=body_text)

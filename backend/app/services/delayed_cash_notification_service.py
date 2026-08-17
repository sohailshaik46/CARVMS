"""Decision-triggered center notification for Delayed Cash Billing.

Two distinct flows, matching the two shapes of review decision:

1. Considered / Not Considered (terminal) -- a plain "your remark was
   <decision>" notice, no link, no further action expected.
2. Needs More Detail / Needs Proof (non-terminal) -- Vigilance's own typed
   comment, plus a freshly-minted response-portal link so the center can
   act on it.

Sending is always best-effort from the caller's point of view: a failure
here (no mailbox connected, no email on file for the center, Gmail
rejects the send) is reported back as a NotifyResult, never raised past
the API boundary, so a missing mailbox can never block Vigilance from
recording a decision -- consistent with how contact-change proposals and
every other side effect in this codebase already work.
"""

from dataclasses import dataclass
from typing import Optional

from sqlalchemy.orm import Session

from app.config.settings import settings
from app.models.delayed_cash_billing import DelayedCashBill, DelayedCashCenterPenalty
from app.services import delayed_cash_response_service as response_service
from app.services import email_connection_service, email_send_service, org_service

TERMINAL_DECISION_LABELS = {
    "considered": "Considered",
    "not_considered": "Not Considered",
}
FOLLOWUP_DECISION_LABELS = {
    "needs_more_detail": "Needs More Detail",
    "needs_proof": "Needs Proof",
}


@dataclass
class NotifyResult:
    sent: bool
    reason: Optional[str] = None


class InvalidNotifyRequestError(Exception):
    """Raised for caller-fixable problems (no decision yet, missing
    comment for a follow-up request) -- the API layer turns this into a
    400, distinct from a NotifyResult (which always means "decision is
    saved, only the email attempt failed")."""


def resolve_center_email(db: Session, centre_code: str) -> Optional[str]:
    """The center's notification address comes from the Org Master (the
    same manager_email an uploaded dataset's Center Code resolves against
    everywhere else) -- never from anything self-reported on the public
    portal, so a spoofed submission can't redirect where decisions get
    mailed."""
    node = org_service.get_node_by_external_code(db, centre_code)
    if node is None or not node.manager_email:
        return None
    return node.manager_email


def _get_center_penalty(db: Session, bill: DelayedCashBill) -> Optional[DelayedCashCenterPenalty]:
    return (
        db.query(DelayedCashCenterPenalty)
        .filter(
            DelayedCashCenterPenalty.batch_id == bill.batch_id,
            DelayedCashCenterPenalty.centre_code == bill.centre_code,
        )
        .first()
    )


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


def notify_bill_decision(db: Session, *, bill: DelayedCashBill, comment: Optional[str] = None) -> NotifyResult:
    """Sends whichever notification matches this bill's current decision.
    Raises InvalidNotifyRequestError for a caller mistake (no decision
    yet, or a follow-up request missing its required comment) -- anything
    past that point is a NotifyResult, never an exception."""
    decision = bill.considered
    if decision is None:
        raise InvalidNotifyRequestError("This bill has not been reviewed yet -- record a decision before notifying the center.")
    if decision not in TERMINAL_DECISION_LABELS and decision not in FOLLOWUP_DECISION_LABELS:
        raise InvalidNotifyRequestError(f"'{decision}' is not a decision this feature knows how to notify for.")
    if decision in FOLLOWUP_DECISION_LABELS and (not comment or not comment.strip()):
        # A caller-fixable mistake -- check it before touching the center's
        # email or the mailbox, so it's always a clean 400, never masked by
        # an unrelated "no email on file"/"not connected" NotifyResult.
        raise InvalidNotifyRequestError("A remark is required before sending a Needs More Detail/Needs Proof request.")

    to = resolve_center_email(db, bill.centre_code)
    if to is None:
        return NotifyResult(
            sent=False,
            reason=f"No email on file for center {bill.centre_code} in the Org Master -- add manager_email there first.",
        )

    if decision in TERMINAL_DECISION_LABELS:
        subject = f"Delayed Cash Billing -- {bill.centre_name} ({bill.centre_code}): {TERMINAL_DECISION_LABELS[decision]}"
        body_text = (
            f"Your remark for sales bill {bill.sales_bill} has been reviewed.\n\n"
            f"Decision: {TERMINAL_DECISION_LABELS[decision]}\n\n"
            "No further action is required from you at this time.\n\n"
            "-- Vigilance"
        )
        return _send(db, to=to, subject=subject, body_text=body_text)

    # Only FOLLOWUP_DECISION_LABELS remains at this point -- TERMINAL_DECISION_LABELS
    # returned above, and anything else was already rejected.
    center_penalty = _get_center_penalty(db, bill)
    response_url = None
    if center_penalty is not None:
        center_penalty = response_service.generate_response_link_token(db, center_penalty=center_penalty)
        response_url = f"{settings.FRONTEND_URL}/respond/delayed-cash/{center_penalty.response_token}"

    subject = f"Delayed Cash Billing -- {bill.centre_name} ({bill.centre_code}): {FOLLOWUP_DECISION_LABELS[decision]}"
    body_lines = [
        f"Your remark for sales bill {bill.sales_bill} needs more information before it can be finalized.",
        "",
        "Vigilance's remark:",
        comment.strip(),
    ]
    if response_url:
        body_lines += ["", f"Please submit your response here: {response_url}"]
    body_lines += ["", "-- Vigilance"]
    return _send(db, to=to, subject=subject, body_text="\n".join(body_lines))

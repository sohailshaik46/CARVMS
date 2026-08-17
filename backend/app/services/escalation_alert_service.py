"""48-hour response-window escalation SMS -- alerts an Admin (never the
center itself; this is an internal "go check this" nudge, not a
disciplinary notice to the center) once a DCB/WRC case's response deadline
passes with no submission.

Deliberately NOT a background job: there is no scheduler/cron in this app
(see docs/SMS_SETUP.md). `check_and_send_overdue_alerts` is a plain
function an admin (or an external cron hitting POST /admin/escalations/check)
calls whenever they want the check to run "now" -- it is idempotent (a case
already alerted, via escalation_sms_sent_at, is never re-alerted) so calling
it on a schedule from outside is safe and is exactly how real periodicity
would be added without changing anything in here.
"""

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.delayed_cash_billing import DelayedCashCaseResponse, DelayedCashCenterPenalty
from app.models.user import User
from app.models.weekly_revenue_closure import WeeklyRevenueCenterCase
from app.services.sms_provider import NotConfiguredError, SmsSendError, get_sms_provider


@dataclass
class EscalationCheckResult:
    dcb_overdue_found: int = 0
    wrc_overdue_found: int = 0
    admins_notified: int = 0
    sms_attempted: int = 0
    sms_sent: int = 0
    sms_provider_not_configured: bool = False


def _admin_phone_numbers(db: Session) -> list[str]:
    return [
        u.phone_number
        for u in db.query(User).filter(User.role == "Admin", User.is_active.is_(True)).all()
        if u.phone_number
    ]


def check_and_send_overdue_alerts(db: Session) -> EscalationCheckResult:
    now = datetime.now(timezone.utc)
    result = EscalationCheckResult()

    overdue_dcb = (
        db.query(DelayedCashCenterPenalty)
        .filter(
            DelayedCashCenterPenalty.response_token_expires_at.isnot(None),
            DelayedCashCenterPenalty.response_token_expires_at < now,
            DelayedCashCenterPenalty.escalation_sms_sent_at.is_(None),
        )
        .all()
    )
    overdue_dcb = [
        p
        for p in overdue_dcb
        if not db.query(DelayedCashCaseResponse).filter_by(center_penalty_id=p.id).first()
    ]
    result.dcb_overdue_found = len(overdue_dcb)

    overdue_wrc = (
        db.query(WeeklyRevenueCenterCase)
        .filter(
            WeeklyRevenueCenterCase.response_token_expires_at.isnot(None),
            WeeklyRevenueCenterCase.response_token_expires_at < now,
            WeeklyRevenueCenterCase.escalation_sms_sent_at.is_(None),
        )
        .all()
    )
    overdue_wrc = [c for c in overdue_wrc if not c.responses]
    result.wrc_overdue_found = len(overdue_wrc)

    if not overdue_dcb and not overdue_wrc:
        return result

    admin_numbers = _admin_phone_numbers(db)
    result.admins_notified = len(admin_numbers)
    provider = get_sms_provider()

    for penalty in overdue_dcb:
        message = (
            f"CARVMS: Delayed Cash Billing response window closed with no reply -- "
            f"center {penalty.centre_code} ({penalty.centre_name}). Please review."
        )
        _send_to_admins(provider, admin_numbers, message, result)
        penalty.escalation_sms_sent_at = now

    for case in overdue_wrc:
        message = (
            f"CARVMS: Weekly Revenue Closure response window closed with no reply -- "
            f"center {case.centre_code} ({case.centre_name}). Please review."
        )
        _send_to_admins(provider, admin_numbers, message, result)
        case.escalation_sms_sent_at = now

    db.commit()
    return result


def _send_to_admins(provider, admin_numbers: list[str], message: str, result: EscalationCheckResult) -> None:
    for number in admin_numbers:
        result.sms_attempted += 1
        try:
            provider.send(number, message)
            result.sms_sent += 1
        except NotConfiguredError:
            result.sms_provider_not_configured = True
        except SmsSendError:
            pass

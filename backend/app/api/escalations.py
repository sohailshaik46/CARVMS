from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth import roles
from app.auth.dependencies import require_role
from app.database.database import get_db
from app.models.user import User
from app.services import escalation_alert_service

router = APIRouter(prefix="/admin/escalations", tags=["Escalation Alerts"])


@router.post("/check")
def check_overdue_cases(
    db: Session = Depends(get_db),
    _admin: User = Depends(require_role(roles.ADMIN)),
):
    """Runs the 48-hour-overdue check now and sends SMS to Admins with a
    phone number on file for anything newly overdue. Idempotent -- a case
    already alerted is never re-alerted. See docs/SMS_SETUP.md for why this
    is a manually/externally-triggered check rather than an automatic job."""
    result = escalation_alert_service.check_and_send_overdue_alerts(db)
    return result

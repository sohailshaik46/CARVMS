from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth import roles
from app.auth.dependencies import require_role
from app.database.database import get_db
from app.models.user import User
from app.schemas.metrics import DashboardSummaryOut
from app.services.metrics import MetricFilters, compute_summary

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])

# Billing data is sensitive and, everywhere else in this codebase (batches,
# review queue, centers activity), gated to Admin/Auditor -- the Dashboard
# is no exception now that it computes from the same data.
VIGILANCE_ROLES = (roles.ADMIN, roles.AUDITOR)


@router.get("/summary", response_model=DashboardSummaryOut)
def dashboard_summary(
    period_from: date | None = None,
    period_to: date | None = None,
    db: Session = Depends(get_db),
    _user: User = Depends(require_role(*VIGILANCE_ROLES)),
):
    filters = MetricFilters(period_from=period_from, period_to=period_to)
    return compute_summary(db, filters)

"""Import every model module here so Base.metadata always knows about all of
them -- Alembic autogenerate and tests' Base.metadata.create_all() both rely
on this. Adding a new model module without importing it here means Alembic
will silently ignore it."""

from app.models.user import User  # noqa: F401
from app.models.user_preference import UserPreference  # noqa: F401
from app.models.otp import OtpCode  # noqa: F401
from app.models.audit_log import AuditLog  # noqa: F401
from app.models.org import OrgDimension, OrgNode, OrgNodeContactChangeRequest  # noqa: F401
from app.models.report import ReportTemplate, ReportHistory  # noqa: F401
from app.models.auto_validation import AutoValidationRule  # noqa: F401
from app.models.dashboard_layout import DashboardLayout  # noqa: F401
from app.models.center_scoring import CenterScoringWeight  # noqa: F401
from app.models.email_connection import EmailConnectionRequest, EmailConnection  # noqa: F401
from app.models.delayed_cash_billing import (  # noqa: F401
    DelayedCashPenaltyRule,
    DelayedCashUploadBatch,
    DelayedCashBill,
    DelayedCashCenterPenalty,
    DelayedCashCaseResponse,
    DelayedCashCenterActivity,
)
from app.models.weekly_revenue_closure import (  # noqa: F401
    WeeklyRevenueClosureRule,
    WeeklyRevenueClosureBatch,
    WeeklyRevenueBillIncident,
    WeeklyRevenueNoRemarkIncident,
    WeeklyRevenueCenterPenalty,
    WeeklyRevenueRolePenalty,
    WeeklyRevenueCenterCase,
    WeeklyRevenueCaseResponse,
    WeeklyRevenueCenterActivity,
)

__all__ = [
    "User",
    "UserPreference",
    "OtpCode",
    "AuditLog",
    "OrgDimension",
    "OrgNode",
    "OrgNodeContactChangeRequest",
    "ReportTemplate",
    "ReportHistory",
    "AutoValidationRule",
    "DashboardLayout",
    "CenterScoringWeight",
    "EmailConnectionRequest",
    "EmailConnection",
    "DelayedCashPenaltyRule",
    "DelayedCashUploadBatch",
    "DelayedCashBill",
    "DelayedCashCenterPenalty",
    "DelayedCashCaseResponse",
    "DelayedCashCenterActivity",
    "WeeklyRevenueClosureRule",
    "WeeklyRevenueClosureBatch",
    "WeeklyRevenueBillIncident",
    "WeeklyRevenueNoRemarkIncident",
    "WeeklyRevenueCenterPenalty",
    "WeeklyRevenueRolePenalty",
    "WeeklyRevenueCenterCase",
    "WeeklyRevenueCaseResponse",
    "WeeklyRevenueCenterActivity",
]

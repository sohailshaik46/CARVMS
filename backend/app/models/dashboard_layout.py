from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, JSON, String, func
from sqlalchemy.orm import relationship

from app.database.database import Base

# What a layout's config actually controls -- purely presentation (which
# KPI cards/charts show, and a default filter set to pre-apply). It never
# stores computed numbers; applying a layout just changes what the Metric
# Engine is asked to compute and how the result is displayed. This is what
# keeps a saved layout from ever showing stale figures.
DEFAULT_KPI_KEYS = (
    "total_audits",
    "open_audits",
    "closed_or_cancelled_audits",
    "critical_open_findings",
    "total_financial_exposure",
    "total_recoverable_amount",
)


class DashboardLayout(Base):
    """A saved dashboard view -- 'My Dashboard', 'South Zone Dashboard',
    'Monthly Management Dashboard'. Shared layouts are visible to every
    authenticated user (read-only unless you're the owner or an Admin);
    private ones are visible only to their owner.
    """

    __tablename__ = "dashboard_layouts"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    description = Column(String, nullable=True)
    config = Column(JSON, nullable=False)  # {"visible_kpis": [...], "show_status_chart": bool, "show_severity_chart": bool, "default_filters": {...}}
    is_shared = Column(Boolean, nullable=False, default=False, server_default="0")

    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    owner = relationship("User")

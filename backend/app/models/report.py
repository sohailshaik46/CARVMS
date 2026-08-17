from sqlalchemy import JSON, CheckConstraint, Column, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import relationship

from app.database.database import Base

REPORT_FORMATS = ("csv", "xlsx", "pdf", "docx", "pptx")
REPORT_HISTORY_STATUSES = ("completed", "failed")


class ReportTemplate(Base):
    """A saved, named filter set -- 'Monthly Vigilance Report' -- reusable
    every period with whatever data is current at run time. Templates never
    store a result; they store the *question* (filters), and every run reads
    live from the Metric Engine. This is what keeps a template's output
    consistent with the dashboard automatically, with no separate sync step.
    """

    __tablename__ = "report_templates"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    description = Column(String, nullable=True)
    filters = Column(JSON, nullable=False)  # {date_from, date_to, status, center_node_id}

    created_by_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    created_by = relationship("User")


class ReportHistory(Base):
    """One row per report generation -- template-based or ad-hoc. Never
    stores the generated file (see brief: don't duplicate binaries); a
    'regenerate' action re-runs the same filters through the same Metric
    Engine functions, so a re-download always reflects current data, not a
    stale snapshot -- and can never disagree with the live dashboard for
    the same filters.
    """

    __tablename__ = "report_history"
    __table_args__ = (
        CheckConstraint(f"format IN {REPORT_FORMATS}", name="ck_report_history_format_valid"),
        CheckConstraint(f"status IN {REPORT_HISTORY_STATUSES}", name="ck_report_history_status_valid"),
    )

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    template_id = Column(Integer, ForeignKey("report_templates.id"), nullable=True, index=True)
    filters_used = Column(JSON, nullable=False)
    format = Column(String, nullable=False)
    status = Column(String, nullable=False, default="completed")
    error = Column(String, nullable=True)

    generated_by_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    generated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    regenerated_from_id = Column(Integer, ForeignKey("report_history.id"), nullable=True)

    template = relationship("ReportTemplate")
    generated_by = relationship("User")

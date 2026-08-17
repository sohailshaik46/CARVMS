from sqlalchemy import CheckConstraint, Column, DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.orm import relationship

from app.database.database import Base

# Renamed 2026-08-14 from the Audits-era financial_exposure/recovery_rate/
# open_findings/repeat_findings when that domain was deleted -- these four
# now reflect SOP-non-compliance across Delayed Cash Billing + Weekly
# Revenue Closure instead. "lower_is_better" says how a raw value maps to
# "good" before normalization -- see center_scoring_service.py. This tuple
# is the complete, real list of what is scored; nothing here is a
# placeholder for a component that doesn't exist yet.
CENTER_SCORE_COMPONENTS = (
    "non_compliance_rate",
    "repeat_violations",
    "outstanding_penalty",
    "unresolved_cases",
)

COMPONENT_LOWER_IS_BETTER = {
    "non_compliance_rate": True,
    "repeat_violations": True,
    "outstanding_penalty": True,
    "unresolved_cases": True,
}

COMPONENT_LABELS = {
    "non_compliance_rate": "Non-Compliance Rate",
    "repeat_violations": "Repeat SOP Violations",
    "outstanding_penalty": "Outstanding Penalty",
    "unresolved_cases": "Unresolved Cases",
}


class CenterScoringWeight(Base):
    """Admin-configurable weight for one scoring component. Seeded with
    EQUAL weights (0.25 each) by migration, per explicit user instruction
    on 2026-08-13 ("start with equal weights, I'll adjust later") -- this
    is not an invented business answer, it's the documented placeholder the
    user asked for, changeable via PATCH /center-scoring/weights/{key} at
    any time without a migration.
    """

    __tablename__ = "center_scoring_weights"
    __table_args__ = (
        CheckConstraint(f"component_key IN {CENTER_SCORE_COMPONENTS}", name="ck_center_scoring_component_valid"),
    )

    id = Column(Integer, primary_key=True, index=True)
    component_key = Column(String, unique=True, nullable=False, index=True)
    weight = Column(Float, nullable=False)

    updated_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    updated_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    updated_by = relationship("User")

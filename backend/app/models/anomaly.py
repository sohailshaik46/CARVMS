from sqlalchemy import JSON, CheckConstraint, Column, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import relationship

from app.database.database import Base

# Deliberately narrow, real ruleset -- not a claim to cover the full
# forensic taxonomy the brief lists (impossible chronology, FASTag
# mismatches, travel inconsistencies, etc.). Those need domain-specific
# column semantics this generic engine cannot honestly infer. What's here
# is real and general: exact duplicates, an over-threshold repeated value,
# and standard IQR statistical outliers.
ANOMALY_RULE_CODES = ("duplicate_row", "repeated_value", "outlier_iqr")

ANOMALY_RISK_LEVELS = ("Low", "Medium", "High", "Critical")

# "Exception" / "Red Flag" language per the brief -- never a fraud
# conclusion. There is no "Escalated" status: the Audits/Findings case-
# management domain this used to promote into was deleted (2026-08-14, per
# explicit user request -- "iam not performing any audits from here").
# Anomalies stay dataset-scoped and informational: a human dismisses one
# or leaves it open, full stop.
ANOMALY_STATUSES = ("Open", "Dismissed")


class DatasetAnomaly(Base):
    __tablename__ = "dataset_anomalies"
    __table_args__ = (
        CheckConstraint(f"rule_code IN {ANOMALY_RULE_CODES}", name="ck_anomalies_rule_valid"),
        CheckConstraint(f"risk_level IN {ANOMALY_RISK_LEVELS}", name="ck_anomalies_risk_valid"),
        CheckConstraint(f"status IN {ANOMALY_STATUSES}", name="ck_anomalies_status_valid"),
    )

    id = Column(Integer, primary_key=True, index=True)
    dataset_id = Column(Integer, ForeignKey("datasets.id"), nullable=False, index=True)

    rule_code = Column(String, nullable=False, index=True)
    entity_description = Column(String, nullable=False)   # e.g. "Row 5 (claim_id=C123)"
    observed_value = Column(JSON, nullable=False)
    expected_baseline = Column(JSON, nullable=False)
    difference = Column(JSON, nullable=False)
    risk_level = Column(String, nullable=False)
    potential_impact = Column(String, nullable=True)
    evidence_source = Column(String, nullable=False)      # dataset name + row reference
    recommended_verification = Column(String, nullable=False)

    status = Column(String, nullable=False, default="Open")
    dismissed_reason = Column(String, nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    dataset = relationship("Dataset")

from sqlalchemy import JSON, CheckConstraint, Column, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import relationship

from app.database.database import Base

RECONCILIATION_STATUSES = ("completed", "failed")


class Reconciliation(Base):
    """A single dataset-vs-dataset comparison run. Summary counts live as
    real columns (cheap, queryable); the capped example rows live in
    details_json -- bounded in size (see reconciliation_service.MAX_EXAMPLES),
    never the full row set, so this never becomes a blob table."""

    __tablename__ = "reconciliations"
    __table_args__ = (
        CheckConstraint(f"status IN {RECONCILIATION_STATUSES}", name="ck_reconciliations_status_valid"),
    )

    id = Column(Integer, primary_key=True, index=True)
    dataset_a_id = Column(Integer, ForeignKey("datasets.id"), nullable=False, index=True)
    dataset_b_id = Column(Integer, ForeignKey("datasets.id"), nullable=False, index=True)
    key_column_a = Column(String, nullable=False)
    key_column_b = Column(String, nullable=False)
    compare_columns = Column(JSON, nullable=True)  # null = compare every shared column

    status = Column(String, nullable=False)
    error = Column(String, nullable=True)

    matched_count = Column(Integer, nullable=True)
    mismatched_count = Column(Integer, nullable=True)
    missing_in_b_count = Column(Integer, nullable=True)
    extra_in_b_count = Column(Integer, nullable=True)
    details_json = Column(JSON, nullable=True)

    run_by_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    run_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    dataset_a = relationship("Dataset", foreign_keys=[dataset_a_id])
    dataset_b = relationship("Dataset", foreign_keys=[dataset_b_id])
    run_by = relationship("User")

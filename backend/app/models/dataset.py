from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    func,
)
from sqlalchemy.orm import relationship

from app.database.database import Base

# What we can actually store. Only "csv" and "excel" get real profiling
# (row/column counts, dtypes, null rates, a quality score) in this pass --
# pdf/word/pptx/image are stored with correct metadata but are NOT tabular,
# so pretending to profile them would mean fabricating numbers. Their
# status stays "uploaded" rather than "clean"/"failed" from profiling.
DATASET_SOURCE_TYPES = ("csv", "excel", "pdf", "word", "pptx", "image")

DATASET_STATUSES = ("uploaded", "profiling", "clean", "failed", "archived")

PROFILABLE_SOURCE_TYPES = ("csv", "excel")


class Dataset(Base):
    __tablename__ = "datasets"
    __table_args__ = (
        CheckConstraint(f"source_type IN {DATASET_SOURCE_TYPES}", name="ck_datasets_source_type_valid"),
        CheckConstraint(f"status IN {DATASET_STATUSES}", name="ck_datasets_status_valid"),
    )

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    source_type = Column(String, nullable=False)
    original_filename = Column(String, nullable=False)
    storage_path = Column(String, nullable=False)
    checksum = Column(String, nullable=False)

    uploaded_by_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    uploaded_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    version = Column(Integer, nullable=False, default=1)
    status = Column(String, nullable=False, default="uploaded")

    row_count = Column(Integer, nullable=True)
    column_count = Column(Integer, nullable=True)
    duplicate_row_count = Column(Integer, nullable=True)
    quality_score = Column(Float, nullable=True)
    profiling_error = Column(String, nullable=True)

    lineage_of_id = Column(Integer, ForeignKey("datasets.id"), nullable=True)

    uploaded_by = relationship("User")
    lineage_of = relationship("Dataset", remote_side=[id])
    columns = relationship("DatasetColumn", back_populates="dataset", cascade="all, delete-orphan")


class DatasetColumn(Base):
    __tablename__ = "dataset_columns"

    id = Column(Integer, primary_key=True, index=True)
    dataset_id = Column(Integer, ForeignKey("datasets.id"), nullable=False, index=True)
    name = Column(String, nullable=False)
    inferred_type = Column(String, nullable=False)
    null_rate = Column(Float, nullable=False, default=0.0)
    # Soft match against org_dimensions.key by normalized column name --
    # not a hard FK, since the mapping is a heuristic suggestion, not a
    # guaranteed-correct link.
    mapped_dimension = Column(String, nullable=True)

    dataset = relationship("Dataset", back_populates="columns")

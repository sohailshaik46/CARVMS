from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class DatasetOut(BaseModel):
    id: int
    name: str
    source_type: str
    original_filename: str
    checksum: str
    uploaded_by_id: int
    uploaded_at: datetime
    version: int
    status: str
    row_count: Optional[int]
    column_count: Optional[int]
    duplicate_row_count: Optional[int]
    quality_score: Optional[float]
    profiling_error: Optional[str]
    lineage_of_id: Optional[int]

    model_config = {"from_attributes": True}


class DatasetColumnOut(BaseModel):
    id: int
    name: str
    inferred_type: str
    null_rate: float
    mapped_dimension: Optional[str]

    model_config = {"from_attributes": True}

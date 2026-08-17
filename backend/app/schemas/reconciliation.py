from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class ReconciliationCreate(BaseModel):
    dataset_a_id: int
    dataset_b_id: int
    key_column_a: str
    key_column_b: str
    compare_columns: Optional[list[str]] = None


class ReconciliationOut(BaseModel):
    id: int
    dataset_a_id: int
    dataset_b_id: int
    key_column_a: str
    key_column_b: str
    compare_columns: Optional[list[str]]
    status: str
    error: Optional[str]
    matched_count: Optional[int]
    mismatched_count: Optional[int]
    missing_in_b_count: Optional[int]
    extra_in_b_count: Optional[int]
    run_by_id: int
    run_at: datetime

    model_config = {"from_attributes": True}


class ReconciliationDetailOut(ReconciliationOut):
    details_json: Optional[dict]

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, Field


class ReportFiltersIn(BaseModel):
    period_from: Optional[date] = None
    period_to: Optional[date] = None


class ReportTemplateCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: Optional[str] = Field(default=None, max_length=1000)
    filters: ReportFiltersIn


class ReportTemplateOut(BaseModel):
    id: int
    name: str
    description: Optional[str]
    filters: dict
    created_by_id: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ReportHistoryOut(BaseModel):
    id: int
    name: str
    template_id: Optional[int]
    filters_used: dict
    format: str
    status: str
    error: Optional[str]
    generated_by_id: int
    generated_at: datetime
    regenerated_from_id: Optional[int]

    model_config = {"from_attributes": True}

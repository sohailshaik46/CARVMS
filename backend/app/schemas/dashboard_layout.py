from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator

from app.models.dashboard_layout import DEFAULT_KPI_KEYS


class DashboardLayoutConfig(BaseModel):
    visible_kpis: list[str] = Field(default_factory=lambda: list(DEFAULT_KPI_KEYS))
    show_status_chart: bool = True
    show_severity_chart: bool = True
    default_filters: dict = Field(default_factory=dict)

    @field_validator("visible_kpis")
    @classmethod
    def kpis_must_be_known(cls, v: list[str]) -> list[str]:
        unknown = [k for k in v if k not in DEFAULT_KPI_KEYS]
        if unknown:
            raise ValueError(f"Unknown KPI key(s) {unknown}; must be a subset of {DEFAULT_KPI_KEYS}")
        return v


class DashboardLayoutCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: Optional[str] = Field(default=None, max_length=1000)
    config: DashboardLayoutConfig
    is_shared: bool = False


class DashboardLayoutUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    description: Optional[str] = Field(default=None, max_length=1000)
    config: Optional[DashboardLayoutConfig] = None
    is_shared: Optional[bool] = None


class DashboardLayoutOut(BaseModel):
    id: int
    name: str
    description: Optional[str]
    config: dict
    is_shared: bool
    owner_id: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

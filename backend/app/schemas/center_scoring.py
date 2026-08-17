from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class CenterScoringWeightOut(BaseModel):
    id: int
    component_key: str
    weight: float
    updated_by_id: Optional[int]
    updated_at: datetime

    model_config = {"from_attributes": True}


class CenterScoringWeightUpdate(BaseModel):
    weight: float = Field(ge=0)


class ComponentScoreOut(BaseModel):
    raw: Optional[float]
    normalized: Optional[float]


class CenterRankingOut(BaseModel):
    rank: int
    centre_code: str
    centre_name: str
    case_count: int
    components: dict[str, ComponentScoreOut]
    composite_score: Optional[float]

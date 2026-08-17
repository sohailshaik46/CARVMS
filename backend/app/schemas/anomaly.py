from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator

from app.models.anomaly import ANOMALY_RULE_CODES


class AnomalyScanRequest(BaseModel):
    rules: list[str] = Field(min_length=1)
    repeated_value_column: Optional[str] = None
    repeated_value_threshold: int = 3
    outlier_column: Optional[str] = None
    outlier_iqr_multiplier: float = 1.5

    @field_validator("rules")
    @classmethod
    def rules_must_be_known(cls, v: list[str]) -> list[str]:
        unknown = [r for r in v if r not in ANOMALY_RULE_CODES]
        if unknown:
            raise ValueError(f"Unknown rule(s) {unknown}; must be one of {ANOMALY_RULE_CODES}")
        return v


class AnomalyOut(BaseModel):
    id: int
    dataset_id: int
    rule_code: str
    entity_description: str
    observed_value: dict
    expected_baseline: dict
    difference: dict
    risk_level: str
    potential_impact: Optional[str]
    evidence_source: str
    recommended_verification: str
    status: str
    dismissed_reason: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}


class AnomalyDismissRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=500)

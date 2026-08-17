from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class AutoValidationRuleOut(BaseModel):
    id: int
    bucket: str
    category: str
    keyword_phrase: str
    decision_label: str
    reason: Optional[str]
    notes: Optional[str]
    applies_to: str
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class AutoValidationRuleIn(BaseModel):
    bucket: str = Field(pattern="^(considered|not_considered)$")
    category: str = Field(min_length=1, max_length=200)
    keyword_phrase: str = Field(min_length=1, max_length=500)
    decision_label: str = Field(min_length=1, max_length=200)
    reason: Optional[str] = None
    notes: Optional[str] = None
    applies_to: str = Field(default="both", pattern="^(both|dcb|wrc)$")


class AutoValidationRuleActiveIn(BaseModel):
    is_active: bool


class AutoValidationOverrideIn(BaseModel):
    bucket: str = Field(pattern="^(considered|not_considered|manual_check)$")
    note: Optional[str] = Field(default=None, max_length=2000)


class AutoValidationResponseOut(BaseModel):
    """One case-response's auto-validation result, denormalized with enough
    center/batch context for the frontend to both list it and click through
    to the underlying bill(s)/incident(s) -- populated by the API layer,
    not a 1:1 mirror of the DB row (mirrors BillOut's center_penalty_id
    pattern for the same reason: the bill<->case link is by
    batch_id+centre_code, no real FK)."""

    id: int
    engine: str  # "dcb" | "wrc"
    case_or_penalty_id: int  # center_penalty_id (DCB) or case_id (WRC) -- what Review Queue filters need
    batch_id: int
    centre_code: str
    centre_name: str
    reason: str
    submitted_at: datetime
    auto_bucket: Optional[str]
    auto_category: Optional[str]
    auto_matched_keyword: Optional[str]
    auto_decision_label: Optional[str]
    auto_reason: Optional[str]
    auto_evaluated_at: Optional[datetime]
    admin_override_bucket: Optional[str]
    admin_override_by_name: Optional[str]
    admin_override_at: Optional[datetime]
    admin_override_note: Optional[str]
    effective_bucket: Optional[str]

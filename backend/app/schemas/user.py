from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, field_validator

from app.auth.roles import ALL_ROLES


class UserAdminOut(BaseModel):
    id: int
    username: str
    email: EmailStr
    role: str
    is_active: bool
    org_node_id: Optional[int]
    phone_number: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class RoleUpdateRequest(BaseModel):
    role: str

    @field_validator("role")
    @classmethod
    def role_must_be_known(cls, v: str) -> str:
        if v not in ALL_ROLES:
            raise ValueError(f"role must be one of {ALL_ROLES}")
        return v


class ActiveUpdateRequest(BaseModel):
    is_active: bool


class OrgNodeAssignRequest(BaseModel):
    # None deliberately allowed -- unassigns the user from any org node
    # (e.g. a manager who has left, before a replacement is assigned).
    org_node_id: Optional[int] = None

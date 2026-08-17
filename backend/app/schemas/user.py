from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.auth.roles import ALL_ROLES
from app.schemas.auth import _validate_phone


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


class AdminUserCreateRequest(BaseModel):
    """Admin-driven account creation -- distinct from public self-registration
    (/auth/register): an Admin can hand someone a ready-made account with a
    real role already set, rather than everyone landing as the self-register
    default and needing a follow-up promotion."""

    username: str = Field(min_length=3, max_length=50)
    email: EmailStr
    password: str = Field(min_length=8, max_length=72)
    phone_number: Optional[str] = None
    role: str = "Auditor"

    @field_validator("phone_number")
    @classmethod
    def _phone_valid(cls, v: Optional[str]) -> Optional[str]:
        return _validate_phone(v) if v else v

    @field_validator("role")
    @classmethod
    def _role_valid(cls, v: str) -> str:
        if v not in ALL_ROLES:
            raise ValueError(f"role must be one of {ALL_ROLES}")
        return v

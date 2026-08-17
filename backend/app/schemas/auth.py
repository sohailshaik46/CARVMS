import re
from typing import Optional

from pydantic import BaseModel, EmailStr, Field, field_validator

# E.164-ish: a leading + then 8-15 digits -- permissive about country code
# length (this app's own users are +91 numbers today, but the format isn't
# hardcoded to India). Rejects anything that isn't plausibly a real mobile
# number rather than trying to fully validate one.
_PHONE_RE = re.compile(r"^\+[1-9]\d{7,14}$")


def _validate_phone(v: str) -> str:
    v = v.strip()
    if not _PHONE_RE.match(v):
        raise ValueError("phone_number must be in international format, e.g. +919154187948")
    return v


class UserRegister(BaseModel):
    # NOTE: role is deliberately NOT accepted here. Every self-registered
    # user gets roles.DEFAULT_SELF_REGISTER_ROLE. Privileged roles can only
    # be granted by an existing Admin via an admin-only endpoint (P1).
    username: str = Field(min_length=3, max_length=50)
    email: EmailStr
    password: str = Field(min_length=8, max_length=72)
    # Optional at the API level (existing automated callers/tests never
    # supplied one, and never should have to just to register a test user
    # for something unrelated) but required by the Register PAGE's own
    # form -- every real account created through the UI is asked for a
    # number so password-reset OTPs and escalation alerts reach the right
    # person, never a shared inbox/number. See app/models/user.py's note.
    phone_number: Optional[str] = None

    @field_validator("phone_number")
    @classmethod
    def _phone_valid(cls, v: Optional[str]) -> Optional[str]:
        return _validate_phone(v) if v else v


class UserLogin(BaseModel):
    username: str
    password: str = Field(max_length=72)


class Token(BaseModel):
    access_token: str
    token_type: str


class UserOut(BaseModel):
    id: int
    username: str
    email: EmailStr
    role: str
    is_active: bool
    phone_number: Optional[str] = None

    model_config = {"from_attributes": True}


class PasswordChangeRequest(BaseModel):
    """Self-service change -- requires the CURRENT password, unlike an
    admin-driven reset. This is the only password-change path today; the
    OTP-based "forgot password" flow (no current password known) is
    separate, see schemas/otp.py."""

    current_password: str = Field(max_length=72)
    new_password: str = Field(min_length=8, max_length=72)


class PhoneNumberUpdateRequest(BaseModel):
    phone_number: str

    @field_validator("phone_number")
    @classmethod
    def _phone_valid(cls, v: str) -> str:
        return _validate_phone(v)

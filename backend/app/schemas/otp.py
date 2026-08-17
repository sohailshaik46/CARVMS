from pydantic import BaseModel, Field, field_validator

from app.schemas.auth import _validate_phone


class ForgotPasswordRequest(BaseModel):
    phone_number: str

    @field_validator("phone_number")
    @classmethod
    def _phone_valid(cls, v: str) -> str:
        return _validate_phone(v)


class ForgotPasswordResponse(BaseModel):
    message: str = "If that number is registered, a reset code has been sent."


class ResetPasswordRequest(BaseModel):
    phone_number: str
    code: str = Field(min_length=4, max_length=8)
    new_password: str = Field(min_length=8, max_length=72)

    @field_validator("phone_number")
    @classmethod
    def _phone_valid(cls, v: str) -> str:
        return _validate_phone(v)

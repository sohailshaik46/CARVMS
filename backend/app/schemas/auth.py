from pydantic import BaseModel, EmailStr, Field


class UserRegister(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    email: EmailStr
    password: str = Field(min_length=8, max_length=72)
    # NOTE: role is deliberately NOT accepted here. Every self-registered
    # user gets roles.DEFAULT_SELF_REGISTER_ROLE. Privileged roles can only
    # be granted by an existing Admin via an admin-only endpoint (P1).


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

    model_config = {"from_attributes": True}

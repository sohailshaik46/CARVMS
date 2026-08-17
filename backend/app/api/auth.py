from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database.database import get_db
from app.schemas.auth import (
    PasswordChangeRequest,
    PhoneNumberUpdateRequest,
    UserRegister,
    UserLogin,
    Token,
    UserOut,
)
from app.schemas.otp import ForgotPasswordRequest, ForgotPasswordResponse, ResetPasswordRequest
from app.services import otp_service, user_service
from app.services.otp_service import InvalidOrExpiredOtpError
from app.services.user_service import create_user, authenticate_user, WrongPasswordError
from app.auth.security import create_access_token
from app.auth.dependencies import get_current_user
from app.models.user import User

router = APIRouter(
    prefix="/auth",
    tags=["Authentication"]
)


# ==========================
# Register
# ==========================

@router.post("/register", status_code=201)
def register_user(
    user: UserRegister,
    db: Session = Depends(get_db)
):
    new_user = create_user(db, user)

    if new_user is None:
        raise HTTPException(
            status_code=400,
            detail="Username or email already exists"
        )

    return {
        "message": "User registered successfully"
    }


# ==========================
# Login
# ==========================

@router.post("/login", response_model=Token)
def login(
    user: UserLogin,
    db: Session = Depends(get_db)
):
    db_user = authenticate_user(
        db,
        user.username,
        user.password
    )

    if db_user is None:
        raise HTTPException(
            status_code=401,
            detail="Invalid username or password"
        )

    if not db_user.is_active:
        raise HTTPException(
            status_code=401,
            detail="User account is inactive"
        )

    access_token = create_access_token(
        data={
            "sub": db_user.username,
            "role": db_user.role
        }
    )

    return {
        "access_token": access_token,
        "token_type": "bearer"
    }


# ==========================
# Current Logged-in User
# ==========================

@router.get("/me", response_model=UserOut)
def get_current_user_details(
    current_user: User = Depends(get_current_user)
):
    return current_user


# ==========================
# Self-service: password + phone number
# ==========================

@router.patch("/me/password", response_model=UserOut)
def change_my_password(
    payload: PasswordChangeRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        return user_service.change_own_password(
            db, user=current_user, current_password=payload.current_password, new_password=payload.new_password
        )
    except WrongPasswordError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.patch("/me/phone", response_model=UserOut)
def update_my_phone_number(
    payload: PhoneNumberUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return user_service.update_own_phone_number(db, user=current_user, phone_number=payload.phone_number)


# ==========================
# Forgot password (SMS OTP) -- unauthenticated by definition
# ==========================

@router.post("/forgot-password", response_model=ForgotPasswordResponse)
def forgot_password(
    payload: ForgotPasswordRequest,
    db: Session = Depends(get_db),
):
    otp_service.request_password_reset_otp(db, phone_number=payload.phone_number)
    return ForgotPasswordResponse()


@router.post("/reset-password")
def reset_password(
    payload: ResetPasswordRequest,
    db: Session = Depends(get_db),
):
    try:
        otp_service.verify_and_reset_password(
            db, phone_number=payload.phone_number, code=payload.code, new_password=payload.new_password
        )
    except InvalidOrExpiredOtpError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"message": "Password reset"}

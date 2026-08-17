from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database.database import get_db
from app.schemas.auth import UserRegister, UserLogin, Token, UserOut
from app.services.user_service import create_user, authenticate_user
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

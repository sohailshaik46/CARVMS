from sqlalchemy.orm import Session

from app.models.user import User
from app.schemas.auth import UserRegister
from app.auth.security import hash_password, verify_password


def create_user(db: Session, user: UserRegister):

    existing_user = db.query(User).filter(
        User.email == user.email
    ).first()

    if existing_user:
        return None

    new_user = User(
        username=user.username,
        email=user.email,
        password=hash_password(user.password),
        role=user.role
    )

    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    return new_user


def authenticate_user(db: Session, username: str, password: str):
    user = db.query(User).filter(
        User.username == username
    ).first()

    if not user:
        return None

    if not verify_password(password, user.password):
        return None

    return user
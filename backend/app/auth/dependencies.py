from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.database.database import get_db
from app.models.user import User
from app.auth.security import SECRET_KEY, ALGORITHM

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    credentials_exception = HTTPException(
        status_code=401,
        detail="Could not validate credentials",
    )

    try:
        payload = jwt.decode(
            token,
            SECRET_KEY,
            algorithms=[ALGORITHM],
        )

        username = payload.get("sub")

        if username is None:
            raise credentials_exception

    except JWTError:
        # Covers malformed tokens, bad signature, AND expired tokens --
        # python-jose validates the "exp" claim during decode() and raises
        # ExpiredSignatureError, a JWTError subclass.
        raise credentials_exception

    user = db.query(User).filter(
        User.username == username
    ).first()

    if user is None:
        raise credentials_exception

    if not user.is_active:
        raise HTTPException(status_code=401, detail="User account is inactive")

    return user


def require_role(*allowed_roles: str):
    """FastAPI dependency factory enforcing server-side RBAC.

    Usage: `current_user: User = Depends(require_role(roles.ADMIN))`.
    Always layers on top of get_current_user -- there is no route that can
    check a role without first being authenticated.
    """

    def _check(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=403,
                detail=f"Role '{current_user.role}' is not permitted to perform this action",
            )
        return current_user

    return _check

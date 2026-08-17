from datetime import datetime, timedelta, timezone

import bcrypt
from jose import jwt

from app.config import settings

# Single source of truth for JWT settings -- read from environment/.env via
# app.config.settings, never hardcoded. (A duplicate hardcoded copy of this
# used to live in app/auth/backend/app/auth_utils.py -- unused, deleted.)
SECRET_KEY = settings.SECRET_KEY
ALGORITHM = settings.ALGORITHM
ACCESS_TOKEN_EXPIRE_MINUTES = settings.ACCESS_TOKEN_EXPIRE_MINUTES


def hash_password(password: str) -> str:
    """Hash a plaintext password with bcrypt directly (not via passlib).

    passlib's CryptContext version-sniffs the installed bcrypt package on
    import, which breaks against modern bcrypt releases (bcrypt>=4.1 removed
    the `__about__.__version__` attribute passlib 1.7.x looks for). Calling
    bcrypt directly avoids that whole class of compatibility bug.
    """
    hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())
    return hashed.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(
        plain_password.encode("utf-8"),
        hashed_password.encode("utf-8"),
    )


def create_access_token(data: dict) -> str:
    to_encode = data.copy()

    expire = datetime.now(timezone.utc) + timedelta(
        minutes=ACCESS_TOKEN_EXPIRE_MINUTES
    )

    to_encode.update({"exp": expire})

    encoded_jwt = jwt.encode(
        to_encode,
        SECRET_KEY,
        algorithm=ALGORITHM,
    )

    return encoded_jwt

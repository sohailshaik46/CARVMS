"""Symmetric encryption for secrets we must store at rest (currently: OAuth
access/refresh tokens). Backed by Fernet, keyed off
settings.EMAIL_TOKEN_ENCRYPTION_KEY -- a key WE generate locally (see
.env.example), never one issued by an external party like Google.

Deliberately raises a clear ConfigurationError instead of crashing at import
time when the key is missing, so the rest of the app can start up fine with
email features simply reporting "not configured".
"""

from cryptography.fernet import Fernet, InvalidToken

from app.config.settings import settings


class ConfigurationError(Exception):
    """Raised when an operation needs a setting that was never configured."""


def _fernet() -> Fernet:
    # Deliberately not cached: settings.EMAIL_TOKEN_ENCRYPTION_KEY can be
    # monkeypatched per-test, and Fernet construction is cheap enough that
    # caching would only risk serving a stale key.
    key = settings.EMAIL_TOKEN_ENCRYPTION_KEY
    if not key:
        raise ConfigurationError(
            "EMAIL_TOKEN_ENCRYPTION_KEY is not set -- email features are unavailable "
            "until it is configured (see .env.example)."
        )
    try:
        return Fernet(key.encode("utf-8"))
    except (ValueError, TypeError) as exc:
        raise ConfigurationError(f"EMAIL_TOKEN_ENCRYPTION_KEY is not a valid Fernet key: {exc}") from exc


def encrypt(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt(ciphertext: str) -> str:
    try:
        return _fernet().decrypt(ciphertext.encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        raise ConfigurationError("Stored token could not be decrypted -- key may have changed.") from exc

"""Gmail OAuth 2.0 (authorization-code flow) connection service.

State-token flow, because Google's redirect back to /email/callback carries
no Authorization header of ours -- the browser hits that URL directly, with
only Google's own query params (code/state). The state token is the one
thing that survives that round trip, so it's what maps the callback back to
a specific user server-side.

The only network call anywhere in this module is exchange_code_for_tokens();
every test mocks httpx at that boundary, so no test ever reaches Google.
"""

import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional
from urllib.parse import urlencode

import httpx
from sqlalchemy.orm import Session

from app.config.settings import settings
from app.models.email_connection import EmailConnection, EmailConnectionRequest
from app.models.user import User
from app.services import crypto_service

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
# gmail.send was added alongside the decision-notification feature -- an
# account connected before that only holds gmail.readonly/openid/email and
# MUST reconnect (Google never retroactively grants a new scope to an old
# token). get_connection_status() below flags this so the UI can tell the
# difference between "not connected" and "connected but can't send yet".
GMAIL_SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "openid",
    "email",
]
GMAIL_SEND_SCOPE = "https://www.googleapis.com/auth/gmail.send"

STATE_TOKEN_TTL_MINUTES = 10
# Refresh a bit before the token actually expires so a send request never
# races a token that dies mid-flight.
TOKEN_REFRESH_SKEW_SECONDS = 60


class ConfigurationError(Exception):
    """Raised when Google OAuth env vars are not set."""


class InvalidStateError(Exception):
    """Raised when the callback's state token is missing, expired, or already used."""


class NotConnectedError(Exception):
    """Raised when there is no usable (connected, send-capable) Gmail
    connection to send notification email through."""


def is_configured() -> bool:
    return bool(settings.GOOGLE_CLIENT_ID and settings.GOOGLE_CLIENT_SECRET and settings.GOOGLE_REDIRECT_URI)


def _require_configured() -> None:
    if not is_configured():
        raise ConfigurationError(
            "Gmail OAuth is not configured -- GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET / "
            "GOOGLE_REDIRECT_URI must be set. See docs/EMAIL_SETUP.md."
        )


def build_authorization_url(db: Session, user: User) -> str:
    """Creates a pending EmailConnectionRequest tied to this user and
    returns the full Google consent-screen URL to redirect the browser to."""
    _require_configured()

    # Best-effort cleanup of this user's own stale/abandoned pending
    # requests so the table doesn't grow unbounded.
    db.query(EmailConnectionRequest).filter(EmailConnectionRequest.user_id == user.id).delete()

    state_token = secrets.token_urlsafe(32)
    request = EmailConnectionRequest(
        state_token=state_token,
        user_id=user.id,
        provider="gmail",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=STATE_TOKEN_TTL_MINUTES),
    )
    db.add(request)
    db.commit()

    params = {
        "client_id": settings.GOOGLE_CLIENT_ID,
        "redirect_uri": settings.GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": " ".join(GMAIL_SCOPES),
        "access_type": "offline",
        "prompt": "consent",
        "state": state_token,
    }
    return f"{GOOGLE_AUTH_URL}?{urlencode(params)}"


def _consume_state(db: Session, state_token: str) -> EmailConnectionRequest:
    request = (
        db.query(EmailConnectionRequest)
        .filter(EmailConnectionRequest.state_token == state_token)
        .first()
    )
    if request is None:
        raise InvalidStateError("Unknown or already-used state token")
    # SQLite doesn't actually persist tzinfo (it round-trips DateTime(timezone=True)
    # values as naive) -- the value we wrote was UTC, so treat a naive read-back as UTC
    # rather than comparing it against an aware "now" and raising TypeError.
    expires_at = request.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at < datetime.now(timezone.utc):
        db.delete(request)
        db.commit()
        raise InvalidStateError("State token expired -- please retry connecting")
    return request


def exchange_code_for_tokens(code: str) -> dict:
    """Exchanges an authorization code for tokens via Google's token
    endpoint. Raises httpx.HTTPStatusError on a non-2xx response -- callers
    let that surface as a clean error rather than swallowing it."""
    _require_configured()
    response = httpx.post(
        GOOGLE_TOKEN_URL,
        data={
            "code": code,
            "client_id": settings.GOOGLE_CLIENT_ID,
            "client_secret": settings.GOOGLE_CLIENT_SECRET,
            "redirect_uri": settings.GOOGLE_REDIRECT_URI,
            "grant_type": "authorization_code",
        },
        timeout=10.0,
    )
    response.raise_for_status()
    return response.json()


def complete_connection(db: Session, *, state_token: str, code: str) -> User:
    """Full callback handler: validates the state token, exchanges the
    code, encrypts and stores tokens, and returns the owning user."""
    request = _consume_state(db, state_token)
    user_id = request.user_id
    db.delete(request)
    db.commit()

    token_data = exchange_code_for_tokens(code)

    access_token = token_data.get("access_token")
    if not access_token:
        raise InvalidStateError("Google did not return an access token")
    refresh_token = token_data.get("refresh_token")
    expires_in = token_data.get("expires_in")
    scope = token_data.get("scope")

    expires_at = None
    if expires_in is not None:
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=int(expires_in))

    connection = db.query(EmailConnection).filter(EmailConnection.user_id == user_id).first()
    if connection is None:
        connection = EmailConnection(user_id=user_id, provider="gmail")
        db.add(connection)

    connection.encrypted_access_token = crypto_service.encrypt(access_token)
    if refresh_token:
        # Google only sends refresh_token on first consent (or when a
        # re-consent is forced, which prompt=consent above always does) --
        # never blank out a previously-stored one with a missing value.
        connection.encrypted_refresh_token = crypto_service.encrypt(refresh_token)
    connection.token_expires_at = expires_at
    connection.scope = scope
    connection.status = "connected"
    connection.revoked_at = None

    db.commit()
    db.refresh(connection)

    return connection.user


def _has_send_scope(connection: EmailConnection) -> bool:
    return bool(connection.scope) and GMAIL_SEND_SCOPE in connection.scope.split()


def get_connection_status(db: Session, user: User) -> dict:
    connection = db.query(EmailConnection).filter(EmailConnection.user_id == user.id).first()
    if connection is None or connection.status != "connected":
        return {"connected": False, "provider": None, "scope": None, "connected_at": None, "can_send": False}
    return {
        "connected": True,
        "provider": connection.provider,
        "scope": connection.scope,
        "connected_at": connection.connected_at,
        # False for a connection made before gmail.send was requested --
        # the UI should prompt that user to reconnect, not just show green.
        "can_send": _has_send_scope(connection),
    }


def refresh_access_token(refresh_token: str) -> dict:
    """Exchanges a refresh token for a new access token. Raises
    httpx.HTTPStatusError on a non-2xx response, same convention as
    exchange_code_for_tokens."""
    _require_configured()
    response = httpx.post(
        GOOGLE_TOKEN_URL,
        data={
            "refresh_token": refresh_token,
            "client_id": settings.GOOGLE_CLIENT_ID,
            "client_secret": settings.GOOGLE_CLIENT_SECRET,
            "grant_type": "refresh_token",
        },
        timeout=10.0,
    )
    response.raise_for_status()
    return response.json()


def get_any_send_capable_connection(db: Session) -> Optional[EmailConnection]:
    """The notification feature sends from whichever registered mailbox
    Vigilance has connected -- there's no per-reviewer mailbox, just the
    one shared "registered email ID" the user described. Picks the most
    recently connected send-capable connection if more than one exists."""
    candidates = (
        db.query(EmailConnection)
        .filter(EmailConnection.status == "connected")
        .order_by(EmailConnection.connected_at.desc())
        .all()
    )
    for connection in candidates:
        if _has_send_scope(connection):
            return connection
    return None


def get_valid_access_token(db: Session, connection: EmailConnection) -> str:
    """Returns a usable access token for this connection, transparently
    refreshing it first if it's expired (or about to expire)."""
    expires_at = connection.token_expires_at
    needs_refresh = expires_at is None
    if expires_at is not None:
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        needs_refresh = expires_at < datetime.now(timezone.utc) + timedelta(seconds=TOKEN_REFRESH_SKEW_SECONDS)

    if needs_refresh:
        if not connection.encrypted_refresh_token:
            raise NotConnectedError(
                "Gmail access token has expired and no refresh token is on file -- reconnect Gmail in Settings."
            )
        refresh_token = crypto_service.decrypt(connection.encrypted_refresh_token)
        token_data = refresh_access_token(refresh_token)
        access_token = token_data.get("access_token")
        if not access_token:
            raise NotConnectedError("Google did not return a new access token on refresh -- reconnect Gmail in Settings.")
        connection.encrypted_access_token = crypto_service.encrypt(access_token)
        expires_in = token_data.get("expires_in")
        connection.token_expires_at = (
            datetime.now(timezone.utc) + timedelta(seconds=int(expires_in)) if expires_in is not None else None
        )
        db.commit()
        db.refresh(connection)

    if not connection.encrypted_access_token:
        raise NotConnectedError("No Gmail access token on file -- reconnect Gmail in Settings.")
    return crypto_service.decrypt(connection.encrypted_access_token)


def get_notification_access_token(db: Session) -> str:
    """Convenience wrapper for the notification feature: finds the shared
    send-capable connection and returns a valid access token for it, or
    raises NotConnectedError with a message safe to surface to the user."""
    connection = get_any_send_capable_connection(db)
    if connection is None:
        raise NotConnectedError(
            "No Gmail account is connected with permission to send email -- connect (or reconnect) Gmail in "
            "Settings and grant the send permission."
        )
    return get_valid_access_token(db, connection)


def disconnect(db: Session, user: User) -> None:
    connection = db.query(EmailConnection).filter(EmailConnection.user_id == user.id).first()
    if connection is None:
        return
    connection.status = "revoked"
    connection.revoked_at = datetime.now(timezone.utc)
    # Actively clear stored credentials on revoke -- a revoked connection
    # should not leave a still-usable token sitting in the database.
    connection.encrypted_access_token = None
    connection.encrypted_refresh_token = None
    db.commit()

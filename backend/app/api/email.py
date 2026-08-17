from typing import Optional
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.config.settings import settings
from app.database.database import get_db
from app.models.user import User
from app.schemas.email_connection import (
    EmailConnectAuthorizationOut,
    EmailConnectionStatusOut,
    EmailProviderInfo,
)
from app.services import email_connection_service
from app.services.email_connection_service import ConfigurationError, InvalidStateError

router = APIRouter(prefix="/email", tags=["Email Integration"])


def _settings_redirect(**params) -> RedirectResponse:
    return RedirectResponse(url=f"{settings.FRONTEND_URL}/settings?{urlencode(params)}")


@router.get("/providers", response_model=list[EmailProviderInfo])
def list_providers(_user: User = Depends(get_current_user)):
    return [EmailProviderInfo(provider="gmail", configured=email_connection_service.is_configured())]


@router.get("/connect", response_model=EmailConnectAuthorizationOut)
def connect(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Returns the Google consent-screen URL for the frontend to redirect
    the browser to. Does not redirect itself (this is an API call, not the
    browser navigation) so the frontend can decide how to send the user."""
    try:
        url = email_connection_service.build_authorization_url(db, user)
    except ConfigurationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return EmailConnectAuthorizationOut(authorization_url=url)


@router.get("/callback", include_in_schema=False)
def callback(
    code: Optional[str] = Query(default=None),
    state: Optional[str] = Query(default=None),
    error: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
):
    """Google redirects the user's browser here directly -- no Authorization
    header of ours is present, which is exactly why this endpoint has no
    get_current_user dependency and instead trusts only the state token
    minted by /email/connect. Always ends in a redirect back to the
    frontend, success or failure, since a browser landed here directly."""
    if error:
        return _settings_redirect(email_error=error)
    if not code or not state:
        return _settings_redirect(email_error="missing_code_or_state")

    try:
        email_connection_service.complete_connection(db, state_token=state, code=code)
    except InvalidStateError as exc:
        return _settings_redirect(email_error=str(exc))
    except ConfigurationError as exc:
        return _settings_redirect(email_error=str(exc))
    except httpx.HTTPStatusError:
        return _settings_redirect(email_error="google_token_exchange_failed")

    return _settings_redirect(email_connected="1")


@router.get("/status", response_model=EmailConnectionStatusOut)
def status(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return email_connection_service.get_connection_status(db, user)


@router.post("/disconnect", status_code=204)
def disconnect(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    email_connection_service.disconnect(db, user)

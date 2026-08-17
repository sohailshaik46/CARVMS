from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class EmailProviderInfo(BaseModel):
    provider: str
    configured: bool


class EmailConnectAuthorizationOut(BaseModel):
    authorization_url: str


class EmailConnectionStatusOut(BaseModel):
    connected: bool
    provider: Optional[str]
    scope: Optional[str]
    connected_at: Optional[datetime]
    # False for a connection made before gmail.send was requested (or one
    # that never re-consented to it) -- the UI should prompt a reconnect
    # rather than imply decision-notification email will actually work.
    can_send: bool = False

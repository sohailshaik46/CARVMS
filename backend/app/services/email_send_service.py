"""Sends outbound notification email through Gmail's REST API.

This is deliberately a thin, single-purpose module: build an RFC 2822
message, base64url-encode it, POST it to Gmail's users.messages.send
endpoint with the caller's access token. It knows nothing about Delayed
Cash Billing / Weekly Revenue Closure -- that's delayed_cash_notification_
service's job. Every network call happens here, at one boundary, so tests
mock httpx here and never reach Google -- same convention as
email_connection_service.

Token acquisition (including refresh) is email_connection_service's job;
this module always receives an already-valid access token.
"""

import base64
from email.mime.text import MIMEText

import httpx

GMAIL_SEND_URL = "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"


class EmailSendError(Exception):
    """Raised when Gmail's API rejects the send (bad token, invalid
    recipient, quota, etc). Wraps the underlying httpx error's message so
    callers can surface something readable without leaking response guts."""


def send_email(*, access_token: str, sender: str, to: str, subject: str, body_text: str) -> None:
    message = MIMEText(body_text)
    message["to"] = to
    message["from"] = sender
    message["subject"] = subject
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode("ascii")

    try:
        response = httpx.post(
            GMAIL_SEND_URL,
            headers={"Authorization": f"Bearer {access_token}"},
            json={"raw": raw},
            timeout=10.0,
        )
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise EmailSendError(f"Gmail rejected the send ({exc.response.status_code}): {exc.response.text}") from exc
    except httpx.HTTPError as exc:
        raise EmailSendError(f"Could not reach Gmail: {exc}") from exc

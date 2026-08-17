"""Pluggable SMS sending -- deliberately provider-agnostic (per an explicit
choice: "build the generic interface now, pick a provider later"). Nothing
in this module ever talks to a real SMS gateway; NullSmsProvider is the only
implementation until a real one (Twilio, MSG91, etc.) is wired in.

To add a real provider later: implement `SmsProvider` (one method, `send`),
wire it up in `get_sms_provider()` below gated on its own env vars (mirror
how email_connection_service checks GOOGLE_CLIENT_ID), and nothing else in
this codebase needs to change -- otp_service and the escalation-alert path
both call `get_sms_provider().send(...)`, never a concrete provider class.
See docs/SMS_SETUP.md.
"""

from abc import ABC, abstractmethod


class SmsSendError(Exception):
    """Raised when a configured provider's actual API call fails (bad
    number, provider outage, etc.) -- distinct from NotConfiguredError,
    which means no provider is wired in at all."""


class NotConfiguredError(Exception):
    """Raised by NullSmsProvider -- no real SMS provider is configured yet."""


class SmsProvider(ABC):
    @abstractmethod
    def send(self, phone_number: str, message: str) -> None:
        """Send `message` to `phone_number` (E.164, e.g. +919876543210).
        Raises SmsSendError on failure. Never returns a value -- success is
        "didn't raise"."""


class NullSmsProvider(SmsProvider):
    """The only provider until a real one is configured. Raises rather
    than silently pretending to send -- callers (otp_service, escalation
    alerts) are expected to catch NotConfiguredError and degrade
    gracefully (e.g. still let a password-reset request succeed generically
    without leaking whether it actually went anywhere)."""

    def send(self, phone_number: str, message: str) -> None:
        raise NotConfiguredError(
            "No SMS provider is configured -- see docs/SMS_SETUP.md to wire one in."
        )


def get_sms_provider() -> SmsProvider:
    # Add real-provider branches here once credentials exist, e.g.:
    #   if settings.MSG91_API_KEY:
    #       return Msg91SmsProvider(api_key=settings.MSG91_API_KEY, sender_id=settings.MSG91_SENDER_ID)
    #   if settings.TWILIO_ACCOUNT_SID:
    #       return TwilioSmsProvider(...)
    return NullSmsProvider()


def is_configured() -> bool:
    return not isinstance(get_sms_provider(), NullSmsProvider)

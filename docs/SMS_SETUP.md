# SMS (OTP + Escalation Alerts) Setup

CARVMS has two things that want to send an SMS:

1. **Forgot-password OTP** -- `POST /auth/forgot-password` (phone number
   in) -> `POST /auth/reset-password` (phone number + code + new password
   in). Every user account has its own `phone_number` (asked for at
   registration, editable per-user in **Settings -> Security**, and
   editable for any user by an Admin in **Users**) -- an OTP always goes to
   that specific account's own number, never a shared one.
2. **48-hour response-window escalation** -- when a DCB/WRC case's
   response deadline passes with no response, an alert SMS to Admins who
   have opted in. See "What's NOT automatic yet" below -- this exists as a
   callable check, not a running background job.

**Right now, neither actually sends anything.** `app/services/sms_provider.py`
defines the interface (`SmsProvider.send(phone_number, message)`) and the
only implementation is `NullSmsProvider`, which always raises
"not configured". Both features already call through this interface
end-to-end (OTP codes are generated and stored, escalation checks already
identify who to alert) -- the only missing piece is a real provider
underneath it, which needs an account you set up yourself (CARVMS can't
create one on your behalf).

## 1. Pick a provider and get credentials

Any provider that can send a plain SMS by API call works. Two common
choices for Indian phone numbers:

- **MSG91** (msg91.com) -- India-focused, INR billing. You'll get an API
  key and register a sender ID (a 6-character alphanumeric tag shown as the
  sender, e.g. `CARVMS`).
- **Twilio** (twilio.com) -- global, works everywhere, needs a Twilio
  phone number and per-country sender registration for India.

Either way, you sign up and get credentials yourself -- paste them only
into `backend/.env`, never into chat, a ticket, or a commit.

## 2. Implement one class

In `app/services/sms_provider.py`, add a class implementing `SmsProvider`,
e.g. for MSG91:

```python
import httpx
from app.config.settings import settings

class Msg91SmsProvider(SmsProvider):
    def send(self, phone_number: str, message: str) -> None:
        resp = httpx.post(
            "https://control.msg91.com/api/v5/flow/",
            headers={"authkey": settings.MSG91_API_KEY},
            json={
                "sender": settings.MSG91_SENDER_ID,
                "mobiles": phone_number.lstrip("+"),
                "message": message,
            },
            timeout=10,
        )
        if resp.status_code >= 400:
            raise SmsSendError(f"MSG91 returned {resp.status_code}: {resp.text}")
```

(Adjust to whatever that provider's actual API shape is at the time --
the snippet above is illustrative, not a guarantee of MSG91's current
endpoint.)

## 3. Add the env vars and wire the factory

In `app/config/settings.py`, add (matching the `Optional[str] = None`
pattern already used for `GOOGLE_CLIENT_ID` etc.):

```python
MSG91_API_KEY: Optional[str] = None
MSG91_SENDER_ID: Optional[str] = None
```

In `app/services/sms_provider.py`'s `get_sms_provider()`:

```python
def get_sms_provider() -> SmsProvider:
    if settings.MSG91_API_KEY:
        return Msg91SmsProvider()
    return NullSmsProvider()
```

Put the real values in `backend/.env`:

```
MSG91_API_KEY=<your key>
MSG91_SENDER_ID=<your sender ID>
```

## 4. Restart the backend and verify

```bash
cd backend
./venv/Scripts/python.exe -m uvicorn main:app --reload
```

Trigger `POST /auth/forgot-password` with a registered phone number and
confirm the SMS actually arrives. `otp_service.request_password_reset_otp`
already swallows `NotConfiguredError`/`SmsSendError` on purpose (so a
misconfigured provider never blocks the generic "if registered, a code
was sent" response) -- if nothing arrives, check the backend log for the
underlying exception rather than assuming the endpoint call itself failed.

## What's NOT automatic yet

There is no scheduler/cron in this app today. The 48-hour escalation SMS
is a **callable check** (an admin action, not a background job that fires
by itself the instant a deadline passes) -- see `app/services/escalation_alert_service.py`
and its `POST /admin/escalations/check` endpoint. Until an external
scheduler (Windows Task Scheduler, a cron job, etc.) is set up to hit that
endpoint periodically, or a real in-app scheduler is added, someone has to
either trigger it manually or you need to tell me to build one.

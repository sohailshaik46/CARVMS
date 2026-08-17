"""Phone-OTP password reset -- the "forgot password" path for a user who
doesn't know their current password (so Settings' self-service password
change, which requires it, doesn't apply). Unauthenticated by definition:
the caller only proves who they are by receiving a code on the phone number
already on file for that account.

Deliberately never reveals whether a given phone number belongs to an
account -- both "request a code" and "verify a code" return the same
generic response whether or not a matching, phone-having user exists,
exactly like this app's login error already doesn't distinguish "wrong
username" from "wrong password".
"""

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.auth.security import hash_password
from app.models.otp import OtpCode, PURPOSE_PASSWORD_RESET
from app.models.user import User
from app.services import audit_log_service
from app.services.sms_provider import NotConfiguredError, SmsSendError, get_sms_provider

OTP_LENGTH = 6
OTP_TTL_MINUTES = 10
MAX_VERIFY_ATTEMPTS = 5


class InvalidOrExpiredOtpError(Exception):
    pass


def _hash_code(code: str) -> str:
    # Not a password -- a 6-digit code valid for 10 minutes doesn't need
    # bcrypt's cost factor, just something that isn't reversible/plaintext
    # in the DB. sha256 is fine for this threat model.
    return hashlib.sha256(code.encode()).hexdigest()


def _generate_code() -> str:
    return f"{secrets.randbelow(10 ** OTP_LENGTH):0{OTP_LENGTH}d}"


def request_password_reset_otp(db: Session, *, phone_number: str) -> None:
    """Looks up the user by phone_number and, if found, sends a code. Never
    raises for "no such number" or "no SMS provider configured" -- both are
    swallowed so the caller (the API layer) always returns the same generic
    "if that number is registered, a code was sent" response. A genuine SMS
    provider failure (SmsSendError, i.e. the provider IS configured but the
    send itself failed) also doesn't propagate, for the same reason -- the
    difference between "not configured" and "send failed" is an operator
    concern, not something to leak to whoever is requesting a reset."""
    user = db.query(User).filter(User.phone_number == phone_number).first()
    if user is None:
        return

    code = _generate_code()
    otp = OtpCode(
        user_id=user.id,
        purpose=PURPOSE_PASSWORD_RESET,
        code_hash=_hash_code(code),
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=OTP_TTL_MINUTES),
    )
    db.add(otp)
    db.commit()

    try:
        get_sms_provider().send(
            phone_number,
            f"Your Billing Data Validation password reset code is {code}. It expires in {OTP_TTL_MINUTES} minutes.",
        )
    except (NotConfiguredError, SmsSendError):
        # The code row still exists (harmless -- it just expires unused),
        # but nothing was actually delivered. Not this function's problem
        # to surface; see the docstring.
        pass


def verify_and_reset_password(db: Session, *, phone_number: str, code: str, new_password: str) -> None:
    """Raises InvalidOrExpiredOtpError for every failure mode (wrong code,
    expired, already used, too many attempts, unknown number) -- same
    generic message regardless of which, so a caller can't use error text
    to enumerate registered phone numbers or narrow down a code by trial."""
    user = db.query(User).filter(User.phone_number == phone_number).first()
    if user is None:
        raise InvalidOrExpiredOtpError("Invalid or expired code")

    otp = _latest_valid_otp(db, user_id=user.id)
    if otp is None:
        raise InvalidOrExpiredOtpError("Invalid or expired code")

    if otp.attempt_count >= MAX_VERIFY_ATTEMPTS:
        raise InvalidOrExpiredOtpError("Invalid or expired code")

    if otp.code_hash != _hash_code(code):
        otp.attempt_count += 1
        db.commit()
        raise InvalidOrExpiredOtpError("Invalid or expired code")

    otp.consumed_at = datetime.now(timezone.utc)
    user.password_hash = hash_password(new_password)
    db.flush()

    audit_log_service.record(
        db,
        actor=user,
        action="user.password_reset_via_otp",
        entity_type="User",
        entity_id=user.id,
        before=None,
        after=None,
    )
    db.commit()


def _latest_valid_otp(db: Session, *, user_id: int) -> Optional[OtpCode]:
    now = datetime.now(timezone.utc)
    return (
        db.query(OtpCode)
        .filter(
            OtpCode.user_id == user_id,
            OtpCode.purpose == PURPOSE_PASSWORD_RESET,
            OtpCode.consumed_at.is_(None),
            OtpCode.expires_at > now,
        )
        .order_by(OtpCode.id.desc())
        .first()
    )

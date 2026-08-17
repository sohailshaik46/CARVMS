from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, func

from app.database.database import Base

# What an OTP is FOR -- keeps password-reset codes from being replayable
# against some other future OTP-gated action just because they share a
# phone number and are still "valid".
PURPOSE_PASSWORD_RESET = "password_reset"


class OtpCode(Base):
    """A one-time code sent to a user's own phone_number (never email --
    this is specifically the SMS channel). Stores a hash of the code, never
    the code itself, same principle as password_hash on User. One row per
    request; requesting again while a prior code is still valid does not
    reuse or extend it -- it simply becomes a second valid code until either
    is consumed or both expire, which is deliberately simple rather than
    trying to invalidate the previous one under a race."""

    __tablename__ = "otp_codes"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    purpose = Column(String, nullable=False, default=PURPOSE_PASSWORD_RESET)
    code_hash = Column(String, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    consumed_at = Column(DateTime(timezone=True), nullable=True)
    # Failed verification attempts against THIS code -- capped in
    # otp_service to stop brute-forcing a 6-digit code before it expires.
    attempt_count = Column(Integer, nullable=False, default=0, server_default="0")

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

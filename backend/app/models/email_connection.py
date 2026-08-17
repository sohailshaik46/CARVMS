from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import relationship

from app.database.database import Base

EMAIL_PROVIDERS = ("gmail",)
EMAIL_CONNECTION_STATUSES = ("connected", "revoked")


def _sql_in_clause(values: tuple[str, ...]) -> str:
    """Renders a SQL IN (...) list from a tuple of strings. Plain
    f"{values}" (used elsewhere for tuples with 2+ items) breaks for a
    single-item tuple -- Python's repr of ("gmail",) is "('gmail',)", and
    that trailing comma before the close-paren is a SQLite syntax error."""
    return "(" + ", ".join(f"'{v}'" for v in values) + ")"


class EmailConnectionRequest(Base):
    """A pending OAuth handshake -- exists only between 'Connect Email' and
    Google's redirect back to /email/callback (a few minutes, at most).
    This is what lets the callback (which Google calls without our JWT)
    know which user initiated the request: the state token is the only
    thing carried through Google's redirect, so it has to map back to a
    user server-side. Deleted once consumed or expired -- never accumulates.
    """

    __tablename__ = "email_connection_requests"

    id = Column(Integer, primary_key=True, index=True)
    state_token = Column(String, unique=True, nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    provider = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    expires_at = Column(DateTime(timezone=True), nullable=False)

    user = relationship("User")


class EmailConnection(Base):
    """One user's OAuth grant for one provider. Tokens are stored
    Fernet-encrypted (see app/services/crypto_service.py) -- never in
    plaintext, and never returned by any API response; GET /email/status
    reports only connected/provider/scope/timestamps.
    """

    __tablename__ = "email_connections"
    __table_args__ = (
        CheckConstraint(
            f"provider IN {_sql_in_clause(EMAIL_PROVIDERS)}", name="ck_email_connections_provider_valid"
        ),
        CheckConstraint(
            f"status IN {_sql_in_clause(EMAIL_CONNECTION_STATUSES)}", name="ck_email_connections_status_valid"
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False, index=True)
    provider = Column(String, nullable=False)

    # Nullable because disconnect() actively clears both tokens rather than
    # leaving a live, usable credential sitting in the DB after revocation.
    encrypted_access_token = Column(String, nullable=True)
    encrypted_refresh_token = Column(String, nullable=True)
    token_expires_at = Column(DateTime(timezone=True), nullable=True)
    scope = Column(String, nullable=True)

    status = Column(String, nullable=False, default="connected")
    connected_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    revoked_at = Column(DateTime(timezone=True), nullable=True)

    user = relationship("User")

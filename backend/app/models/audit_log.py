from sqlalchemy import JSON, Column, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import relationship

from app.database.database import Base


class AuditLog(Base):
    """Immutable record of every mutating action taken in the system.

    No router in this codebase may expose an UPDATE or DELETE against this
    table -- write-once, read-many. This is the governance/traceability
    mechanism required by the product brief (who did what, when, before/after).
    """

    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)

    actor_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    actor = relationship("User")

    action = Column(String, nullable=False, index=True)          # e.g. "user.role_changed"
    entity_type = Column(String, nullable=False, index=True)      # e.g. "User"
    entity_id = Column(String, nullable=False, index=True)

    before_json = Column(JSON, nullable=True)
    after_json = Column(JSON, nullable=True)

    correlation_id = Column(String, nullable=True, index=True)

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

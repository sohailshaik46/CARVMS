from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog
from app.models.user import User


def record(
    db: Session,
    *,
    actor: Optional[User],
    action: str,
    entity_type: str,
    entity_id: Any,
    before: Optional[dict] = None,
    after: Optional[dict] = None,
    correlation_id: Optional[str] = None,
) -> AuditLog:
    """Append an immutable audit log entry. Never call db.commit() for the
    caller -- callers commit their own transaction (the log entry is added
    to the same session/transaction as the business change it records, so
    a failed business change never leaves an orphaned log entry)."""
    entry = AuditLog(
        actor_id=actor.id if actor else None,
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id),
        before_json=before,
        after_json=after,
        correlation_id=correlation_id,
    )
    db.add(entry)
    db.flush()
    return entry

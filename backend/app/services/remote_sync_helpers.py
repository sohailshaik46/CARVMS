"""Small, shared building blocks for the manual local<->Render sync
services (org_master_remote_sync_service, delayed_cash_remote_sync_service,
weekly_revenue_remote_sync_service). Nothing here opens a connection or
runs on its own -- see org_master_remote_sync_service's module docstring
for the full safety contract (never automatic, preview-first, never
deletes) that every one of these services follows.
"""

from typing import Optional

from sqlalchemy.orm import Session

from app.models.user import User


def resolve_user_id(
    source_user_id: Optional[int], source_db: Session, target_db: Session, fallback_target_user_id: int
) -> int:
    """A batch/bill/decision's uploaded_by/reviewed_by/etc. references a
    User row -- but the two databases have completely independent User
    tables (different accounts, different ids, possibly no matching
    account at all). Resolves by USERNAME (the one thing that could
    plausibly be the same person on both sides); if the source user
    doesn't exist locally either, or has no username match on the target,
    falls back to whichever admin is actually running this sync -- never
    fabricates a User row, never leaves a NOT NULL FK unset."""
    if source_user_id is not None:
        source_user = source_db.get(User, source_user_id)
        if source_user is not None:
            target_user = target_db.query(User).filter(User.username == source_user.username).first()
            if target_user is not None:
                return target_user.id
    return fallback_target_user_id


def resolve_user_id_nullable(
    source_user_id: Optional[int], source_db: Session, target_db: Session
) -> Optional[int]:
    """Same username-matching as resolve_user_id, but for a NULLABLE FK
    (e.g. reviewed_by_id before anyone has reviewed something yet) --
    returns None rather than substituting the syncing admin when there's
    no source value or no match, since a nullable field is allowed to
    just stay unset."""
    if source_user_id is None:
        return None
    source_user = source_db.get(User, source_user_id)
    if source_user is None:
        return None
    target_user = target_db.query(User).filter(User.username == source_user.username).first()
    return target_user.id if target_user else None


def resolve_current_admin_target_id(current_user: User, target_db: Session) -> int:
    """The fallback attribution target for resolve_user_id -- whichever
    User is actually running this sync, resolved on the TARGET side by
    username. Falls back to any Admin on the target if the current admin
    genuinely has no account there yet (e.g. first time syncing from a
    brand new local machine)."""
    target_match = target_db.query(User).filter(User.username == current_user.username).first()
    if target_match is not None:
        return target_match.id
    any_admin = target_db.query(User).filter(User.role == "Admin").first()
    if any_admin is not None:
        return any_admin.id
    raise RuntimeError(
        "No Admin user exists on the target database to attribute this sync to -- refusing to proceed."
    )


def merge_field(target, field_name: str, source_value, *, only_fill_if_empty: bool = False, rank_order=None) -> bool:
    """Copies source_value onto target.field_name under one of three
    rules, and returns whether anything actually changed:

      - only_fill_if_empty=True: ONLY sets the field if target's current
        value is None AND source_value is not None. If target already
        has ANY value, it is left completely alone, even if source's
        value differs -- this is what protects a response_token already
        emailed to a real center manager, or a review decision someone
        already made, from ever being silently overwritten or replaced
        by a different value from the other side.

      - rank_order given (a tuple naming valid states worst-to-best, e.g.
        DCB_BATCH_STATUSES): only moves target FORWARD along that order,
        never backward -- so a batch already closed on one side can't be
        regressed to "open" by a sync from a side that simply hasn't
        caught up yet. A value not found in rank_order is treated as
        rank -1 (behind everything).

      - neither flag: plain "set if different" -- for fields with no
        real conflict/ordering risk (names, computed totals, etc.)."""
    current = getattr(target, field_name)

    if only_fill_if_empty:
        if current is not None or source_value is None:
            return False
        setattr(target, field_name, source_value)
        return True

    if source_value == current:
        return False

    if rank_order is not None:
        current_rank = rank_order.index(current) if current in rank_order else -1
        source_rank = rank_order.index(source_value) if source_value in rank_order else -1
        if source_rank < current_rank:
            return False

    setattr(target, field_name, source_value)
    return True

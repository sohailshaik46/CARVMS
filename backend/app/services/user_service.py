from typing import Optional

from sqlalchemy.orm import Session

from app.auth.roles import DEFAULT_SELF_REGISTER_ROLE
from app.models.org import OrgNode
from app.models.user import User
from app.schemas.auth import UserRegister
from app.auth.security import hash_password, verify_password
from app.services import audit_log_service


class SelfActionError(Exception):
    """Raised when an admin attempts a role/activation change on their own
    account -- always rejected server-side, never just hidden in the UI."""


class OrgNodeNotFoundError(Exception):
    pass


class WrongPasswordError(Exception):
    """Current password didn't match -- self-service change refuses to
    proceed. Message is deliberately generic (no hint about *why* it's
    wrong) to avoid leaking anything about the stored hash."""


def _user_snapshot(user: User) -> dict:
    return {"role": user.role, "is_active": user.is_active, "org_node_id": user.org_node_id}


def create_user(db: Session, user: UserRegister) -> User | None:
    existing_user = db.query(User).filter(
        (User.email == user.email) | (User.username == user.username)
    ).first()

    if existing_user:
        return None

    new_user = User(
        username=user.username,
        email=user.email,
        password_hash=hash_password(user.password),
        phone_number=user.phone_number,
        role=DEFAULT_SELF_REGISTER_ROLE,  # never trust a client-supplied role
    )

    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    return new_user


def authenticate_user(db: Session, username: str, password: str) -> User | None:
    user = db.query(User).filter(
        User.username == username
    ).first()

    if not user:
        return None

    if not verify_password(password, user.password_hash):
        return None

    return user


def list_users(db: Session, skip: int = 0, limit: int = 50) -> list[User]:
    limit = max(1, min(limit, 200))
    return (
        db.query(User)
        .order_by(User.id)
        .offset(max(0, skip))
        .limit(limit)
        .all()
    )


def get_user_by_id(db: Session, user_id: int) -> Optional[User]:
    return db.query(User).filter(User.id == user_id).first()


def update_user_role(db: Session, *, target: User, new_role: str, actor: User) -> User:
    """Change a user's role. Never callable by the target on themselves --
    self-promotion is rejected regardless of the actor's current role."""
    if target.id == actor.id:
        raise SelfActionError("Admins cannot change their own role")

    before = _user_snapshot(target)
    target.role = new_role
    db.flush()

    audit_log_service.record(
        db,
        actor=actor,
        action="user.role_changed",
        entity_type="User",
        entity_id=target.id,
        before=before,
        after=_user_snapshot(target),
    )
    db.commit()
    db.refresh(target)
    return target


def assign_org_node(db: Session, *, target: User, org_node_id: Optional[int], actor: User) -> User:
    """Anchors (or unanchors, if org_node_id is None) a user to an org node --
    this is how a Center/Cluster/Zonal Manager's identity and email
    (always just their User.email, never re-typed) stay current as people
    change over time. This is the ongoing-maintenance path the org
    hierarchy admin page is expected to use, not a one-off upload field."""
    if org_node_id is not None and not db.query(OrgNode).filter(OrgNode.id == org_node_id).first():
        raise OrgNodeNotFoundError(f"Org node {org_node_id} does not exist")

    before = _user_snapshot(target)
    target.org_node_id = org_node_id
    db.flush()

    audit_log_service.record(
        db,
        actor=actor,
        action="user.org_node_assigned",
        entity_type="User",
        entity_id=target.id,
        before=before,
        after=_user_snapshot(target),
    )
    db.commit()
    db.refresh(target)
    return target


def change_own_password(db: Session, *, user: User, current_password: str, new_password: str) -> User:
    """Self-service only -- requires the CURRENT password, unlike an
    admin-driven reset. Logged without either password value, obviously."""
    if not verify_password(current_password, user.password_hash):
        raise WrongPasswordError("Current password is incorrect")

    user.password_hash = hash_password(new_password)
    db.flush()

    audit_log_service.record(
        db,
        actor=user,
        action="user.password_changed",
        entity_type="User",
        entity_id=user.id,
        before=None,
        after=None,
    )
    db.commit()
    db.refresh(user)
    return user


def update_own_phone_number(db: Session, *, user: User, phone_number: str) -> User:
    before = {"phone_number": user.phone_number}
    user.phone_number = phone_number
    db.flush()

    audit_log_service.record(
        db,
        actor=user,
        action="user.phone_number_changed",
        entity_type="User",
        entity_id=user.id,
        before=before,
        after={"phone_number": phone_number},
    )
    db.commit()
    db.refresh(user)
    return user


def update_user_phone_number(db: Session, *, target: User, phone_number: str, actor: User) -> User:
    """Admin-driven -- sets or fixes another user's number (e.g. onboarding
    a new account, or correcting a typo the user can't self-serve because
    they're locked out)."""
    before = {"phone_number": target.phone_number}
    target.phone_number = phone_number
    db.flush()

    audit_log_service.record(
        db,
        actor=actor,
        action="user.phone_number_changed",
        entity_type="User",
        entity_id=target.id,
        before=before,
        after={"phone_number": phone_number},
    )
    db.commit()
    db.refresh(target)
    return target


def set_user_active(db: Session, *, target: User, is_active: bool, actor: User) -> User:
    """Activate/deactivate a user. An admin cannot deactivate their own
    account through this endpoint -- prevents an accidental self-lockout."""
    if target.id == actor.id:
        raise SelfActionError("Admins cannot change their own active status")

    before = _user_snapshot(target)
    target.is_active = is_active
    db.flush()

    audit_log_service.record(
        db,
        actor=actor,
        action="user.activation_changed",
        entity_type="User",
        entity_id=target.id,
        before=before,
        after=_user_snapshot(target),
    )
    db.commit()
    db.refresh(target)
    return target

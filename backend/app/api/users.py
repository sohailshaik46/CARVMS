from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.auth import roles
from app.auth.dependencies import require_role
from app.database.database import get_db
from app.models.user import User
from app.schemas.user import ActiveUpdateRequest, OrgNodeAssignRequest, RoleUpdateRequest, UserAdminOut
from app.services import user_service
from app.services.user_service import OrgNodeNotFoundError, SelfActionError

router = APIRouter(
    prefix="/users",
    tags=["User Management"],
)


def _get_target_or_404(db: Session, user_id: int) -> User:
    user = user_service.get_user_by_id(db, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.get("", response_model=list[UserAdminOut])
def list_users(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    _admin: User = Depends(require_role(roles.ADMIN)),
):
    return user_service.list_users(db, skip=skip, limit=limit)


@router.get("/{user_id}", response_model=UserAdminOut)
def get_user(
    user_id: int,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_role(roles.ADMIN)),
):
    return _get_target_or_404(db, user_id)


@router.patch("/{user_id}/role", response_model=UserAdminOut)
def update_role(
    user_id: int,
    payload: RoleUpdateRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(require_role(roles.ADMIN)),
):
    target = _get_target_or_404(db, user_id)
    try:
        return user_service.update_user_role(
            db, target=target, new_role=payload.role, actor=admin
        )
    except SelfActionError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.patch("/{user_id}/active", response_model=UserAdminOut)
def update_active(
    user_id: int,
    payload: ActiveUpdateRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(require_role(roles.ADMIN)),
):
    target = _get_target_or_404(db, user_id)
    try:
        return user_service.set_user_active(
            db, target=target, is_active=payload.is_active, actor=admin
        )
    except SelfActionError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.patch("/{user_id}/org-node", response_model=UserAdminOut)
def update_org_node(
    user_id: int,
    payload: OrgNodeAssignRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(require_role(roles.ADMIN)),
):
    target = _get_target_or_404(db, user_id)
    try:
        return user_service.assign_org_node(
            db, target=target, org_node_id=payload.org_node_id, actor=admin
        )
    except OrgNodeNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

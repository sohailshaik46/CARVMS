from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.database.database import get_db
from app.models.user import User
from app.schemas.dashboard_layout import DashboardLayoutCreate, DashboardLayoutOut, DashboardLayoutUpdate
from app.services import dashboard_layout_service

router = APIRouter(prefix="/dashboard-layouts", tags=["Dashboard Layouts"])


@router.post("", response_model=DashboardLayoutOut, status_code=201)
def create_layout(
    payload: DashboardLayoutCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return dashboard_layout_service.create_layout(
        db,
        name=payload.name,
        description=payload.description,
        config=payload.config.model_dump(),
        is_shared=payload.is_shared,
        owner=user,
    )


@router.get("", response_model=list[DashboardLayoutOut])
def list_layouts(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return dashboard_layout_service.list_visible_layouts(db, user)


@router.get("/{layout_id}", response_model=DashboardLayoutOut)
def get_layout(
    layout_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    layout = dashboard_layout_service.get_visible_layout(db, user, layout_id)
    if layout is None:
        raise HTTPException(status_code=404, detail="Dashboard layout not found")
    return layout


@router.patch("/{layout_id}", response_model=DashboardLayoutOut)
def update_layout(
    layout_id: int,
    payload: DashboardLayoutUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    layout = dashboard_layout_service.get_visible_layout(db, user, layout_id)
    if layout is None:
        raise HTTPException(status_code=404, detail="Dashboard layout not found")
    try:
        return dashboard_layout_service.update_layout(
            db,
            layout=layout,
            actor=user,
            name=payload.name,
            description=payload.description,
            config=payload.config.model_dump() if payload.config else None,
            is_shared=payload.is_shared,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))


@router.delete("/{layout_id}", status_code=204)
def delete_layout(
    layout_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    layout = dashboard_layout_service.get_visible_layout(db, user, layout_id)
    if layout is None:
        raise HTTPException(status_code=404, detail="Dashboard layout not found")
    try:
        dashboard_layout_service.delete_layout(db, layout=layout, actor=user)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))

from typing import Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.dashboard_layout import DashboardLayout
from app.models.user import User


def create_layout(
    db: Session, *, name: str, description: Optional[str], config: dict, is_shared: bool, owner: User
) -> DashboardLayout:
    layout = DashboardLayout(name=name, description=description, config=config, is_shared=is_shared, owner_id=owner.id)
    db.add(layout)
    db.commit()
    db.refresh(layout)
    return layout


def list_visible_layouts(db: Session, user: User) -> list[DashboardLayout]:
    return (
        db.query(DashboardLayout)
        .filter(or_(DashboardLayout.is_shared.is_(True), DashboardLayout.owner_id == user.id))
        .order_by(DashboardLayout.name)
        .all()
    )


def get_visible_layout(db: Session, user: User, layout_id: int) -> Optional[DashboardLayout]:
    """Returns None both when the layout doesn't exist and when it exists
    but is private to someone else -- the router turns either case into a
    plain 404, so a private layout's existence is never leaked."""
    layout = db.query(DashboardLayout).filter(DashboardLayout.id == layout_id).first()
    if layout is None:
        return None
    if layout.is_shared or layout.owner_id == user.id or user.role == "Admin":
        return layout
    return None


def update_layout(
    db: Session,
    *,
    layout: DashboardLayout,
    actor: User,
    name: Optional[str] = None,
    description: Optional[str] = None,
    config: Optional[dict] = None,
    is_shared: Optional[bool] = None,
) -> DashboardLayout:
    if layout.owner_id != actor.id and actor.role != "Admin":
        raise PermissionError("Only the owner or an Admin can edit this layout")

    if name is not None:
        layout.name = name
    if description is not None:
        layout.description = description
    if config is not None:
        layout.config = config
    if is_shared is not None:
        layout.is_shared = is_shared

    db.commit()
    db.refresh(layout)
    return layout


def delete_layout(db: Session, *, layout: DashboardLayout, actor: User) -> None:
    if layout.owner_id != actor.id and actor.role != "Admin":
        raise PermissionError("Only the owner or an Admin can delete this layout")
    db.delete(layout)
    db.commit()

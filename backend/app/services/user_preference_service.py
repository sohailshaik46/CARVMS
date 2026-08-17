from sqlalchemy.orm import Session

from app.models.user import User
from app.models.user_preference import UserPreference


def get_or_create_preferences(db: Session, user: User) -> UserPreference:
    """Every user effectively has preferences (defaulted at the column
    level), but the row itself is only created lazily on first read/write --
    a user who never opens Settings never gets a row, so an admin looking
    at raw preference rows sees only people who actually touched a setting."""
    prefs = db.query(UserPreference).filter(UserPreference.user_id == user.id).first()
    if prefs is None:
        prefs = UserPreference(user_id=user.id)
        db.add(prefs)
        db.commit()
        db.refresh(prefs)
    return prefs


def update_preferences(
    db: Session,
    user: User,
    *,
    theme: str | None = None,
    dashboard_config: dict | None = None,
    notification_prefs: dict | None = None,
    security_settings: dict | None = None,
) -> UserPreference:
    prefs = get_or_create_preferences(db, user)
    if theme is not None:
        prefs.theme = theme
    if dashboard_config is not None:
        prefs.dashboard_config = dashboard_config
    if notification_prefs is not None:
        prefs.notification_prefs = notification_prefs
    if security_settings is not None:
        prefs.security_settings = security_settings
    db.commit()
    db.refresh(prefs)
    return prefs

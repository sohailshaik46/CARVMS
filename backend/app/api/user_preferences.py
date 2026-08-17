from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.database.database import get_db
from app.models.user import User
from app.schemas.user_preference import UserPreferenceOut, UserPreferenceUpdateIn
from app.services import user_preference_service

router = APIRouter(prefix="/me/preferences", tags=["User Preferences"])


@router.get("", response_model=UserPreferenceOut)
def get_my_preferences(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return user_preference_service.get_or_create_preferences(db, user)


@router.put("", response_model=UserPreferenceOut)
def update_my_preferences(
    payload: UserPreferenceUpdateIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return user_preference_service.update_preferences(
        db,
        user,
        theme=payload.theme,
        dashboard_config=payload.dashboard_config,
        notification_prefs=payload.notification_prefs,
        security_settings=payload.security_settings,
    )

from typing import Optional

from pydantic import BaseModel, field_validator

from app.models.user_preference import VALID_THEMES


class UserPreferenceOut(BaseModel):
    theme: str
    dashboard_config: dict
    notification_prefs: dict
    security_settings: dict

    model_config = {"from_attributes": True}


class UserPreferenceUpdateIn(BaseModel):
    """Every field optional -- PATCH-like semantics: only what's provided
    gets changed, so the Appearance tab can save a theme change without
    touching Dashboard/Notifications/Security, and vice versa."""

    theme: Optional[str] = None
    dashboard_config: Optional[dict] = None
    notification_prefs: Optional[dict] = None
    security_settings: Optional[dict] = None

    @field_validator("theme")
    @classmethod
    def _theme_must_be_valid(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in VALID_THEMES:
            raise ValueError(f"theme must be one of {VALID_THEMES}")
        return v

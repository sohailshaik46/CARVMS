from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, Integer, JSON, String, func
from sqlalchemy.orm import relationship

from app.database.database import Base

# What "theme" actually controls: whether AppShell/Login wrap their content
# in the `.dark` class that every shared component (Button, Card, Field,
# Modal, Badge, Feedback) and every internal page already carries a
# `dark:` variant for -- see index.css's own comment on this. Per-user, not
# org-wide (each person picks their own), and defaults to "dark" so an
# existing user with no row yet sees exactly what they see today.
VALID_THEMES = ("light", "dark")

DEFAULT_DASHBOARD_CONFIG: dict = {
    # Every KPI key DashboardPage.tsx knows how to render, in the app's
    # current default order. A user's stored config is a (possibly
    # reordered, possibly filtered) subset of this same key set -- the
    # frontend is the source of truth for what each key means and renders;
    # this is purely "which, and in what order", never computed numbers.
    "visible_kpis": [
        "dcb_non_compliance_rate",
        "wrc_non_compliance_rate",
        "dcb_validated_penalty",
        "wrc_penalty",
        "dcb_awaiting_review",
        "wrc_awaiting_review",
        "repeat_violators",
        "zones_with_non_compliance",
    ],
}

DEFAULT_NOTIFICATION_PREFS: dict = {
    "email_on_new_case": True,
    "email_on_decision": True,
    "email_on_escalation": True,
}

DEFAULT_SECURITY_SETTINGS: dict = {
    # Minutes of inactivity before the frontend forces a re-login. Purely a
    # client-side idle timer today -- see frontend/src/auth/useIdleLogout.ts
    # -- not yet a server-enforced session expiry (a still-valid JWT keeps
    # working against the API directly past this window).
    "session_timeout_minutes": 60,
}


class UserPreference(Base):
    """One-to-one with User. Everything here is presentation/personal-
    workflow preference, never a business decision or permission -- role
    and org_node_id (what a user is ALLOWED to see/do) stay on User itself.
    """

    __tablename__ = "user_preferences"
    __table_args__ = (
        CheckConstraint(f"theme IN {VALID_THEMES}", name="ck_user_preferences_theme_valid"),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, unique=True, index=True)

    theme = Column(String, nullable=False, default="dark", server_default="dark")
    dashboard_config = Column(JSON, nullable=False, default=lambda: dict(DEFAULT_DASHBOARD_CONFIG))
    notification_prefs = Column(JSON, nullable=False, default=lambda: dict(DEFAULT_NOTIFICATION_PREFS))
    security_settings = Column(JSON, nullable=False, default=lambda: dict(DEFAULT_SECURITY_SETTINGS))

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    user = relationship("User")

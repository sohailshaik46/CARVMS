"""
Centralized application configuration.

All secrets and environment-dependent values must be read from here, never
hardcoded in source. Values come from environment variables / a local .env
file (see .env.example). .env is git-ignored; nothing here has a production
secret baked in as a default.
"""

from typing import Optional

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # Auth / JWT
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    # Database
    DATABASE_URL: str = "sqlite:///./carvms.db"

    @field_validator("DATABASE_URL")
    @classmethod
    def _normalize_postgres_scheme(cls, v: str) -> str:
        """Some Postgres hosts (Heroku-style, and occasionally Render's
        own connection strings) hand out `postgres://...` -- SQLAlchemy
        2.0 dropped support for that scheme and requires `postgresql://`.
        Rewriting it here means DATABASE_URL can be pasted verbatim from
        wherever the database lives without a manual edit."""
        if v.startswith("postgres://"):
            return "postgresql://" + v[len("postgres://"):]
        return v

    # CORS - comma-separated origins
    CORS_ORIGINS: str = "http://localhost:5173,http://localhost:3000"

    # Base URL of the frontend app. Only used to build the browser redirect
    # at the end of the Gmail OAuth callback (Google redirects to our
    # backend; we then bounce the browser back to the frontend UI).
    FRONTEND_URL: str = "http://localhost:5173"

    # File uploads (evidence, datasets)
    UPLOAD_DIR: str = "uploads"
    MAX_UPLOAD_SIZE_MB: int = 25
    ALLOWED_UPLOAD_MIME_TYPES: str = (
        "application/pdf,"
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document,"
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,"
        "application/vnd.openxmlformats-officedocument.presentationml.presentation,"
        "application/vnd.ms-excel,"
        "text/csv,"
        "image/png,image/jpeg,image/webp"
    )

    # Email integration (Gmail OAuth) -- ALL optional, deliberately. The app
    # must run fully without these set; email-connect features return a
    # clean "not configured" response instead of crashing at startup. Real
    # values go in .env (git-ignored), never here, never in chat.
    GOOGLE_CLIENT_ID: Optional[str] = None
    GOOGLE_CLIENT_SECRET: Optional[str] = None
    GOOGLE_REDIRECT_URI: Optional[str] = None

    # Symmetric key (Fernet) this backend generates locally to encrypt OAuth
    # tokens at rest -- NOT the same thing as the Google client secret. Safe
    # for the agent to generate; unlike GOOGLE_CLIENT_SECRET it isn't issued
    # by an external party.
    EMAIL_TOKEN_ENCRYPTION_KEY: Optional[str] = None

    # Centers Master sheet (Zone/Cluster/Zonal-Cluster-Center-Manager
    # contacts) -- optional. The CSV export URL of a Google Sheet shared
    # as "Anyone with the link -- Viewer". Without it, /org/sync/centers-
    # master/from-sheet returns a clean "not configured" error; the manual
    # upload endpoint always works regardless.
    CENTERS_MASTER_SHEET_CSV_URL: Optional[str] = None

    # One-time bootstrap Admin account -- ALL optional, and only ever acts
    # if the database has zero Admin users yet (see
    # user_service.ensure_bootstrap_admin). Exists because a brand-new
    # deployment's database starts completely empty and self-registration
    # never grants Admin -- without this there'd be no way to create the
    # first Admin account short of direct DB access. Safe to leave set
    # permanently; it's a no-op the moment any Admin exists.
    BOOTSTRAP_ADMIN_USERNAME: Optional[str] = None
    BOOTSTRAP_ADMIN_EMAIL: Optional[str] = None
    BOOTSTRAP_ADMIN_PASSWORD: Optional[str] = None

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

    @property
    def allowed_upload_mime_types_set(self) -> set[str]:
        return {t.strip() for t in self.ALLOWED_UPLOAD_MIME_TYPES.split(",") if t.strip()}

    @property
    def max_upload_size_bytes(self) -> int:
        return self.MAX_UPLOAD_SIZE_MB * 1024 * 1024


settings = Settings()

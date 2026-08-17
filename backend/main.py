from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi

from app.config import settings
from app.api.auth import router as auth_router
from app.api.users import router as users_router
from app.api.org import router as org_router
from app.api.dashboard import router as dashboard_router
from app.api.reports import router as reports_router
from app.api.report_templates import router as report_templates_router
from app.api.search import router as search_router
from app.api.dashboard_layouts import router as dashboard_layouts_router
from app.api.center_scoring import router as center_scoring_router
from app.api.email import router as email_router
from app.api.delayed_cash import router as delayed_cash_router
from app.api.delayed_cash_public import router as delayed_cash_public_router
from app.api.weekly_revenue_closure import router as weekly_revenue_closure_router
from app.api.weekly_revenue_public import router as weekly_revenue_public_router
from app.api.auto_validation import router as auto_validation_router
from app.api.user_preferences import router as user_preferences_router
from app.api.escalations import router as escalations_router

# Schema is managed by Alembic migrations (see alembic/), never by
# Base.metadata.create_all() -- that call used to live here and would
# silently skip evolving an existing table's columns, which is exactly the
# kind of change (is_active type, added timestamps) this project now needs.
# Run `alembic upgrade head` before starting the app.


def _bootstrap_admin_if_configured() -> None:
    """See Settings.BOOTSTRAP_ADMIN_* and user_service.ensure_bootstrap_admin
    -- only ever creates an account on a brand-new deploy with zero Admin
    users; otherwise a fast no-op on every restart."""
    if not (settings.BOOTSTRAP_ADMIN_USERNAME and settings.BOOTSTRAP_ADMIN_EMAIL and settings.BOOTSTRAP_ADMIN_PASSWORD):
        return
    from app.database.database import SessionLocal
    from app.services import user_service

    db = SessionLocal()
    try:
        created = user_service.ensure_bootstrap_admin(
            db,
            username=settings.BOOTSTRAP_ADMIN_USERNAME,
            email=settings.BOOTSTRAP_ADMIN_EMAIL,
            password=settings.BOOTSTRAP_ADMIN_PASSWORD,
        )
        if created is not None:
            print(f"Bootstrap Admin account created: {created.username}")
    finally:
        db.close()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    _bootstrap_admin_if_configured()
    yield


app = FastAPI(
    title="Billing Data Validation API",
    version="1.0.0",
    description="Billing Data Validation -- Delayed Cash Billing + Weekly Revenue Closure vigilance and penalty automation.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(users_router)
app.include_router(org_router)
app.include_router(dashboard_router)
app.include_router(reports_router)
app.include_router(report_templates_router)
app.include_router(search_router)
app.include_router(dashboard_layouts_router)
app.include_router(center_scoring_router)
app.include_router(email_router)
app.include_router(delayed_cash_router)
app.include_router(delayed_cash_public_router)
app.include_router(weekly_revenue_closure_router)
app.include_router(weekly_revenue_public_router)
app.include_router(auto_validation_router)
app.include_router(user_preferences_router)
app.include_router(escalations_router)

# /email/callback and /public/delayed-cash/* are public: reached directly by
# a browser (Google's redirect; a center manager's emailed link) with no
# Authorization header of ours -- each authenticates via its own token
# check instead (see email_connection_service.py / delayed_cash_response_service.py).
PUBLIC_PATHS = {
    "/", "/health", "/auth/login", "/auth/register", "/email/callback",
    "/public/delayed-cash/cases/{token}", "/public/delayed-cash/cases/{token}/respond",
    "/public/weekly-revenue/cases/{token}", "/public/weekly-revenue/cases/{token}/respond",
}


@app.get("/")
def home():
    return {
        "message": "🚀 Welcome to the Billing Data Validation API",
        "status": "Running Successfully",
        "developer": "Sohail Shaik"
    }


@app.get("/health")
def health():
    return {
        "status": "Healthy"
    }


def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema

    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )

    openapi_schema["components"]["securitySchemes"] = {
        "BearerAuth": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT"
        }
    }

    for path in openapi_schema["paths"]:
        if path in PUBLIC_PATHS:
            continue
        for method in openapi_schema["paths"][path]:
            openapi_schema["paths"][path][method]["security"] = [
                {
                    "BearerAuth": []
                }
            ]

    app.openapi_schema = openapi_schema
    return app.openapi_schema


app.openapi = custom_openapi

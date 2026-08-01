from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi

from app.database.database import Base, engine
from app.api.auth import router as auth_router

# Create database tables
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="CARVMS API",
    version="1.0.0",
    description="Central Audit & Revenue Vigilance Management System",
)


app.include_router(auth_router)


@app.get("/")
def home():
    return {
        "message": "🚀 Welcome to CARVMS API",
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
        for method in openapi_schema["paths"][path]:
            if path != "/auth/login" and path != "/auth/register":
                openapi_schema["paths"][path][method]["security"] = [
                    {
                        "BearerAuth": []
                    }
                ]

    app.openapi_schema = openapi_schema
    return app.openapi_schema


app.openapi = custom_openapi
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("SECRET_KEY", "test-only-secret-key-not-for-production")
os.environ.setdefault("UPLOAD_DIR", "test_uploads")

from app.database.database import Base, get_db
import app.models  # noqa: F401 -- registers every model on Base.metadata
from main import app

TEST_DATABASE_URL = "sqlite:///./test_carvms.db"

engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(autouse=True)
def _fresh_test_db():
    """Every test gets a clean schema -- this is a throwaway test DB created
    via create_all, not the real app DB (which is Alembic-managed). Default
    org dimensions are seeded here to mirror what the real migration seeds,
    since create_all doesn't run migration data steps."""
    from app.services.org_service import seed_default_dimensions_if_missing
    from app.services.center_scoring_service import seed_default_weights_if_missing
    from app.services.auto_validation_service import seed_default_rules_if_missing

    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        seed_default_dimensions_if_missing(db)
        seed_default_weights_if_missing(db)
        seed_default_rules_if_missing(db)
    finally:
        db.close()
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="session", autouse=True)
def _cleanup_test_uploads():
    yield
    import shutil

    shutil.rmtree("test_uploads", ignore_errors=True)

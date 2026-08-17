from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base
from sqlalchemy.orm import sessionmaker

from app.config import settings

DATABASE_URL = settings.DATABASE_URL

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(
    DATABASE_URL,
    connect_args=connect_args,
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)

Base = declarative_base()


def get_db():
    """Canonical DB session dependency. Every router/dependency must import
    this instead of defining its own copy."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

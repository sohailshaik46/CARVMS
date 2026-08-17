"""Tests for user_service.ensure_bootstrap_admin -- the one-time-safe path
that creates the very first Admin account on a brand-new deployment with an
empty database (see Settings.BOOTSTRAP_ADMIN_* and main.py's startup hook).
"""
from app.models.user import User
from app.services import user_service
from tests.conftest import TestingSessionLocal


def _register(client, username, email, password="password123"):
    return client.post("/auth/register", json={"username": username, "email": email, "password": password})


def test_creates_admin_when_none_exists(client):
    db = TestingSessionLocal()
    try:
        assert db.query(User).filter(User.role == "Admin").first() is None
        created = user_service.ensure_bootstrap_admin(
            db, username="bootstrap_admin1", email="bootstrap_admin1@example.com", password="password123",
        )
        assert created is not None
        assert created.role == "Admin"
        assert created.is_active is True
        assert db.query(User).filter(User.username == "bootstrap_admin1", User.role == "Admin").first() is not None
    finally:
        db.close()


def test_is_a_no_op_once_an_admin_already_exists(client):
    _register(client, "bootstrap_plain2", "bootstrap_plain2@example.com")
    db = TestingSessionLocal()
    try:
        db.query(User).filter(User.username == "bootstrap_plain2").first().role = "Admin"
        db.commit()

        created = user_service.ensure_bootstrap_admin(
            db, username="bootstrap_admin2", email="bootstrap_admin2@example.com", password="password123",
        )
        assert created is None
        assert db.query(User).filter(User.username == "bootstrap_admin2").first() is None
    finally:
        db.close()


def test_does_not_touch_an_existing_non_admin_account_with_the_same_identity(client):
    _register(client, "bootstrap_taken3", "bootstrap_taken3@example.com")
    db = TestingSessionLocal()
    try:
        before = db.query(User).filter(User.username == "bootstrap_taken3").first()
        assert before.role != "Admin"

        created = user_service.ensure_bootstrap_admin(
            db, username="bootstrap_taken3", email="bootstrap_taken3@example.com", password="password123",
        )
        assert created is None

        after = db.query(User).filter(User.username == "bootstrap_taken3").first()
        assert after.role != "Admin"
    finally:
        db.close()


def test_running_it_twice_only_creates_one_admin(client):
    db = TestingSessionLocal()
    try:
        first = user_service.ensure_bootstrap_admin(
            db, username="bootstrap_admin4", email="bootstrap_admin4@example.com", password="password123",
        )
        assert first is not None

        second = user_service.ensure_bootstrap_admin(
            db, username="bootstrap_admin5", email="bootstrap_admin5@example.com", password="password123",
        )
        assert second is None
        assert db.query(User).filter(User.username == "bootstrap_admin5").first() is None
    finally:
        db.close()

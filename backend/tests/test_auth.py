from datetime import datetime, timedelta, timezone

from jose import jwt

from app.auth.security import SECRET_KEY, ALGORITHM
from tests.conftest import TestingSessionLocal
from app.models.user import User


def _register(client, username="alice", email="alice@example.com", password="password123"):
    return client.post(
        "/auth/register",
        json={"username": username, "email": email, "password": password},
    )


def _login(client, username="alice", password="password123"):
    return client.post(
        "/auth/login",
        json={"username": username, "password": password},
    )


# ---------- health / boot ----------

def test_root_and_health(client):
    assert client.get("/").status_code == 200
    assert client.get("/health").json() == {"status": "Healthy"}


# ---------- registration ----------

def test_register_success(client):
    resp = _register(client)
    assert resp.status_code == 201
    assert resp.json() == {"message": "User registered successfully"}


def test_register_duplicate_email_rejected(client):
    _register(client, username="alice1", email="dup@example.com")
    resp = _register(client, username="alice2", email="dup@example.com")
    assert resp.status_code == 400


def test_register_duplicate_username_rejected(client):
    _register(client, username="dupuser", email="a@example.com")
    resp = _register(client, username="dupuser", email="b@example.com")
    assert resp.status_code == 400


def test_register_ignores_client_supplied_role(client):
    """A client cannot self-promote to Admin (or any other role) at signup --
    the public schema doesn't even accept a role field, and the service layer
    always assigns the configured default role."""
    resp = client.post(
        "/auth/register",
        json={
            "username": "wannabe_admin",
            "email": "wannabe@example.com",
            "password": "password123",
            "role": "Admin",  # extra field the schema does not declare
        },
    )
    assert resp.status_code == 201

    db = TestingSessionLocal()
    try:
        user = db.query(User).filter(User.username == "wannabe_admin").first()
        assert user is not None
        assert user.role == "Auditor"
    finally:
        db.close()


# ---------- login ----------

def test_login_success_returns_jwt(client):
    _register(client)
    resp = _login(client)
    assert resp.status_code == 200
    body = resp.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]

    payload = jwt.decode(body["access_token"], SECRET_KEY, algorithms=[ALGORITHM])
    assert payload["sub"] == "alice"
    assert payload["role"] == "Auditor"
    assert "exp" in payload


def test_login_wrong_password_rejected(client):
    _register(client)
    resp = _login(client, password="wrong-password")
    assert resp.status_code == 401


def test_login_unknown_user_rejected(client):
    resp = _login(client, username="ghost")
    assert resp.status_code == 401


def test_login_inactive_user_rejected(client):
    _register(client, username="bob", email="bob@example.com")
    db = TestingSessionLocal()
    try:
        user = db.query(User).filter(User.username == "bob").first()
        user.is_active = False
        db.commit()
    finally:
        db.close()

    resp = _login(client, username="bob")
    assert resp.status_code == 401


# ---------- /auth/me ----------

def test_me_requires_token(client):
    resp = client.get("/auth/me")
    assert resp.status_code == 401


def test_me_with_valid_token(client):
    _register(client)
    token = _login(client).json()["access_token"]
    resp = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["username"] == "alice"
    assert body["role"] == "Auditor"
    assert body["is_active"] is True
    assert "password" not in body
    assert "password_hash" not in body


def test_me_with_malformed_token_rejected(client):
    resp = client.get("/auth/me", headers={"Authorization": "Bearer not-a-real-token"})
    assert resp.status_code == 401


def test_me_with_expired_token_rejected(client):
    _register(client)
    expired_payload = {
        "sub": "alice",
        "role": "Auditor",
        "exp": datetime.now(timezone.utc) - timedelta(minutes=5),
    }
    expired_token = jwt.encode(expired_payload, SECRET_KEY, algorithm=ALGORITHM)
    resp = client.get("/auth/me", headers={"Authorization": f"Bearer {expired_token}"})
    assert resp.status_code == 401


def test_me_for_deactivated_user_rejected(client):
    _register(client, username="carol", email="carol@example.com")
    token = _login(client, username="carol").json()["access_token"]

    db = TestingSessionLocal()
    try:
        user = db.query(User).filter(User.username == "carol").first()
        user.is_active = False
        db.commit()
    finally:
        db.close()

    resp = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401

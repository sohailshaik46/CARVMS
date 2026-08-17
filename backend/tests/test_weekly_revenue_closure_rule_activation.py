"""Tests for POST /weekly-revenue-closure/rules/activate-default and
GET /weekly-revenue-closure/rules/active -- the endpoints an Admin now
uses instead of needing someone to run a script to unblock the "No
approved WeeklyRevenueClosureRule exists yet" upload error."""

from decimal import Decimal

from app.models.user import User
from tests.conftest import TestingSessionLocal


def _register(client, username, email, password="password123"):
    return client.post("/auth/register", json={"username": username, "email": email, "password": password})


def _login(client, username, password="password123"):
    return client.post("/auth/login", json={"username": username, "password": password}).json()["access_token"]


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _admin(client, username, email):
    _register(client, username, email)
    db = TestingSessionLocal()
    try:
        db.query(User).filter(User.username == username).first().role = "Admin"
        db.commit()
    finally:
        db.close()
    return _login(client, username)


def test_active_rule_404s_when_none_approved_yet(client):
    admin_token = _admin(client, "wrc_rule_none", "wrc_rule_none@example.com")
    resp = client.get("/weekly-revenue-closure/rules/active", headers=_auth(admin_token))
    assert resp.status_code == 404
    assert "no approved" in resp.json()["detail"].lower()


def test_activate_default_rule_creates_and_approves_in_one_step(client):
    admin_token = _admin(client, "wrc_rule_activate", "wrc_rule_activate@example.com")

    resp = client.post("/weekly-revenue-closure/rules/activate-default", headers=_auth(admin_token))
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "approved"
    assert Decimal(body["penalty_rate"]) == Decimal("0.0625")

    active = client.get("/weekly-revenue-closure/rules/active", headers=_auth(admin_token))
    assert active.status_code == 200
    assert active.json()["id"] == body["id"]


def test_activate_default_rule_is_idempotent(client):
    admin_token = _admin(client, "wrc_rule_idempotent", "wrc_rule_idempotent@example.com")

    first = client.post("/weekly-revenue-closure/rules/activate-default", headers=_auth(admin_token)).json()
    second = client.post("/weekly-revenue-closure/rules/activate-default", headers=_auth(admin_token)).json()
    assert first["id"] == second["id"]


def test_activate_default_rule_requires_admin_role(client):
    _register(client, "wrc_rule_plain", "wrc_rule_plain@example.com")
    token = _login(client, "wrc_rule_plain")

    resp = client.post("/weekly-revenue-closure/rules/activate-default", headers=_auth(token))
    assert resp.status_code == 403

from tests.conftest import TestingSessionLocal
from app.models.user import User
from app.models.audit_log import AuditLog


def _register(client, username, email, password="password123"):
    return client.post(
        "/auth/register",
        json={"username": username, "email": email, "password": password},
    )


def _login(client, username, password="password123"):
    resp = client.post("/auth/login", json={"username": username, "password": password})
    return resp.json()["access_token"]


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _promote_to_admin_directly(username: str):
    """Test-only helper: there is no self-serve or public way to create an
    Admin -- exactly the property test_register_ignores_client_supplied_role
    in test_auth.py already checks. We reach into the DB directly here only
    to *set up* an admin fixture for testing the admin endpoints themselves."""
    db = TestingSessionLocal()
    try:
        user = db.query(User).filter(User.username == username).first()
        user.role = "Admin"
        db.commit()
    finally:
        db.close()


def _make_admin_and_login(client, username="root_admin", email="root_admin@example.com"):
    _register(client, username, email)
    _promote_to_admin_directly(username)
    return _login(client, username)


# ---------- RBAC enforcement ----------

def test_non_admin_cannot_list_users(client):
    _register(client, "plain", "plain@example.com")
    token = _login(client, "plain")
    resp = client.get("/users", headers=_auth(token))
    assert resp.status_code == 403


def test_anonymous_cannot_list_users(client):
    resp = client.get("/users")
    assert resp.status_code == 401


def test_admin_can_list_users(client):
    admin_token = _make_admin_and_login(client)
    _register(client, "someone", "someone@example.com")
    resp = client.get("/users", headers=_auth(admin_token))
    assert resp.status_code == 200
    usernames = {u["username"] for u in resp.json()}
    assert {"root_admin", "someone"} <= usernames
    # never leak password/hash fields
    for u in resp.json():
        assert "password" not in u
        assert "password_hash" not in u


# ---------- role changes ----------

def test_admin_can_change_role(client):
    admin_token = _make_admin_and_login(client)
    _register(client, "finance_user", "finance@example.com")

    users = client.get("/users", headers=_auth(admin_token)).json()
    target_id = next(u["id"] for u in users if u["username"] == "finance_user")

    resp = client.patch(
        f"/users/{target_id}/role",
        json={"role": "Finance"},
        headers=_auth(admin_token),
    )
    assert resp.status_code == 200
    assert resp.json()["role"] == "Finance"


def test_admin_cannot_promote_self(client):
    admin_token = _make_admin_and_login(client)
    users = client.get("/users", headers=_auth(admin_token)).json()
    self_id = next(u["id"] for u in users if u["username"] == "root_admin")

    resp = client.patch(
        f"/users/{self_id}/role",
        json={"role": "Finance"},
        headers=_auth(admin_token),
    )
    assert resp.status_code == 400


def test_role_update_rejects_unknown_role(client):
    admin_token = _make_admin_and_login(client)
    _register(client, "someone2", "someone2@example.com")
    users = client.get("/users", headers=_auth(admin_token)).json()
    target_id = next(u["id"] for u in users if u["username"] == "someone2")

    resp = client.patch(
        f"/users/{target_id}/role",
        json={"role": "Super Admin"},
        headers=_auth(admin_token),
    )
    assert resp.status_code == 422


def test_non_admin_cannot_change_roles(client):
    _register(client, "attacker", "attacker@example.com")
    attacker_token = _login(client, "attacker")
    _register(client, "victim", "victim@example.com")

    admin_token = _make_admin_and_login(client, "admin2", "admin2@example.com")
    users = client.get("/users", headers=_auth(admin_token)).json()
    victim_id = next(u["id"] for u in users if u["username"] == "victim")

    resp = client.patch(
        f"/users/{victim_id}/role",
        json={"role": "Admin"},
        headers=_auth(attacker_token),
    )
    assert resp.status_code == 403


# ---------- activation changes ----------

def test_admin_can_deactivate_other_user_and_login_then_fails(client):
    admin_token = _make_admin_and_login(client)
    _register(client, "todeactivate", "todeactivate@example.com")
    users = client.get("/users", headers=_auth(admin_token)).json()
    target_id = next(u["id"] for u in users if u["username"] == "todeactivate")

    resp = client.patch(
        f"/users/{target_id}/active",
        json={"is_active": False},
        headers=_auth(admin_token),
    )
    assert resp.status_code == 200
    assert resp.json()["is_active"] is False

    login_resp = client.post(
        "/auth/login",
        json={"username": "todeactivate", "password": "password123"},
    )
    assert login_resp.status_code == 401


def test_admin_cannot_deactivate_self(client):
    admin_token = _make_admin_and_login(client)
    users = client.get("/users", headers=_auth(admin_token)).json()
    self_id = next(u["id"] for u in users if u["username"] == "root_admin")

    resp = client.patch(
        f"/users/{self_id}/active",
        json={"is_active": False},
        headers=_auth(admin_token),
    )
    assert resp.status_code == 400


# ---------- audit trail ----------

def test_role_change_writes_immutable_audit_log(client):
    admin_token = _make_admin_and_login(client)
    _register(client, "audited_user", "audited@example.com")
    users = client.get("/users", headers=_auth(admin_token)).json()
    target_id = next(u["id"] for u in users if u["username"] == "audited_user")

    client.patch(
        f"/users/{target_id}/role",
        json={"role": "Finance"},
        headers=_auth(admin_token),
    )

    db = TestingSessionLocal()
    try:
        entry = (
            db.query(AuditLog)
            .filter(AuditLog.action == "user.role_changed", AuditLog.entity_id == str(target_id))
            .first()
        )
        assert entry is not None
        assert entry.before_json["role"] == "Auditor"
        assert entry.after_json["role"] == "Finance"
        assert entry.actor_id is not None
    finally:
        db.close()

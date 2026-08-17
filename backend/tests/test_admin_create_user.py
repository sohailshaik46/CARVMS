def _register(client, username, email, password="password123"):
    return client.post("/auth/register", json={"username": username, "email": email, "password": password})


def _login(client, username, password="password123"):
    return client.post("/auth/login", json={"username": username, "password": password}).json()["access_token"]


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _admin(client, username="acu_admin", email="acu_admin@example.com"):
    from app.models.user import User
    from tests.conftest import TestingSessionLocal

    _register(client, username, email)
    db = TestingSessionLocal()
    try:
        db.query(User).filter(User.username == username).first().role = "Admin"
        db.commit()
    finally:
        db.close()
    return _login(client, username)


def test_admin_can_create_user_with_a_real_role_immediately(client):
    admin_token = _admin(client)
    resp = client.post(
        "/users",
        json={
            "username": "acu_newuser",
            "email": "acu_newuser@example.com",
            "password": "somepassword1",
            "phone_number": "+919876543210",
            "role": "Finance",
        },
        headers=_auth(admin_token),
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["role"] == "Finance"
    assert body["phone_number"] == "+919876543210"

    # the created account can actually log in
    login = client.post("/auth/login", json={"username": "acu_newuser", "password": "somepassword1"})
    assert login.status_code == 200


def test_admin_create_user_defaults_role_to_auditor(client):
    admin_token = _admin(client, "acu_admin2", "acu_admin2@example.com")
    resp = client.post(
        "/users",
        json={"username": "acu_newuser2", "email": "acu_newuser2@example.com", "password": "somepassword2"},
        headers=_auth(admin_token),
    )
    assert resp.status_code == 201
    assert resp.json()["role"] == "Auditor"
    assert resp.json()["phone_number"] is None


def test_admin_create_user_rejects_duplicate_username(client):
    admin_token = _admin(client, "acu_admin3", "acu_admin3@example.com")
    client.post(
        "/users",
        json={"username": "acu_dupe", "email": "acu_dupe1@example.com", "password": "somepassword3"},
        headers=_auth(admin_token),
    )
    resp = client.post(
        "/users",
        json={"username": "acu_dupe", "email": "acu_dupe2@example.com", "password": "somepassword3"},
        headers=_auth(admin_token),
    )
    assert resp.status_code == 400


def test_non_admin_cannot_create_user(client):
    _register(client, "acu_plain", "acu_plain@example.com")
    token = _login(client, "acu_plain")
    resp = client.post(
        "/users",
        json={"username": "acu_x", "email": "acu_x@example.com", "password": "somepassword4"},
        headers=_auth(token),
    )
    assert resp.status_code == 403


def test_admin_create_user_rejects_invalid_role(client):
    admin_token = _admin(client, "acu_admin4", "acu_admin4@example.com")
    resp = client.post(
        "/users",
        json={"username": "acu_badrole", "email": "acu_badrole@example.com", "password": "somepassword5", "role": "NotARole"},
        headers=_auth(admin_token),
    )
    assert resp.status_code == 422

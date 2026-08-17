def _register(client, username, email, password="password123", phone_number=None):
    payload = {"username": username, "email": email, "password": password}
    if phone_number is not None:
        payload["phone_number"] = phone_number
    return client.post("/auth/register", json=payload)


def _login(client, username, password="password123"):
    return client.post("/auth/login", json={"username": username, "password": password}).json()["access_token"]


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _admin(client, username="phone_admin", email="phone_admin@example.com"):
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


def test_register_without_phone_number_still_works(client):
    resp = _register(client, "nophone_user", "nophone_user@example.com")
    assert resp.status_code == 201
    token = _login(client, "nophone_user")
    me = client.get("/auth/me", headers=_auth(token))
    assert me.json()["phone_number"] is None


def test_register_with_phone_number_persists_it(client):
    resp = _register(client, "phone_user", "phone_user@example.com", phone_number="+919154187948")
    assert resp.status_code == 201
    token = _login(client, "phone_user")
    me = client.get("/auth/me", headers=_auth(token))
    assert me.json()["phone_number"] == "+919154187948"


def test_register_with_malformed_phone_number_rejected(client):
    resp = _register(client, "badphone_user", "badphone_user@example.com", phone_number="9154187948")
    assert resp.status_code == 422


def test_change_my_password_requires_correct_current_password(client):
    _register(client, "pw_user1", "pw_user1@example.com", phone_number="+919999999999")
    token = _login(client, "pw_user1")
    resp = client.patch(
        "/auth/me/password",
        json={"current_password": "wrong-password", "new_password": "newpassword123"},
        headers=_auth(token),
    )
    assert resp.status_code == 400


def test_change_my_password_succeeds_and_new_password_logs_in(client):
    _register(client, "pw_user2", "pw_user2@example.com")
    token = _login(client, "pw_user2")
    resp = client.patch(
        "/auth/me/password",
        json={"current_password": "password123", "new_password": "newpassword456"},
        headers=_auth(token),
    )
    assert resp.status_code == 200

    # old password no longer works
    old = client.post("/auth/login", json={"username": "pw_user2", "password": "password123"})
    assert old.status_code == 401

    # new password does
    new = client.post("/auth/login", json={"username": "pw_user2", "password": "newpassword456"})
    assert new.status_code == 200


def test_update_my_phone_number_self_service(client):
    _register(client, "phone_self", "phone_self@example.com")
    token = _login(client, "phone_self")
    resp = client.patch("/auth/me/phone", json={"phone_number": "+917331191185"}, headers=_auth(token))
    assert resp.status_code == 200
    assert resp.json()["phone_number"] == "+917331191185"


def test_admin_can_set_another_users_phone_number(client):
    admin_token = _admin(client)
    _register(client, "phone_target", "phone_target@example.com")
    from app.models.user import User
    from tests.conftest import TestingSessionLocal

    db = TestingSessionLocal()
    try:
        target_id = db.query(User).filter(User.username == "phone_target").first().id
    finally:
        db.close()

    resp = client.patch(f"/users/{target_id}/phone", json={"phone_number": "+911234567890"}, headers=_auth(admin_token))
    assert resp.status_code == 200
    assert resp.json()["phone_number"] == "+911234567890"


def test_non_admin_cannot_set_another_users_phone_number(client):
    _register(client, "phone_plain", "phone_plain@example.com")
    token = _login(client, "phone_plain")
    resp = client.patch("/users/999999/phone", json={"phone_number": "+911234567890"}, headers=_auth(token))
    assert resp.status_code == 403

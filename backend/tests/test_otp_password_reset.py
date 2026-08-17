from app.models.otp import OtpCode
from app.models.user import User
from tests.conftest import TestingSessionLocal


def _register(client, username, email, password="password123", phone_number=None):
    payload = {"username": username, "email": email, "password": password}
    if phone_number is not None:
        payload["phone_number"] = phone_number
    return client.post("/auth/register", json=payload)


def _login(client, username, password="password123"):
    return client.post("/auth/login", json={"username": username, "password": password}).json()["access_token"]


def test_forgot_password_for_unregistered_number_returns_generic_message(client):
    resp = client.post("/auth/forgot-password", json={"phone_number": "+919000000000"})
    assert resp.status_code == 200
    assert "registered" in resp.json()["message"].lower()


def test_forgot_password_for_registered_number_creates_otp_row_even_without_sms_provider(client):
    _register(client, "otp_user1", "otp_user1@example.com", phone_number="+919111111111")
    resp = client.post("/auth/forgot-password", json={"phone_number": "+919111111111"})
    assert resp.status_code == 200

    db = TestingSessionLocal()
    try:
        user = db.query(User).filter(User.username == "otp_user1").first()
        rows = db.query(OtpCode).filter(OtpCode.user_id == user.id).all()
        assert len(rows) == 1
        assert rows[0].consumed_at is None
    finally:
        db.close()


def test_reset_password_with_correct_code_succeeds(client, monkeypatch):
    _register(client, "otp_user2", "otp_user2@example.com", phone_number="+919222222222")

    monkeypatch.setattr("app.services.otp_service._generate_code", lambda: "123456")
    resp = client.post("/auth/forgot-password", json={"phone_number": "+919222222222"})
    assert resp.status_code == 200

    reset = client.post(
        "/auth/reset-password",
        json={"phone_number": "+919222222222", "code": "123456", "new_password": "brandnewpassword"},
    )
    assert reset.status_code == 200

    assert client.post("/auth/login", json={"username": "otp_user2", "password": "password123"}).status_code == 401
    assert client.post("/auth/login", json={"username": "otp_user2", "password": "brandnewpassword"}).status_code == 200


def test_reset_password_with_wrong_code_rejected(client, monkeypatch):
    _register(client, "otp_user3", "otp_user3@example.com", phone_number="+919333333333")
    monkeypatch.setattr("app.services.otp_service._generate_code", lambda: "111111")
    client.post("/auth/forgot-password", json={"phone_number": "+919333333333"})

    resp = client.post(
        "/auth/reset-password",
        json={"phone_number": "+919333333333", "code": "000000", "new_password": "somenewpassword"},
    )
    assert resp.status_code == 400
    # password unchanged
    assert client.post("/auth/login", json={"username": "otp_user3", "password": "password123"}).status_code == 200


def test_reset_password_code_cannot_be_reused(client, monkeypatch):
    _register(client, "otp_user4", "otp_user4@example.com", phone_number="+919444444444")
    monkeypatch.setattr("app.services.otp_service._generate_code", lambda: "222222")
    client.post("/auth/forgot-password", json={"phone_number": "+919444444444"})

    first = client.post(
        "/auth/reset-password",
        json={"phone_number": "+919444444444", "code": "222222", "new_password": "firstnewpassword"},
    )
    assert first.status_code == 200

    second = client.post(
        "/auth/reset-password",
        json={"phone_number": "+919444444444", "code": "222222", "new_password": "secondnewpassword"},
    )
    assert second.status_code == 400


def test_reset_password_too_many_wrong_attempts_locks_out_the_code(client, monkeypatch):
    _register(client, "otp_user5", "otp_user5@example.com", phone_number="+919555555555")
    monkeypatch.setattr("app.services.otp_service._generate_code", lambda: "333333")
    client.post("/auth/forgot-password", json={"phone_number": "+919555555555"})

    for _ in range(5):
        resp = client.post(
            "/auth/reset-password",
            json={"phone_number": "+919555555555", "code": "999999", "new_password": "irrelevant123"},
        )
        assert resp.status_code == 400

    # even the CORRECT code is now rejected -- attempt cap exhausted
    correct = client.post(
        "/auth/reset-password",
        json={"phone_number": "+919555555555", "code": "333333", "new_password": "shouldnotwork1"},
    )
    assert correct.status_code == 400

from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse

from cryptography.fernet import Fernet

from tests.conftest import TestingSessionLocal
from app.config.settings import settings
from app.models.email_connection import EmailConnection, EmailConnectionRequest
from app.services import crypto_service, email_connection_service


def _register(client, username, email, password="password123"):
    return client.post("/auth/register", json={"username": username, "email": email, "password": password})


def _login(client, username, password="password123"):
    resp = client.post("/auth/login", json={"username": username, "password": password})
    return resp.json()["access_token"]

def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _user(client, username, email):
    _register(client, username, email)
    return _login(client, username)


def _configure_google(monkeypatch):
    """Dummy, never-real credentials -- no test in this file ever reaches
    the actual Google endpoint; exchange_code_for_tokens' httpx.post call
    is mocked wherever a real token exchange would otherwise happen."""
    monkeypatch.setattr(settings, "GOOGLE_CLIENT_ID", "test-client-id")
    monkeypatch.setattr(settings, "GOOGLE_CLIENT_SECRET", "test-client-secret")
    monkeypatch.setattr(settings, "GOOGLE_REDIRECT_URI", "http://localhost:8000/email/callback")


def _configure_encryption_key(monkeypatch):
    monkeypatch.setattr(settings, "EMAIL_TOKEN_ENCRYPTION_KEY", Fernet.generate_key().decode())


def _unconfigure_google(monkeypatch):
    monkeypatch.setattr(settings, "GOOGLE_CLIENT_ID", None)
    monkeypatch.setattr(settings, "GOOGLE_CLIENT_SECRET", None)


class _FakeGoogleResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


def _mock_token_exchange(monkeypatch, payload):
    monkeypatch.setattr(
        email_connection_service.httpx, "post", lambda *a, **kw: _FakeGoogleResponse(payload)
    )


def _state_from_authorization_url(url: str) -> str:
    return parse_qs(urlparse(url).query)["state"][0]


# ---------- /email/providers ----------

def test_providers_not_configured_by_default(client, monkeypatch):
    _unconfigure_google(monkeypatch)
    token = _user(client, "email_u1", "email_u1@example.com")
    resp = client.get("/email/providers", headers=_auth(token))
    assert resp.status_code == 200
    assert resp.json() == [{"provider": "gmail", "configured": False}]


def test_providers_configured_once_credentials_set(client, monkeypatch):
    _configure_google(monkeypatch)
    token = _user(client, "email_u2", "email_u2@example.com")
    resp = client.get("/email/providers", headers=_auth(token))
    assert resp.json() == [{"provider": "gmail", "configured": True}]


# ---------- /email/connect ----------

def test_connect_requires_configuration(client, monkeypatch):
    _unconfigure_google(monkeypatch)
    token = _user(client, "email_u3", "email_u3@example.com")
    resp = client.get("/email/connect", headers=_auth(token))
    assert resp.status_code == 400


def test_connect_returns_google_url_and_pending_request(client, monkeypatch):
    _configure_google(monkeypatch)
    token = _user(client, "email_u4", "email_u4@example.com")

    resp = client.get("/email/connect", headers=_auth(token))
    assert resp.status_code == 200
    url = resp.json()["authorization_url"]
    assert url.startswith(email_connection_service.GOOGLE_AUTH_URL)
    assert "state=" in url

    db = TestingSessionLocal()
    try:
        pending = db.query(EmailConnectionRequest).all()
        assert len(pending) == 1
        assert pending[0].provider == "gmail"
    finally:
        db.close()


def test_connect_and_status_and_disconnect_require_auth(client):
    assert client.get("/email/connect").status_code == 401
    assert client.get("/email/status").status_code == 401
    assert client.post("/email/disconnect").status_code == 401


# ---------- /email/callback ----------

def test_callback_missing_params_redirects_with_error(client):
    resp = client.get("/email/callback", follow_redirects=False)
    assert resp.status_code in (302, 307)
    assert "email_error=missing_code_or_state" in resp.headers["location"]


def test_callback_google_denied_redirects_with_error(client):
    resp = client.get("/email/callback?error=access_denied", follow_redirects=False)
    assert "email_error=access_denied" in resp.headers["location"]


def test_callback_unknown_state_redirects_with_error(client):
    resp = client.get("/email/callback?code=abc&state=does-not-exist", follow_redirects=False)
    assert "email_error=" in resp.headers["location"]


def test_callback_expired_state_redirects_with_error(client, monkeypatch):
    _configure_google(monkeypatch)
    token = _user(client, "email_u5", "email_u5@example.com")
    url = client.get("/email/connect", headers=_auth(token)).json()["authorization_url"]
    state = _state_from_authorization_url(url)

    db = TestingSessionLocal()
    try:
        pending = db.query(EmailConnectionRequest).filter(EmailConnectionRequest.state_token == state).first()
        pending.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        db.commit()
    finally:
        db.close()

    resp = client.get(f"/email/callback?code=abc&state={state}", follow_redirects=False)
    assert "email_error=" in resp.headers["location"]


def test_callback_success_stores_encrypted_tokens_and_status_reflects_it(client, monkeypatch):
    _configure_google(monkeypatch)
    _configure_encryption_key(monkeypatch)
    token = _user(client, "email_u6", "email_u6@example.com")

    url = client.get("/email/connect", headers=_auth(token)).json()["authorization_url"]
    state = _state_from_authorization_url(url)

    _mock_token_exchange(
        monkeypatch,
        {"access_token": "real-access-token", "refresh_token": "real-refresh-token", "expires_in": 3600, "scope": "gmail.readonly"},
    )

    resp = client.get(f"/email/callback?code=fake-code&state={state}", follow_redirects=False)
    assert "email_connected=1" in resp.headers["location"]

    status = client.get("/email/status", headers=_auth(token)).json()
    assert status["connected"] is True
    assert status["provider"] == "gmail"
    assert status["scope"] == "gmail.readonly"

    db = TestingSessionLocal()
    try:
        connection = db.query(EmailConnection).first()
        assert connection.encrypted_access_token != "real-access-token"
        assert crypto_service.decrypt(connection.encrypted_access_token) == "real-access-token"
        assert crypto_service.decrypt(connection.encrypted_refresh_token) == "real-refresh-token"
        # the state token/request must be consumed, not reusable
        assert db.query(EmailConnectionRequest).count() == 0
    finally:
        db.close()

    # Re-using the same (now-consumed) state token must fail cleanly.
    replay = client.get(f"/email/callback?code=fake-code&state={state}", follow_redirects=False)
    assert "email_error=" in replay.headers["location"]


def test_disconnect_clears_stored_tokens(client, monkeypatch):
    _configure_google(monkeypatch)
    _configure_encryption_key(monkeypatch)
    token = _user(client, "email_u7", "email_u7@example.com")

    url = client.get("/email/connect", headers=_auth(token)).json()["authorization_url"]
    state = _state_from_authorization_url(url)
    _mock_token_exchange(monkeypatch, {"access_token": "at", "refresh_token": "rt", "expires_in": 3600})
    client.get(f"/email/callback?code=c&state={state}", follow_redirects=False)

    resp = client.post("/email/disconnect", headers=_auth(token))
    assert resp.status_code == 204

    status = client.get("/email/status", headers=_auth(token)).json()
    assert status["connected"] is False

    db = TestingSessionLocal()
    try:
        connection = db.query(EmailConnection).first()
        assert connection.status == "revoked"
        assert connection.encrypted_access_token is None
        assert connection.encrypted_refresh_token is None
    finally:
        db.close()


def test_disconnect_with_no_connection_is_a_no_op(client):
    token = _user(client, "email_u8", "email_u8@example.com")
    resp = client.post("/email/disconnect", headers=_auth(token))
    assert resp.status_code == 204


def test_status_with_no_connection_reports_not_connected(client):
    token = _user(client, "email_u9", "email_u9@example.com")
    resp = client.get("/email/status", headers=_auth(token)).json()
    assert resp == {"connected": False, "provider": None, "scope": None, "connected_at": None, "can_send": False}


def test_status_flags_can_send_false_for_a_readonly_only_connection(client, monkeypatch):
    """A connection made before gmail.send was requested (or one where the
    user declined the broader scope) must NOT be reported as send-capable
    -- Google never retroactively grants a new scope to an old token."""
    _configure_google(monkeypatch)
    _configure_encryption_key(monkeypatch)
    token = _user(client, "email_u10", "email_u10@example.com")

    url = client.get("/email/connect", headers=_auth(token)).json()["authorization_url"]
    state = _state_from_authorization_url(url)
    _mock_token_exchange(
        monkeypatch,
        {"access_token": "at", "refresh_token": "rt", "expires_in": 3600, "scope": "gmail.readonly openid email"},
    )
    client.get(f"/email/callback?code=c&state={state}", follow_redirects=False)

    status = client.get("/email/status", headers=_auth(token)).json()
    assert status["connected"] is True
    assert status["can_send"] is False


def test_status_flags_can_send_true_once_send_scope_is_granted(client, monkeypatch):
    _configure_google(monkeypatch)
    _configure_encryption_key(monkeypatch)
    token = _user(client, "email_u11", "email_u11@example.com")

    url = client.get("/email/connect", headers=_auth(token)).json()["authorization_url"]
    state = _state_from_authorization_url(url)
    _mock_token_exchange(
        monkeypatch,
        {
            "access_token": "at",
            "refresh_token": "rt",
            "expires_in": 3600,
            "scope": "gmail.readonly https://www.googleapis.com/auth/gmail.send openid email",
        },
    )
    client.get(f"/email/callback?code=c&state={state}", follow_redirects=False)

    status = client.get("/email/status", headers=_auth(token)).json()
    assert status["can_send"] is True

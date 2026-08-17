"""Tests for POST /delayed-cash/bills/{id}/notify -- decision-triggered
center email. Every test mocks the Gmail send boundary (email_send_service.
httpx.post) and, where a connection is needed, the token-exchange boundary
(email_connection_service.httpx.post) -- no test here ever reaches Google.
"""

from datetime import date, datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse

from cryptography.fernet import Fernet

from app.config.settings import settings
from app.models.org import OrgDimension, OrgNode
from app.models.user import User
from app.services import delayed_cash_penalty_service as calc_svc
from app.services import email_send_service
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


def _make_case_with_bill(username_suffix):
    db = TestingSessionLocal()
    try:
        import bcrypt

        user = User(
            username=f"dcbnotify_setup{username_suffix}",
            email=f"dcbnotify_setup{username_suffix}@example.com",
            password_hash=bcrypt.hashpw(b"password123", bcrypt.gensalt()).decode(),
            role="Admin",
            is_active=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        rule = calc_svc.create_rule(db, rule_version=f"DCB-NOTIFY-{username_suffix}", created_by=user)
        calc_svc.approve_rule(db, rule=rule, approver=user)
        batch = calc_svc.create_upload_batch(
            db, period_start=date(2026, 7, 1), period_end=date(2026, 7, 31),
            source_filename="notify-test.xlsx", rule=rule, uploaded_by=user,
        )
        bill_date = date(2026, 7, 1)
        created = bill_date + timedelta(days=2)
        code = f"NOTIFY-C{username_suffix}"
        raw = calc_svc.RawBillInput(
            centre_code=code, centre_name="Notify Test Center",
            sales_bill=f"NOTIFY-{username_suffix}-1", bill_date=bill_date,
            bill_created_time=datetime.combine(created, datetime.min.time(), tzinfo=timezone.utc),
            created_date=created, source_day_difference=2,
        )
        calc_svc.ingest_bills(db, batch=batch, rule=rule, raw_bills=[raw])
        calc_svc.compute_center_penalties(db, batch=batch, rule=rule)
        bill_id = (
            db.query(calc_svc.DelayedCashBill)
            .filter(calc_svc.DelayedCashBill.batch_id == batch.id, calc_svc.DelayedCashBill.centre_code == code)
            .first()
            .id
        )
        return bill_id, code
    finally:
        db.close()


def _give_center_an_email(centre_code, email):
    db = TestingSessionLocal()
    try:
        dimension = OrgDimension(key=f"center-{centre_code}", label="Center", sort_order=0)
        db.add(dimension)
        db.commit()
        db.refresh(dimension)
        node = OrgNode(dimension_id=dimension.id, parent_id=None, name=centre_code, external_code=centre_code, manager_email=email)
        db.add(node)
        db.commit()
    finally:
        db.close()


def _configure_google(monkeypatch):
    monkeypatch.setattr(settings, "GOOGLE_CLIENT_ID", "test-client-id")
    monkeypatch.setattr(settings, "GOOGLE_CLIENT_SECRET", "test-client-secret")
    monkeypatch.setattr(settings, "GOOGLE_REDIRECT_URI", "http://localhost:8000/email/callback")
    monkeypatch.setattr(settings, "EMAIL_TOKEN_ENCRYPTION_KEY", Fernet.generate_key().decode())


class _FakeGoogleResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


def _connect_gmail_with_send_scope(client, monkeypatch, token, *, refresh_token="rt", expires_in=3600):
    from app.services import email_connection_service

    monkeypatch.setattr(
        email_connection_service.httpx,
        "post",
        lambda *a, **kw: _FakeGoogleResponse(
            {
                "access_token": "at",
                "refresh_token": refresh_token,
                "expires_in": expires_in,
                "scope": "gmail.readonly https://www.googleapis.com/auth/gmail.send openid email",
            }
        ),
    )
    url = client.get("/email/connect", headers=_auth(token)).json()["authorization_url"]
    state = parse_qs(urlparse(url).query)["state"][0]
    client.get(f"/email/callback?code=fake-code&state={state}", follow_redirects=False)


class _FakeGmailSendResponse:
    def __init__(self, status_code=200):
        self.status_code = status_code
        self.text = "ok"

    def raise_for_status(self):
        if self.status_code >= 400:
            import httpx

            raise httpx.HTTPStatusError("boom", request=None, response=self)


def _mock_gmail_send_success(monkeypatch, captured):
    def fake_post(url, headers=None, json=None, timeout=None):
        captured.append({"url": url, "headers": headers, "json": json})
        return _FakeGmailSendResponse(200)

    monkeypatch.setattr(email_send_service.httpx, "post", fake_post)


def _mock_gmail_send_rejected(monkeypatch):
    monkeypatch.setattr(email_send_service.httpx, "post", lambda *a, **kw: _FakeGmailSendResponse(403))


# ---------------------------------------------------------------------------
# Guard rails


def test_notify_requires_a_decision_first(client, monkeypatch):
    admin_token = _admin(client, "dcbnotify_admin1", "dcbnotify_admin1@example.com")
    bill_id, code = _make_case_with_bill("1")

    resp = client.post(f"/delayed-cash/bills/{bill_id}/notify", json={}, headers=_auth(admin_token))
    assert resp.status_code == 400


def test_notify_followup_requires_a_comment(client, monkeypatch):
    admin_token = _admin(client, "dcbnotify_admin2", "dcbnotify_admin2@example.com")
    bill_id, code = _make_case_with_bill("2")
    client.post(f"/delayed-cash/bills/{bill_id}/review", json={"decision": "needs_more_detail"}, headers=_auth(admin_token))

    resp = client.post(f"/delayed-cash/bills/{bill_id}/notify", json={}, headers=_auth(admin_token))
    assert resp.status_code == 400


def test_notify_requires_vigilance_role(client):
    bill_id, code = _make_case_with_bill("3")
    assert client.post(f"/delayed-cash/bills/{bill_id}/notify", json={}).status_code == 401


# ---------------------------------------------------------------------------
# Graceful degradation -- decision is never blocked by a failed send


def test_notify_reports_no_mailbox_connected(client, monkeypatch):
    admin_token = _admin(client, "dcbnotify_admin4", "dcbnotify_admin4@example.com")
    bill_id, code = _make_case_with_bill("4")
    _give_center_an_email(code, "manager4@example.com")
    client.post(f"/delayed-cash/bills/{bill_id}/review", json={"decision": "considered"}, headers=_auth(admin_token))

    resp = client.post(f"/delayed-cash/bills/{bill_id}/notify", json={}, headers=_auth(admin_token))
    assert resp.status_code == 200
    body = resp.json()
    assert body["sent"] is False
    assert "connect" in body["reason"].lower()


def test_notify_reports_no_email_on_file(client, monkeypatch):
    admin_token = _admin(client, "dcbnotify_admin5", "dcbnotify_admin5@example.com")
    bill_id, code = _make_case_with_bill("5")
    _configure_google(monkeypatch)
    _connect_gmail_with_send_scope(client, monkeypatch, admin_token)
    client.post(f"/delayed-cash/bills/{bill_id}/review", json={"decision": "considered"}, headers=_auth(admin_token))

    resp = client.post(f"/delayed-cash/bills/{bill_id}/notify", json={}, headers=_auth(admin_token))
    assert resp.status_code == 200
    body = resp.json()
    assert body["sent"] is False
    assert "no email on file" in body["reason"].lower()


def test_notify_reports_gmail_rejection(client, monkeypatch):
    admin_token = _admin(client, "dcbnotify_admin6", "dcbnotify_admin6@example.com")
    bill_id, code = _make_case_with_bill("6")
    _give_center_an_email(code, "manager6@example.com")
    _configure_google(monkeypatch)
    _connect_gmail_with_send_scope(client, monkeypatch, admin_token)
    _mock_gmail_send_rejected(monkeypatch)
    client.post(f"/delayed-cash/bills/{bill_id}/review", json={"decision": "considered"}, headers=_auth(admin_token))

    resp = client.post(f"/delayed-cash/bills/{bill_id}/notify", json={}, headers=_auth(admin_token))
    assert resp.status_code == 200
    body = resp.json()
    assert body["sent"] is False
    assert "gmail rejected" in body["reason"].lower()


# ---------------------------------------------------------------------------
# The real success paths


def test_notify_terminal_decision_sends_a_fixed_notice(client, monkeypatch):
    admin_token = _admin(client, "dcbnotify_admin7", "dcbnotify_admin7@example.com")
    bill_id, code = _make_case_with_bill("7")
    _give_center_an_email(code, "manager7@example.com")
    _configure_google(monkeypatch)
    _connect_gmail_with_send_scope(client, monkeypatch, admin_token)
    captured = []
    _mock_gmail_send_success(monkeypatch, captured)
    client.post(f"/delayed-cash/bills/{bill_id}/review", json={"decision": "not_considered"}, headers=_auth(admin_token))

    resp = client.post(f"/delayed-cash/bills/{bill_id}/notify", json={}, headers=_auth(admin_token))
    assert resp.status_code == 200
    assert resp.json() == {"sent": True, "reason": None}
    assert len(captured) == 1
    assert captured[0]["headers"]["Authorization"] == "Bearer at"


def test_notify_followup_sends_comment_and_a_fresh_response_link(client, monkeypatch):
    import base64

    admin_token = _admin(client, "dcbnotify_admin8", "dcbnotify_admin8@example.com")
    bill_id, code = _make_case_with_bill("8")
    _give_center_an_email(code, "manager8@example.com")
    _configure_google(monkeypatch)
    _connect_gmail_with_send_scope(client, monkeypatch, admin_token)
    captured = []
    _mock_gmail_send_success(monkeypatch, captured)
    client.post(f"/delayed-cash/bills/{bill_id}/review", json={"decision": "needs_proof"}, headers=_auth(admin_token))

    resp = client.post(
        f"/delayed-cash/bills/{bill_id}/notify", json={"comment": "Please attach the courier receipt"}, headers=_auth(admin_token)
    )
    assert resp.status_code == 200
    assert resp.json() == {"sent": True, "reason": None}

    raw = base64.urlsafe_b64decode(captured[0]["json"]["raw"])
    decoded = raw.decode("utf-8", errors="ignore")
    assert "Please attach the courier receipt" in decoded
    assert f"{settings.FRONTEND_URL}/respond/delayed-cash/" in decoded
    assert "manager8@example.com" in decoded


def test_notify_uses_the_most_recently_connected_send_capable_mailbox(client, monkeypatch):
    """There's no per-reviewer mailbox -- whichever registered account is
    connected sends on behalf of the whole system, regardless of which
    Vigilance user clicked notify."""
    admin_token = _admin(client, "dcbnotify_admin9", "dcbnotify_admin9@example.com")
    other_token = _admin(client, "dcbnotify_admin9b", "dcbnotify_admin9b@example.com")
    bill_id, code = _make_case_with_bill("9")
    _give_center_an_email(code, "manager9@example.com")
    _configure_google(monkeypatch)
    _connect_gmail_with_send_scope(client, monkeypatch, other_token)
    captured = []
    _mock_gmail_send_success(monkeypatch, captured)
    client.post(f"/delayed-cash/bills/{bill_id}/review", json={"decision": "considered"}, headers=_auth(admin_token))

    resp = client.post(f"/delayed-cash/bills/{bill_id}/notify", json={}, headers=_auth(admin_token))
    assert resp.json() == {"sent": True, "reason": None}
    assert len(captured) == 1

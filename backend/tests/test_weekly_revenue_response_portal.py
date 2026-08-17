"""Tests for the Weekly Revenue Closure public response portal, Action
Taken, Centers Activity, and decision-notification email -- mirrors the
Delayed Cash Billing test suites for the same features
(test_delayed_cash_review_queue.py, test_delayed_cash_center_activity.py,
test_delayed_cash_notifications.py), adapted for WRC's real decision model
(considered/not_considered only) and its case-handle design (see
WeeklyRevenueCenterCase's model docstring for why it's decoupled from
WeeklyRevenueCenterPenalty)."""

from datetime import date
from io import BytesIO
from urllib.parse import parse_qs, urlparse

from cryptography.fernet import Fernet

from app.config.settings import settings
from app.models.org import OrgDimension, OrgNode
from app.models.user import User
from app.services import weekly_revenue_closure_service as wrc_svc
from app.services import email_send_service
from tests.conftest import TestingSessionLocal


def _register(client, username, email, password="password123"):
    return client.post("/auth/register", json={"username": username, "email": email, "password": password})


def _login(client, username, password="password123"):
    return client.post("/auth/login", json={"username": username, "password": password}).json()["access_token"]


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _admin(client, username="wrc_pp_admin", email="wrc_pp_admin@example.com"):
    _register(client, username, email)
    db = TestingSessionLocal()
    try:
        db.query(User).filter(User.username == username).first().role = "Admin"
        db.commit()
    finally:
        db.close()
    return _login(client, username)


def _make_user(username):
    db = TestingSessionLocal()
    try:
        import bcrypt

        user = User(
            username=username, email=f"{username}@example.com",
            password_hash=bcrypt.hashpw(b"password123", bcrypt.gensalt()).decode(),
            role="Admin", is_active=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user
    finally:
        db.close()


def _make_batch_with_incident(suffix: str, centre_code=None):
    _make_user(f"wrc_pp_setup{suffix}")
    db = TestingSessionLocal()
    try:
        user = db.query(User).filter(User.username == f"wrc_pp_setup{suffix}").first()
        rule = wrc_svc.create_rule(db, rule_version=f"PP-WRC-{suffix}", created_by=user)
        wrc_svc.approve_rule(db, rule=rule, approver=user)
        batch = wrc_svc.create_batch(
            db, period_start=date(2026, 7, 1), period_end=date(2026, 7, 7),
            week_label=f"Week PP {suffix}", rule=rule, created_by=user,
        )
        code = centre_code or f"PP-WRC-{suffix}"
        raw = wrc_svc.RawBillIncidentInput(
            centre_code=code, centre_name=f"PP Test Center {suffix}",
            incident_date=date(2026, 7, 2), mis_final_remark="bill_pending",
        )
        incidents = wrc_svc.record_bill_incidents(db, batch=batch, raw_incidents=[raw])
        return incidents[0].id, batch.id, code
    finally:
        db.close()


def _evidence_file(name="proof.pdf", content=b"%PDF-1.4 fake evidence content"):
    return {"evidence": (name, BytesIO(content), "application/pdf")}


# ---------------------------------------------------------------------------
# Response link + public portal


def test_response_link_can_be_minted_and_opened(client):
    admin_token = _admin(client)
    incident_id, batch_id, code = _make_batch_with_incident("1")

    link = client.post(
        f"/weekly-revenue-closure/batches/{batch_id}/centers/{code}/response-link", headers=_auth(admin_token)
    ).json()
    assert link["response_url"].startswith(f"{settings.FRONTEND_URL}/respond/weekly-revenue/")

    public_case = client.get(f"/public/weekly-revenue/cases/{link['response_token']}").json()
    assert public_case["centre_code"] == code
    assert public_case["pending_incident_count"] == 1
    assert public_case["already_responded"] is False


def test_submitting_via_token_requires_evidence(client):
    admin_token = _admin(client, "wrc_pp_admin2", "wrc_pp_admin2@example.com")
    incident_id, batch_id, code = _make_batch_with_incident("2")
    link = client.post(
        f"/weekly-revenue-closure/batches/{batch_id}/centers/{code}/response-link", headers=_auth(admin_token)
    ).json()

    resp = client.post(
        f"/public/weekly-revenue/cases/{link['response_token']}/respond",
        data={"responder_name": "M", "responder_npid": "NP1", "responder_email": "m@example.com", "reason": "delay explained"},
    )
    assert resp.status_code == 400


def test_submitting_via_token_succeeds_and_shows_up_for_vigilance(client):
    admin_token = _admin(client, "wrc_pp_admin3", "wrc_pp_admin3@example.com")
    incident_id, batch_id, code = _make_batch_with_incident("3")
    link = client.post(
        f"/weekly-revenue-closure/batches/{batch_id}/centers/{code}/response-link", headers=_auth(admin_token)
    ).json()

    resp = client.post(
        f"/public/weekly-revenue/cases/{link['response_token']}/respond",
        data={"responder_name": "M", "responder_npid": "NP1", "responder_email": "m@example.com", "reason": "delay explained"},
        files=_evidence_file(),
    )
    assert resp.status_code == 201

    responses = client.get(f"/weekly-revenue-closure/cases/{link['case_id']}/responses", headers=_auth(admin_token)).json()
    assert len(responses) == 1
    assert responses[0]["reason"] == "delay explained"

    download = client.get(f"/weekly-revenue-closure/case-responses/{responses[0]['id']}/evidence", headers=_auth(admin_token))
    assert download.status_code == 200


def test_open_cases_via_single_shared_link(client):
    admin_token = _admin(client, "wrc_pp_admin4", "wrc_pp_admin4@example.com")
    incident_id, batch_id, code = _make_batch_with_incident("4")

    resp = client.get("/public/weekly-revenue/open-cases", params={"centre_code": code})
    assert resp.status_code == 200
    assert len(resp.json()) == 1
    assert resp.json()[0]["pending_incident_count"] == 1


def test_case_drops_off_open_list_once_reviewed(client):
    admin_token = _admin(client, "wrc_pp_admin5", "wrc_pp_admin5@example.com")
    incident_id, batch_id, code = _make_batch_with_incident("5")

    client.post(f"/weekly-revenue-closure/bills/{incident_id}/review", json={"decision": "considered"}, headers=_auth(admin_token))

    resp = client.get("/public/weekly-revenue/open-cases", params={"centre_code": code})
    assert resp.json() == []


def test_publish_links_mints_a_link_for_every_center_in_batch(client):
    admin_token = _admin(client, "wrc_pp_admin6", "wrc_pp_admin6@example.com")
    _, batch_id, code_a = _make_batch_with_incident("6a")
    db = TestingSessionLocal()
    try:
        user = db.query(User).filter(User.username == "wrc_pp_setup6a").first()
        rule = wrc_svc.get_active_rule(db)
        batch = wrc_svc.get_batch(db, batch_id)
        raw = wrc_svc.RawBillIncidentInput(
            centre_code="PP-WRC-6b", centre_name="PP Test Center 6b",
            incident_date=date(2026, 7, 3), mis_final_remark="daily_report_not_sent",
        )
        wrc_svc.record_bill_incidents(db, batch=batch, raw_incidents=[raw])
    finally:
        db.close()

    result = client.post(f"/weekly-revenue-closure/batches/{batch_id}/publish-links", headers=_auth(admin_token)).json()
    codes = {link["centre_code"] for link in result["links"]}
    assert codes == {code_a, "PP-WRC-6b"}


# ---------------------------------------------------------------------------
# Action Taken


def test_action_taken_only_shows_terminal_decisions(client):
    admin_token = _admin(client, "wrc_pp_admin7", "wrc_pp_admin7@example.com")
    incident_id, batch_id, code = _make_batch_with_incident("7")

    empty = client.get("/weekly-revenue-closure/bills/action-taken", headers=_auth(admin_token)).json()
    assert empty == []

    client.post(f"/weekly-revenue-closure/bills/{incident_id}/review", json={"decision": "not_considered"}, headers=_auth(admin_token))

    action_taken = client.get("/weekly-revenue-closure/bills/action-taken", headers=_auth(admin_token)).json()
    assert len(action_taken) == 1
    assert action_taken[0]["id"] == incident_id
    assert action_taken[0]["considered"] == "not_considered"
    assert action_taken[0]["reviewed_at"] is not None


def test_action_taken_requires_vigilance_role(client):
    assert client.get("/weekly-revenue-closure/bills/action-taken").status_code == 401


# ---------------------------------------------------------------------------
# Centers Activity


def test_activity_logs_opened_and_submitted(client):
    admin_token = _admin(client, "wrc_pp_admin8", "wrc_pp_admin8@example.com")
    incident_id, batch_id, code = _make_batch_with_incident("8")

    client.get("/public/weekly-revenue/open-cases", params={"centre_code": code})
    link = client.post(
        f"/weekly-revenue-closure/batches/{batch_id}/centers/{code}/response-link", headers=_auth(admin_token)
    ).json()
    client.post(
        f"/public/weekly-revenue/cases/{link['response_token']}/respond",
        data={"responder_name": "M", "responder_npid": "NP1", "responder_email": "m@example.com", "reason": "x"},
        files=_evidence_file(),
    )

    activity = client.get("/weekly-revenue-closure/centers-activity", headers=_auth(admin_token)).json()
    matching = [a for a in activity if a["centre_code"] == code]
    event_types = {a["event_type"] for a in matching}
    assert "opened" in event_types
    assert "submitted" in event_types


def test_checking_a_center_with_nothing_open_still_logs_opened(client):
    admin_token = _admin(client, "wrc_pp_admin9", "wrc_pp_admin9@example.com")
    resp = client.get("/public/weekly-revenue/open-cases", params={"centre_code": "NEVER-UPLOADED-WRC"})
    assert resp.json() == []

    activity = client.get("/weekly-revenue-closure/centers-activity", headers=_auth(admin_token)).json()
    matching = [a for a in activity if a["centre_code"] == "NEVER-UPLOADED-WRC"]
    assert len(matching) == 1
    assert matching[0]["case_id"] is None


# ---------------------------------------------------------------------------
# Decision-notification email


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


def _connect_gmail_with_send_scope(client, monkeypatch, token):
    from app.services import email_connection_service

    monkeypatch.setattr(
        email_connection_service.httpx,
        "post",
        lambda *a, **kw: _FakeGoogleResponse(
            {"access_token": "at", "refresh_token": "rt", "expires_in": 3600,
             "scope": "gmail.readonly https://www.googleapis.com/auth/gmail.send openid email"},
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


def _give_center_an_email(centre_code, email):
    db = TestingSessionLocal()
    try:
        dimension = OrgDimension(key=f"wrc-center-{centre_code}", label="Center", sort_order=0)
        db.add(dimension)
        db.commit()
        db.refresh(dimension)
        node = OrgNode(dimension_id=dimension.id, parent_id=None, name=centre_code, external_code=centre_code, manager_email=email)
        db.add(node)
        db.commit()
    finally:
        db.close()


def test_notify_requires_a_decision_first(client):
    admin_token = _admin(client, "wrc_pp_admin10", "wrc_pp_admin10@example.com")
    incident_id, batch_id, code = _make_batch_with_incident("10")

    resp = client.post(f"/weekly-revenue-closure/bills/{incident_id}/notify", json={}, headers=_auth(admin_token))
    assert resp.status_code == 400


def test_notify_reports_no_mailbox_connected(client):
    admin_token = _admin(client, "wrc_pp_admin11", "wrc_pp_admin11@example.com")
    incident_id, batch_id, code = _make_batch_with_incident("11")
    _give_center_an_email(code, "manager11@example.com")
    client.post(f"/weekly-revenue-closure/bills/{incident_id}/review", json={"decision": "considered"}, headers=_auth(admin_token))

    resp = client.post(f"/weekly-revenue-closure/bills/{incident_id}/notify", json={}, headers=_auth(admin_token))
    assert resp.status_code == 200
    body = resp.json()
    assert body["sent"] is False
    assert "connect" in body["reason"].lower()


def test_notify_sends_a_fixed_notice_once_connected(client, monkeypatch):
    admin_token = _admin(client, "wrc_pp_admin12", "wrc_pp_admin12@example.com")
    incident_id, batch_id, code = _make_batch_with_incident("12")
    _give_center_an_email(code, "manager12@example.com")
    _configure_google(monkeypatch)
    _connect_gmail_with_send_scope(client, monkeypatch, admin_token)
    captured = []
    monkeypatch.setattr(
        email_send_service.httpx, "post",
        lambda url, headers=None, json=None, timeout=None: (captured.append({"headers": headers, "json": json}), _FakeGmailSendResponse(200))[1],
    )
    client.post(f"/weekly-revenue-closure/bills/{incident_id}/review", json={"decision": "not_considered"}, headers=_auth(admin_token))

    resp = client.post(f"/weekly-revenue-closure/bills/{incident_id}/notify", json={}, headers=_auth(admin_token))
    assert resp.status_code == 200
    assert resp.json() == {"sent": True, "reason": None}
    assert len(captured) == 1

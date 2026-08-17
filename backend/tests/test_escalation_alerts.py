"""48-hour escalation SMS -- check_and_send_overdue_alerts finds cases
whose response_token_expires_at has passed with no response, and sends an
Admin-targeted SMS via whatever SmsProvider is configured (NullSmsProvider
in tests, which raises NotConfiguredError -- the service is expected to
swallow that and still mark the case as alerted, exactly as it would for a
real provider that's simply not set up)."""

from datetime import date, datetime, timedelta, timezone

from app.models.delayed_cash_billing import DelayedCashCenterPenalty
from app.models.user import User
from app.services import delayed_cash_penalty_service as dcb_svc
from app.services import delayed_cash_response_service as dcb_resp_svc
from app.services import escalation_alert_service
from tests.conftest import TestingSessionLocal


def _register(client, username, email, password="password123", phone_number=None):
    payload = {"username": username, "email": email, "password": password}
    if phone_number is not None:
        payload["phone_number"] = phone_number
    return client.post("/auth/register", json=payload)


def _login(client, username, password="password123"):
    return client.post("/auth/login", json={"username": username, "password": password}).json()["access_token"]


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _admin(client, username, email, phone_number=None):
    _register(client, username, email, phone_number=phone_number)
    db = TestingSessionLocal()
    try:
        db.query(User).filter(User.username == username).first().role = "Admin"
        db.commit()
    finally:
        db.close()
    return _login(client, username)


def _make_overdue_dcb_case():
    db = TestingSessionLocal()
    try:
        from app.models.user import User as UserModel

        setup_user = UserModel(
            username="esc_setup", email="esc_setup@example.com", password_hash="x", role="Admin", is_active=True,
        )
        db.add(setup_user)
        db.commit()
        db.refresh(setup_user)

        rule = dcb_svc.create_rule(db, rule_version="ESC-1", created_by=setup_user)
        dcb_svc.approve_rule(db, rule=rule, approver=setup_user)
        batch = dcb_svc.create_upload_batch(
            db, period_start=date(2026, 7, 1), period_end=date(2026, 7, 31),
            source_filename="esc.xlsx", rule=rule, uploaded_by=setup_user,
        )
        bill_date = date(2026, 7, 1)
        created = bill_date + timedelta(days=2)
        raw = dcb_svc.RawBillInput(
            centre_code="ESC-C1", centre_name="Escalation Test Center",
            sales_bill="ESC-B1", bill_date=bill_date,
            bill_created_time=datetime.combine(created, datetime.min.time(), tzinfo=timezone.utc),
            created_date=created, source_day_difference=2,
        )
        dcb_svc.ingest_bills(db, batch=batch, rule=rule, raw_bills=[raw])
        dcb_svc.compute_center_penalties(db, batch=batch, rule=rule)

        penalty = db.query(DelayedCashCenterPenalty).filter_by(centre_code="ESC-C1").first()
        dcb_resp_svc.generate_response_link_token(db, center_penalty=penalty)
        # Backdate the deadline so it's already overdue.
        penalty.response_token_expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
        db.commit()
        return penalty.id
    finally:
        db.close()


def test_overdue_case_with_no_response_gets_flagged_and_admin_notified(client):
    _admin(client, "esc_admin1", "esc_admin1@example.com", phone_number="+919000000001")
    penalty_id = _make_overdue_dcb_case()

    db = TestingSessionLocal()
    try:
        result = escalation_alert_service.check_and_send_overdue_alerts(db)
    finally:
        db.close()

    assert result.dcb_overdue_found == 1
    assert result.admins_notified == 1
    assert result.sms_attempted == 1
    assert result.sms_provider_not_configured is True  # NullSmsProvider in tests

    db = TestingSessionLocal()
    try:
        penalty = db.query(DelayedCashCenterPenalty).filter_by(id=penalty_id).first()
        assert penalty.escalation_sms_sent_at is not None
    finally:
        db.close()


def test_already_alerted_case_is_not_re_alerted(client):
    _admin(client, "esc_admin2", "esc_admin2@example.com", phone_number="+919000000002")
    _make_overdue_dcb_case()

    db = TestingSessionLocal()
    try:
        first = escalation_alert_service.check_and_send_overdue_alerts(db)
    finally:
        db.close()
    assert first.dcb_overdue_found == 1

    db = TestingSessionLocal()
    try:
        second = escalation_alert_service.check_and_send_overdue_alerts(db)
    finally:
        db.close()
    assert second.dcb_overdue_found == 0  # already flagged, not found again


def test_admin_only_endpoint(client):
    _register(client, "esc_plain", "esc_plain@example.com")
    token = _login(client, "esc_plain")
    resp = client.post("/admin/escalations/check", headers=_auth(token))
    assert resp.status_code == 403


def test_admin_can_trigger_check_via_api(client):
    admin_token = _admin(client, "esc_admin3", "esc_admin3@example.com", phone_number="+919000000003")
    _make_overdue_dcb_case()

    resp = client.post("/admin/escalations/check", headers=_auth(admin_token))
    assert resp.status_code == 200
    body = resp.json()
    assert body["dcb_overdue_found"] == 1

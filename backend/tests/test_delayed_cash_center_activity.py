"""Tests for the Centers Activity trail -- every "opened"/"submitted"
event a center manager's browser generates on the public portal, and
GET /delayed-cash/centers-activity, the internal endpoint Vigilance uses
to read it."""

from datetime import date, datetime, timedelta, timezone
from io import BytesIO

from app.models.user import User
from app.services import delayed_cash_penalty_service as calc_svc
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


def _make_center_penalty(username_suffix, centre_code=None):
    db = TestingSessionLocal()
    try:
        user = db.query(User).filter(User.username == f"dcbact_setup{username_suffix}").first()
        if user is None:
            import bcrypt

            user = User(
                username=f"dcbact_setup{username_suffix}",
                email=f"dcbact_setup{username_suffix}@example.com",
                password_hash=bcrypt.hashpw(b"password123", bcrypt.gensalt()).decode(),
                role="Admin",
                is_active=True,
            )
            db.add(user)
            db.commit()
            db.refresh(user)

        rule = calc_svc.create_rule(db, rule_version=f"DCB-ACT-{username_suffix}", created_by=user)
        calc_svc.approve_rule(db, rule=rule, approver=user)
        batch = calc_svc.create_upload_batch(
            db, period_start=date(2026, 7, 1), period_end=date(2026, 7, 31),
            source_filename="act-test.xlsx", rule=rule, uploaded_by=user,
        )
        bill_date = date(2026, 7, 1)
        created = bill_date + timedelta(days=2)
        code = centre_code or f"ACT-C{username_suffix}"
        raw = calc_svc.RawBillInput(
            centre_code=code, centre_name="Activity Test Center",
            sales_bill=f"ACT-{username_suffix}-1", bill_date=bill_date,
            bill_created_time=datetime.combine(created, datetime.min.time(), tzinfo=timezone.utc),
            created_date=created, source_day_difference=2,
        )
        calc_svc.ingest_bills(db, batch=batch, rule=rule, raw_bills=[raw])
        center_penalties = calc_svc.compute_center_penalties(db, batch=batch, rule=rule)
        return center_penalties[0].id, batch.id, code
    finally:
        db.close()


def _evidence_file(name="proof.pdf", content=b"%PDF-1.4 fake evidence content"):
    return {"evidence": (name, BytesIO(content), "application/pdf")}


def test_opening_a_case_by_token_logs_an_opened_event(client):
    admin_token = _admin(client, "dcbact_admin1", "dcbact_admin1@example.com")
    cp_id, batch_id, code = _make_center_penalty("1")
    link = client.post(f"/delayed-cash/center-penalties/{cp_id}/response-link", headers=_auth(admin_token)).json()

    client.get(f"/public/delayed-cash/cases/{link['response_token']}")

    activity = client.get("/delayed-cash/centers-activity", headers=_auth(admin_token)).json()
    matching = [a for a in activity if a["centre_code"] == code]
    assert len(matching) == 1
    assert matching[0]["event_type"] == "opened"
    assert matching[0]["center_penalty_id"] == cp_id


def test_opening_via_the_single_shared_link_logs_an_opened_event_per_case(client):
    admin_token = _admin(client, "dcbact_admin2", "dcbact_admin2@example.com")
    cp_id, batch_id, code = _make_center_penalty("2")

    resp = client.get("/public/delayed-cash/open-cases", params={"centre_code": code})
    assert resp.status_code == 200
    assert len(resp.json()) == 1

    activity = client.get("/delayed-cash/centers-activity", headers=_auth(admin_token)).json()
    matching = [a for a in activity if a["centre_code"] == code]
    assert len(matching) == 1
    assert matching[0]["event_type"] == "opened"


def test_checking_a_center_with_nothing_open_still_logs_opened_with_no_case(client):
    admin_token = _admin(client, "dcbact_admin3", "dcbact_admin3@example.com")

    resp = client.get("/public/delayed-cash/open-cases", params={"centre_code": "NEVER-UPLOADED-CODE"})
    assert resp.status_code == 200
    assert resp.json() == []

    activity = client.get("/delayed-cash/centers-activity", headers=_auth(admin_token)).json()
    matching = [a for a in activity if a["centre_code"] == "NEVER-UPLOADED-CODE"]
    assert len(matching) == 1
    assert matching[0]["event_type"] == "opened"
    assert matching[0]["center_penalty_id"] is None


def test_submitting_via_token_logs_a_submitted_event(client):
    admin_token = _admin(client, "dcbact_admin4", "dcbact_admin4@example.com")
    cp_id, batch_id, code = _make_center_penalty("4")
    link = client.post(f"/delayed-cash/center-penalties/{cp_id}/response-link", headers=_auth(admin_token)).json()

    client.post(
        f"/public/delayed-cash/cases/{link['response_token']}/respond",
        data={"responder_name": "M", "responder_npid": "NP1", "responder_email": "m@example.com", "reason": "delay explained"},
        files=_evidence_file(),
    )

    activity = client.get("/delayed-cash/centers-activity", headers=_auth(admin_token)).json()
    submitted = [a for a in activity if a["centre_code"] == code and a["event_type"] == "submitted"]
    assert len(submitted) == 1


def test_submitting_via_single_link_by_id_logs_a_submitted_event(client):
    admin_token = _admin(client, "dcbact_admin5", "dcbact_admin5@example.com")
    cp_id, batch_id, code = _make_center_penalty("5")

    client.post(
        f"/public/delayed-cash/cases/by-id/{cp_id}/respond",
        data={"responder_name": "M", "responder_npid": "NP1", "responder_email": "m@example.com", "reason": "delay explained"},
        files=_evidence_file(),
    )

    activity = client.get("/delayed-cash/centers-activity", headers=_auth(admin_token)).json()
    submitted = [a for a in activity if a["centre_code"] == code and a["event_type"] == "submitted"]
    assert len(submitted) == 1


def test_activity_can_be_scoped_to_a_batch(client):
    admin_token = _admin(client, "dcbact_admin6", "dcbact_admin6@example.com")
    cp_id_a, batch_id_a, code_a = _make_center_penalty("6a")
    cp_id_b, batch_id_b, code_b = _make_center_penalty("6b")

    client.get(f"/public/delayed-cash/open-cases", params={"centre_code": code_a})
    client.get(f"/public/delayed-cash/open-cases", params={"centre_code": code_b})

    scoped = client.get(
        "/delayed-cash/centers-activity", params={"batch_id": batch_id_a}, headers=_auth(admin_token)
    ).json()
    scoped_codes = {a["centre_code"] for a in scoped}
    assert code_a in scoped_codes
    assert code_b not in scoped_codes


def test_activity_is_newest_first(client):
    admin_token = _admin(client, "dcbact_admin7", "dcbact_admin7@example.com")
    cp_id, batch_id, code = _make_center_penalty("7")

    client.get(f"/public/delayed-cash/open-cases", params={"centre_code": code})
    client.post(
        f"/public/delayed-cash/cases/by-id/{cp_id}/respond",
        data={"responder_name": "M", "responder_npid": "NP1", "responder_email": "m@example.com", "reason": "delay explained"},
        files=_evidence_file(),
    )

    activity = client.get("/delayed-cash/centers-activity", headers=_auth(admin_token)).json()
    matching = [a for a in activity if a["centre_code"] == code]
    assert matching[0]["event_type"] == "submitted"  # most recent first
    assert matching[1]["event_type"] == "opened"


def test_centers_activity_requires_vigilance_role(client):
    assert client.get("/delayed-cash/centers-activity").status_code == 401

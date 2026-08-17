"""Tests for GET /delayed-cash/center-penalties/{id}/responses and
GET /delayed-cash/case-responses/{id}/evidence -- the endpoints Vigilance
uses to read a center's submitted remark (and download their proof) from
the review queue, before deciding considered/not_considered/etc."""

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


def _make_center_penalty(username_suffix):
    db = TestingSessionLocal()
    try:
        user = db.query(User).filter(User.username == f"dcbcr_setup{username_suffix}").first()
        if user is None:
            import bcrypt

            user = User(
                username=f"dcbcr_setup{username_suffix}",
                email=f"dcbcr_setup{username_suffix}@example.com",
                password_hash=bcrypt.hashpw(b"password123", bcrypt.gensalt()).decode(),
                role="Admin",
                is_active=True,
            )
            db.add(user)
            db.commit()
            db.refresh(user)

        rule = calc_svc.create_rule(db, rule_version=f"DCB-CR-{username_suffix}", created_by=user)
        calc_svc.approve_rule(db, rule=rule, approver=user)
        batch = calc_svc.create_upload_batch(
            db, period_start=date(2026, 7, 1), period_end=date(2026, 7, 31),
            source_filename="cr-test.xlsx", rule=rule, uploaded_by=user,
        )
        bill_date = date(2026, 7, 1)
        created = bill_date + timedelta(days=2)
        raw = calc_svc.RawBillInput(
            centre_code=f"CR-C{username_suffix}", centre_name="Case Response Test Center",
            sales_bill=f"CR-{username_suffix}-1", bill_date=bill_date,
            bill_created_time=datetime.combine(created, datetime.min.time(), tzinfo=timezone.utc),
            created_date=created, source_day_difference=2,
        )
        calc_svc.ingest_bills(db, batch=batch, rule=rule, raw_bills=[raw])
        center_penalties = calc_svc.compute_center_penalties(db, batch=batch, rule=rule)
        return center_penalties[0].id
    finally:
        db.close()


def _evidence_file(name="proof.pdf", content=b"%PDF-1.4 fake evidence content"):
    return {"evidence": (name, BytesIO(content), "application/pdf")}


def test_no_responses_yet_returns_empty_list(client):
    admin_token = _admin(client, "dcbcr_admin1", "dcbcr_admin1@example.com")
    cp_id = _make_center_penalty("1")

    resp = client.get(f"/delayed-cash/center-penalties/{cp_id}/responses", headers=_auth(admin_token))
    assert resp.status_code == 200
    assert resp.json() == []


def test_submitted_response_is_listed_with_remark_text(client):
    admin_token = _admin(client, "dcbcr_admin2", "dcbcr_admin2@example.com")
    cp_id = _make_center_penalty("2")
    link = client.post(f"/delayed-cash/center-penalties/{cp_id}/response-link", headers=_auth(admin_token)).json()

    submit = client.post(
        f"/public/delayed-cash/cases/{link['response_token']}/respond",
        data={
            "responder_name": "Case Response Manager",
            "responder_npid": "NP99001",
            "responder_email": "manager@example.com",
            "reason": "Dialysis session ran over, proof attached",
        },
        files=_evidence_file(),
    )
    assert submit.status_code == 201

    listing = client.get(f"/delayed-cash/center-penalties/{cp_id}/responses", headers=_auth(admin_token))
    assert listing.status_code == 200
    body = listing.json()
    assert len(body) == 1
    assert body[0]["responder_name"] == "Case Response Manager"
    assert body[0]["reason"] == "Dialysis session ran over, proof attached"
    assert body[0]["evidence_original_filename"] == "proof.pdf"
    response_id = body[0]["id"]

    download = client.get(f"/delayed-cash/case-responses/{response_id}/evidence", headers=_auth(admin_token))
    assert download.status_code == 200
    assert download.content == b"%PDF-1.4 fake evidence content"
    assert "proof.pdf" in download.headers["content-disposition"]


def test_multiple_submissions_are_all_listed_oldest_to_newest(client):
    admin_token = _admin(client, "dcbcr_admin3", "dcbcr_admin3@example.com")
    cp_id = _make_center_penalty("3")
    link = client.post(f"/delayed-cash/center-penalties/{cp_id}/response-link", headers=_auth(admin_token)).json()

    client.post(
        f"/public/delayed-cash/cases/{link['response_token']}/respond",
        data={"responder_name": "First", "responder_npid": "NP1", "responder_email": "a@example.com", "reason": "first pass"},
        files=_evidence_file("first.pdf"),
    )
    client.post(
        f"/public/delayed-cash/cases/{link['response_token']}/respond",
        data={"responder_name": "First", "responder_npid": "NP1", "responder_email": "a@example.com", "reason": "follow-up with more detail"},
        files=_evidence_file("second.pdf"),
    )

    listing = client.get(f"/delayed-cash/center-penalties/{cp_id}/responses", headers=_auth(admin_token)).json()
    assert len(listing) == 2
    assert listing[0]["reason"] == "first pass"
    assert listing[1]["reason"] == "follow-up with more detail"


def test_responses_and_evidence_download_require_vigilance_role(client):
    cp_id = _make_center_penalty("4")
    assert client.get(f"/delayed-cash/center-penalties/{cp_id}/responses").status_code == 401
    assert client.get("/delayed-cash/case-responses/1/evidence").status_code == 401


def test_unknown_response_evidence_404s(client):
    admin_token = _admin(client, "dcbcr_admin5", "dcbcr_admin5@example.com")
    resp = client.get("/delayed-cash/case-responses/999999/evidence", headers=_auth(admin_token))
    assert resp.status_code == 404

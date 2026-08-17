"""Tests for the single shared response link -- one fixed public URL for
every center, instead of a per-case token:
  GET  /public/delayed-cash/open-cases?centre_code=...
  POST /public/delayed-cash/cases/by-id/{center_penalty_id}/respond

The per-case token flow (test_delayed_cash_response_portal.py) is untouched
and kept working in parallel -- these tests only cover the new path.
"""

from datetime import date, datetime, timedelta, timezone
from io import BytesIO

from app.models.delayed_cash_billing import DelayedCashBill
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


def _get_or_create_user(db, username):
    user = db.query(User).filter(User.username == username).first()
    if user is None:
        import bcrypt

        user = User(
            username=username,
            email=f"{username}@example.com",
            password_hash=bcrypt.hashpw(b"password123", bcrypt.gensalt()).decode(),
            role="Admin",
            is_active=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    return user


def _make_case(username_suffix, centre_code, day_diffs=(1,)):
    db = TestingSessionLocal()
    try:
        user = _get_or_create_user(db, f"dcbol_setup{username_suffix}")
        rule = calc_svc.create_rule(db, rule_version=f"DCB-OL-{username_suffix}", created_by=user)
        calc_svc.approve_rule(db, rule=rule, approver=user)
        batch = calc_svc.create_upload_batch(
            db, period_start=date(2026, 7, 1), period_end=date(2026, 7, 31),
            source_filename="ol-test.xlsx", rule=rule, uploaded_by=user,
        )
        bill_date = date(2026, 7, 1)
        raw_bills = []
        for i, dd in enumerate(day_diffs):
            created = bill_date + timedelta(days=dd)
            raw_bills.append(
                calc_svc.RawBillInput(
                    centre_code=centre_code, centre_name="Open Link Test Center",
                    sales_bill=f"OL-{username_suffix}-{i}", bill_date=bill_date,
                    bill_created_time=datetime.combine(created, datetime.min.time(), tzinfo=timezone.utc),
                    created_date=created, source_day_difference=dd,
                )
            )
        calc_svc.ingest_bills(db, batch=batch, rule=rule, raw_bills=raw_bills)
        cp_id = calc_svc.compute_center_penalties(db, batch=batch, rule=rule)[0].id
        return cp_id, rule.id, batch.id
    finally:
        db.close()


def _evidence_file():
    return {"evidence": ("proof.pdf", BytesIO(b"%PDF-1.4 fake"), "application/pdf")}


# ---------------------------------------------------------------------------
# open-cases listing
# ---------------------------------------------------------------------------


def test_open_cases_returns_case_for_matching_centre_code(client):
    cp_id, _, _ = _make_case("1", "OL-C1")

    resp = client.get("/public/delayed-cash/open-cases", params={"centre_code": "OL-C1"})
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["id"] == cp_id
    assert body[0]["centre_code"] == "OL-C1"
    assert body[0]["already_responded"] is False


def test_open_cases_empty_list_for_unknown_centre_code(client):
    resp = client.get("/public/delayed-cash/open-cases", params={"centre_code": "NO-SUCH-CENTER"})
    assert resp.status_code == 200
    assert resp.json() == []


def test_open_cases_requires_no_authentication(client):
    _make_case("2", "OL-C2")
    resp = client.get("/public/delayed-cash/open-cases", params={"centre_code": "OL-C2"})
    assert resp.status_code == 200  # no Authorization header sent, still works


def test_case_disappears_from_open_list_once_validated(client):
    cp_id, rule_id, _ = _make_case("3", "OL-C3")

    still_open = client.get("/public/delayed-cash/open-cases", params={"centre_code": "OL-C3"}).json()
    assert any(c["id"] == cp_id for c in still_open)

    db = TestingSessionLocal()
    try:
        from app.models.delayed_cash_billing import DelayedCashCenterPenalty, DelayedCashPenaltyRule

        cp = db.query(DelayedCashCenterPenalty).filter(DelayedCashCenterPenalty.id == cp_id).first()
        rule = db.query(DelayedCashPenaltyRule).filter(DelayedCashPenaltyRule.id == rule_id).first()
        bills = db.query(DelayedCashBill).filter(DelayedCashBill.batch_id == cp.batch_id).all()
        for b in bills:
            b.considered = "not_considered"
        db.commit()
        calc_svc.recompute_validated_penalty(db, center_penalty=cp, rule=rule)
    finally:
        db.close()

    now_open = client.get("/public/delayed-cash/open-cases", params={"centre_code": "OL-C3"}).json()
    assert not any(c["id"] == cp_id for c in now_open)


# ---------------------------------------------------------------------------
# respond-by-id
# ---------------------------------------------------------------------------


def test_respond_by_id_succeeds_and_matches_token_flow(client):
    cp_id, _, _ = _make_case("4", "OL-C4")

    resp = client.post(
        f"/public/delayed-cash/cases/by-id/{cp_id}/respond",
        data={
            "responder_name": "Open Link Manager",
            "responder_npid": "NP-OL-4",
            "responder_email": "ol4@example.com",
            "reason": "Responding via the single shared link",
        },
        files=_evidence_file(),
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["responder_name"] == "Open Link Manager"
    assert body["responder_email"] == "ol4@example.com"

    # already_responded now flips true, visible from the open-cases list too.
    open_cases = client.get("/public/delayed-cash/open-cases", params={"centre_code": "OL-C4"}).json()
    assert open_cases[0]["already_responded"] is True


def test_respond_by_id_still_requires_evidence(client):
    cp_id, _, _ = _make_case("5", "OL-C5")
    resp = client.post(
        f"/public/delayed-cash/cases/by-id/{cp_id}/respond",
        data={
            "responder_name": "X", "responder_npid": "Y", "responder_email": "x@example.com",
            "reason": "No evidence attached",
        },
    )
    assert resp.status_code == 400


def test_respond_by_id_unknown_case_404s(client):
    resp = client.post(
        "/public/delayed-cash/cases/by-id/999999/respond",
        data={
            "responder_name": "X", "responder_npid": "Y", "responder_email": "x@example.com",
            "reason": "Case doesn't exist",
        },
        files=_evidence_file(),
    )
    assert resp.status_code == 404


def test_respond_by_id_records_center_mismatch_same_as_token_flow(client):
    cp_id, _, _ = _make_case("6", "OL-C6")
    resp = client.post(
        f"/public/delayed-cash/cases/by-id/{cp_id}/respond",
        data={
            "responder_name": "X", "responder_npid": "Y", "responder_email": "x@example.com",
            "reason": "On behalf of a different center",
            "selected_center_code": "OTHER-CODE",
            "selected_center_name": "Other Center",
        },
        files=_evidence_file(),
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["selected_center_code"] == "OTHER-CODE"

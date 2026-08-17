"""Delayed Cash Billing: DELETE /delayed-cash/batches/{batch_id}.

Covers RBAC gating and cascade correctness -- every bill, center penalty,
case response (+ its evidence file on disk), and activity row tied to the
deleted batch must actually be gone afterwards, and an unrelated batch's
rows must be untouched. See delayed_cash_penalty_service.delete_batch for
why this can't just rely on ORM cascade (DelayedCashCenterActivity has no
cascade configured from DelayedCashCenterPenalty)."""

from datetime import date, datetime, timedelta, timezone
from io import BytesIO

from app.models.delayed_cash_billing import (
    DelayedCashBill,
    DelayedCashCaseResponse,
    DelayedCashCenterActivity,
    DelayedCashCenterPenalty,
    DelayedCashUploadBatch,
)
from app.models.user import User
from app.services import delayed_cash_penalty_service as calc_svc
from app.services import storage_service
from tests.conftest import TestingSessionLocal


def _register(client, username, email, password="password123"):
    return client.post("/auth/register", json={"username": username, "email": email, "password": password})


def _login(client, username, password="password123"):
    return client.post("/auth/login", json={"username": username, "password": password}).json()["access_token"]


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _admin(client, username="dcbd_admin", email="dcbd_admin@example.com"):
    _register(client, username, email)
    db = TestingSessionLocal()
    try:
        db.query(User).filter(User.username == username).first().role = "Admin"
        db.commit()
    finally:
        db.close()
    return _login(client, username)


def _make_batch_with_case(username_suffix):
    """Builds one real batch, with one bill/center-penalty, through the
    actual calculator pipeline -- returns (batch_id, center_penalty_id)."""
    db = TestingSessionLocal()
    try:
        import bcrypt

        user = User(
            username=f"dcbd_setup{username_suffix}",
            email=f"dcbd_setup{username_suffix}@example.com",
            password_hash=bcrypt.hashpw(b"password123", bcrypt.gensalt()).decode(),
            role="Admin",
            is_active=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        rule = calc_svc.create_rule(db, rule_version=f"DCB-DEL-{username_suffix}", created_by=user)
        calc_svc.approve_rule(db, rule=rule, approver=user)
        batch = calc_svc.create_upload_batch(
            db, period_start=date(2026, 7, 1), period_end=date(2026, 7, 31),
            source_filename=f"del-test-{username_suffix}.xlsx", rule=rule, uploaded_by=user,
        )
        bill_date = date(2026, 7, 1)
        created = bill_date + timedelta(days=2)
        raw = calc_svc.RawBillInput(
            centre_code=f"DEL-C{username_suffix}", centre_name="Delete Test Center",
            sales_bill=f"DEL-{username_suffix}-1", bill_date=bill_date,
            bill_created_time=datetime.combine(created, datetime.min.time(), tzinfo=timezone.utc),
            created_date=created, source_day_difference=2,
        )
        calc_svc.ingest_bills(db, batch=batch, rule=rule, raw_bills=[raw])
        center_penalties = calc_svc.compute_center_penalties(db, batch=batch, rule=rule)
        return batch.id, center_penalties[0].id
    finally:
        db.close()


def _evidence_file(name="proof.pdf", content=b"%PDF-1.4 fake evidence content"):
    return {"evidence": (name, BytesIO(content), "application/pdf")}


def test_non_vigilance_role_cannot_delete_batch(client):
    _admin(client)
    batch_id, _ = _make_batch_with_case("1")
    _register(client, "dcbd_plain", "dcbd_plain@example.com")
    db = TestingSessionLocal()
    try:
        db.query(User).filter(User.username == "dcbd_plain").first().role = "Center Manager"
        db.commit()
    finally:
        db.close()
    token = _login(client, "dcbd_plain")

    resp = client.delete(f"/delayed-cash/batches/{batch_id}", headers=_auth(token))
    assert resp.status_code == 403

    db = TestingSessionLocal()
    try:
        assert db.query(DelayedCashUploadBatch).filter(DelayedCashUploadBatch.id == batch_id).first() is not None
    finally:
        db.close()


def test_delete_batch_removes_everything_including_evidence_file(client):
    admin_token = _admin(client, "dcbd_admin2", "dcbd_admin2@example.com")
    batch_id, cp_id = _make_batch_with_case("2")

    link = client.post(f"/delayed-cash/center-penalties/{cp_id}/response-link", headers=_auth(admin_token)).json()
    submit = client.post(
        f"/public/delayed-cash/cases/{link['response_token']}/respond",
        data={
            "responder_name": "Test Manager",
            "responder_npid": "NP12345",
            "responder_email": "manager@example.com",
            "reason": "Session ran late, proof attached",
        },
        files=_evidence_file(),
    )
    assert submit.status_code == 201

    db = TestingSessionLocal()
    try:
        response_row = db.query(DelayedCashCaseResponse).filter(
            DelayedCashCaseResponse.center_penalty_id == cp_id
        ).first()
        assert response_row is not None
        evidence_path = storage_service.absolute_path_for(response_row.evidence_storage_path)
        assert __import__("os").path.exists(evidence_path)

        # "opened" activity was logged by the GET above.
        activity_count = db.query(DelayedCashCenterActivity).filter(
            DelayedCashCenterActivity.center_penalty_id == cp_id
        ).count()
        assert activity_count >= 1
    finally:
        db.close()

    resp = client.delete(f"/delayed-cash/batches/{batch_id}", headers=_auth(admin_token))
    assert resp.status_code == 204

    db = TestingSessionLocal()
    try:
        assert db.query(DelayedCashUploadBatch).filter(DelayedCashUploadBatch.id == batch_id).first() is None
        assert db.query(DelayedCashBill).filter(DelayedCashBill.batch_id == batch_id).count() == 0
        assert db.query(DelayedCashCenterPenalty).filter(DelayedCashCenterPenalty.batch_id == batch_id).count() == 0
        assert db.query(DelayedCashCaseResponse).filter(
            DelayedCashCaseResponse.center_penalty_id == cp_id
        ).count() == 0
        assert db.query(DelayedCashCenterActivity).filter(
            DelayedCashCenterActivity.center_penalty_id == cp_id
        ).count() == 0
    finally:
        db.close()

    assert not __import__("os").path.exists(evidence_path)


def test_delete_batch_leaves_other_batches_untouched(client):
    admin_token = _admin(client, "dcbd_admin3", "dcbd_admin3@example.com")
    batch_id_a, _ = _make_batch_with_case("3a")
    batch_id_b, _ = _make_batch_with_case("3b")

    resp = client.delete(f"/delayed-cash/batches/{batch_id_a}", headers=_auth(admin_token))
    assert resp.status_code == 204

    db = TestingSessionLocal()
    try:
        assert db.query(DelayedCashUploadBatch).filter(DelayedCashUploadBatch.id == batch_id_a).first() is None
        assert db.query(DelayedCashUploadBatch).filter(DelayedCashUploadBatch.id == batch_id_b).first() is not None
        assert db.query(DelayedCashBill).filter(DelayedCashBill.batch_id == batch_id_b).count() == 1
        assert db.query(DelayedCashCenterPenalty).filter(DelayedCashCenterPenalty.batch_id == batch_id_b).count() == 1
    finally:
        db.close()


def test_delete_nonexistent_batch_returns_404(client):
    admin_token = _admin(client, "dcbd_admin4", "dcbd_admin4@example.com")
    resp = client.delete("/delayed-cash/batches/999999", headers=_auth(admin_token))
    assert resp.status_code == 404

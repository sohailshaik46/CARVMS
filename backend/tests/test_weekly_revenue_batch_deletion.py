"""Weekly Revenue Closure: DELETE /weekly-revenue-closure/batches/{batch_id}.

Mirrors test_delayed_cash_batch_deletion.py, but WRC has one extra wrinkle:
WeeklyRevenueCenterCase has NO cascade at all from WeeklyRevenueClosureBatch
(the case handle is deliberately decoupled from the penalty computation's
lifecycle -- see the model's own docstring), so this suite specifically
proves cases/responses/evidence/activity are cleaned up even though nothing
in the ORM would do it automatically."""

import os
from datetime import date
from io import BytesIO

from app.models.user import User
from app.models.weekly_revenue_closure import (
    WeeklyRevenueBillIncident,
    WeeklyRevenueCaseResponse,
    WeeklyRevenueCenterActivity,
    WeeklyRevenueCenterCase,
    WeeklyRevenueClosureBatch,
)
from app.services import storage_service
from app.services import weekly_revenue_closure_service as wrc_svc
from tests.conftest import TestingSessionLocal


def _register(client, username, email, password="password123"):
    return client.post("/auth/register", json={"username": username, "email": email, "password": password})


def _login(client, username, password="password123"):
    return client.post("/auth/login", json={"username": username, "password": password}).json()["access_token"]


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _admin(client, username="wrcd_admin", email="wrcd_admin@example.com"):
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


def _make_batch_with_incident(suffix: str):
    _make_user(f"wrcd_setup{suffix}")
    db = TestingSessionLocal()
    try:
        user = db.query(User).filter(User.username == f"wrcd_setup{suffix}").first()
        rule = wrc_svc.create_rule(db, rule_version=f"DEL-WRC-{suffix}", created_by=user)
        wrc_svc.approve_rule(db, rule=rule, approver=user)
        batch = wrc_svc.create_batch(
            db, period_start=date(2026, 7, 1), period_end=date(2026, 7, 7),
            week_label=f"Week DEL {suffix}", rule=rule, created_by=user,
        )
        code = f"DEL-WRC-{suffix}"
        raw = wrc_svc.RawBillIncidentInput(
            centre_code=code, centre_name=f"Delete Test Center {suffix}",
            incident_date=date(2026, 7, 2), mis_final_remark="bill_pending",
        )
        wrc_svc.record_bill_incidents(db, batch=batch, raw_incidents=[raw])
        return batch.id, code
    finally:
        db.close()


def _evidence_file(name="proof.pdf", content=b"%PDF-1.4 fake evidence content"):
    return {"evidence": (name, BytesIO(content), "application/pdf")}


def test_non_vigilance_role_cannot_delete_batch(client):
    _admin(client)
    batch_id, _ = _make_batch_with_incident("1")
    _register(client, "wrcd_plain", "wrcd_plain@example.com")
    db = TestingSessionLocal()
    try:
        db.query(User).filter(User.username == "wrcd_plain").first().role = "Center Manager"
        db.commit()
    finally:
        db.close()
    token = _login(client, "wrcd_plain")

    resp = client.delete(f"/weekly-revenue-closure/batches/{batch_id}", headers=_auth(token))
    assert resp.status_code == 403

    db = TestingSessionLocal()
    try:
        assert db.query(WeeklyRevenueClosureBatch).filter(WeeklyRevenueClosureBatch.id == batch_id).first() is not None
    finally:
        db.close()


def test_delete_batch_removes_everything_including_case_and_evidence_file(client):
    admin_token = _admin(client, "wrcd_admin2", "wrcd_admin2@example.com")
    batch_id, code = _make_batch_with_incident("2")

    link = client.post(
        f"/weekly-revenue-closure/batches/{batch_id}/centers/{code}/response-link", headers=_auth(admin_token)
    ).json()
    case_id = link["case_id"]

    submit = client.post(
        f"/public/weekly-revenue/cases/{link['response_token']}/respond",
        data={"responder_name": "M", "responder_npid": "NP1", "responder_email": "m@example.com", "reason": "delay explained"},
        files=_evidence_file(),
    )
    assert submit.status_code == 201

    db = TestingSessionLocal()
    try:
        assert db.query(WeeklyRevenueCenterCase).filter(WeeklyRevenueCenterCase.id == case_id).first() is not None
        response_row = db.query(WeeklyRevenueCaseResponse).filter(
            WeeklyRevenueCaseResponse.case_id == case_id
        ).first()
        assert response_row is not None
        evidence_path = storage_service.absolute_path_for(response_row.evidence_storage_path)
        assert os.path.exists(evidence_path)

        activity_count = db.query(WeeklyRevenueCenterActivity).filter(
            WeeklyRevenueCenterActivity.case_id == case_id
        ).count()
        assert activity_count >= 1
    finally:
        db.close()

    resp = client.delete(f"/weekly-revenue-closure/batches/{batch_id}", headers=_auth(admin_token))
    assert resp.status_code == 204

    db = TestingSessionLocal()
    try:
        assert db.query(WeeklyRevenueClosureBatch).filter(WeeklyRevenueClosureBatch.id == batch_id).first() is None
        assert db.query(WeeklyRevenueBillIncident).filter(WeeklyRevenueBillIncident.batch_id == batch_id).count() == 0
        assert db.query(WeeklyRevenueCenterCase).filter(WeeklyRevenueCenterCase.id == case_id).first() is None
        assert db.query(WeeklyRevenueCaseResponse).filter(WeeklyRevenueCaseResponse.case_id == case_id).count() == 0
        assert db.query(WeeklyRevenueCenterActivity).filter(WeeklyRevenueCenterActivity.case_id == case_id).count() == 0
    finally:
        db.close()

    assert not os.path.exists(evidence_path)


def test_delete_batch_leaves_other_batches_untouched(client):
    admin_token = _admin(client, "wrcd_admin3", "wrcd_admin3@example.com")
    batch_id_a, _ = _make_batch_with_incident("3a")
    batch_id_b, _ = _make_batch_with_incident("3b")

    resp = client.delete(f"/weekly-revenue-closure/batches/{batch_id_a}", headers=_auth(admin_token))
    assert resp.status_code == 204

    db = TestingSessionLocal()
    try:
        assert db.query(WeeklyRevenueClosureBatch).filter(WeeklyRevenueClosureBatch.id == batch_id_a).first() is None
        assert db.query(WeeklyRevenueClosureBatch).filter(WeeklyRevenueClosureBatch.id == batch_id_b).first() is not None
        assert db.query(WeeklyRevenueBillIncident).filter(WeeklyRevenueBillIncident.batch_id == batch_id_b).count() == 1
    finally:
        db.close()


def test_delete_nonexistent_batch_returns_404(client):
    admin_token = _admin(client, "wrcd_admin4", "wrcd_admin4@example.com")
    resp = client.delete("/weekly-revenue-closure/batches/999999", headers=_auth(admin_token))
    assert resp.status_code == 404

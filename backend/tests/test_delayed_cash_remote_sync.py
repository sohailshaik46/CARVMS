"""Tests for delayed_cash_remote_sync_service -- the manual, admin-
triggered push/pull for Delayed Cash Billing data. Mirrors
test_org_master_remote_sync.py's approach: two independent in-memory
SQLite databases standing in for "local" and "remote" (never the real
Render Postgres), plus a couple of API-level RBAC/not-configured tests.
"""

from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.database import Base
from app.models.delayed_cash_billing import (
    DelayedCashBill,
    DelayedCashCenterPenalty,
    DelayedCashPenaltyRule,
    DelayedCashUploadBatch,
)
from app.models.user import User
from app.services import delayed_cash_remote_sync_service as sync_service
from tests.conftest import TestingSessionLocal


def _new_sqlite_db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    return Session()


def _make_user(db, username: str, role: str = "Admin") -> User:
    """Idempotent -- several tests seed a batch's uploader AND separately
    reference "the admin running the sync" by the same username, so this
    returns the existing row rather than erroring on a duplicate."""
    existing = db.query(User).filter(User.username == username).first()
    if existing is not None:
        return existing
    user = User(username=username, email=f"{username}@example.com", password_hash="x", role=role, is_active=True)
    db.add(user)
    db.flush()
    return user


def _seed_batch_with_one_bill(db, *, uploader_username: str):
    uploader = _make_user(db, uploader_username)
    rule = DelayedCashPenaltyRule(
        rule_version="TEST-RULE-1", rate_per_day=Decimal("100"), monthly_cap_percentage=Decimal("0.0625"),
        status="approved", created_by_id=uploader.id,
    )
    db.add(rule)
    db.flush()
    batch = DelayedCashUploadBatch(
        period_start=date(2026, 7, 1), period_end=date(2026, 7, 31), source_filename="week.xlsx",
        rule_id=rule.id, status="uploaded", uploaded_by_id=uploader.id,
    )
    db.add(batch)
    db.flush()
    bill = DelayedCashBill(
        batch_id=batch.id, centre_code="900-X-C", centre_name="Test Center", sales_bill="SB-1",
        bill_date=date(2026, 7, 1), bill_created_time=datetime(2026, 7, 2, 9, 0, tzinfo=timezone.utc),
        created_date=date(2026, 7, 2), source_day_difference=1, calculated_day_difference=1,
        calculated_penalty=Decimal("100"),
    )
    db.add(bill)
    cp = DelayedCashCenterPenalty(
        batch_id=batch.id, centre_code="900-X-C", centre_name="Test Center", total_bills=1,
        calculated_penalty=Decimal("100"), penalty_status="published",
    )
    db.add(cp)
    db.commit()
    return rule, batch, bill, cp


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


# ---------------------------------------------------------------------------
# Dry run + create
# ---------------------------------------------------------------------------


def test_dry_run_reports_correct_counts_and_writes_nothing():
    source = _new_sqlite_db()
    target = _new_sqlite_db()
    admin = _make_user(target, "target_admin")
    target.commit()
    _seed_batch_with_one_bill(source, uploader_username="local_uploader")

    report = sync_service.sync_delayed_cash(source, target, commit=False, current_admin_target_id=admin.id)

    assert report.committed is False
    assert report.rules_created == 1
    assert report.batches_created == 1
    assert report.bills_created == 1
    assert report.center_penalties_created == 1
    assert target.query(DelayedCashUploadBatch).count() == 0  # genuinely nothing written


def test_commit_creates_everything_and_falls_back_uploader_attribution():
    source = _new_sqlite_db()
    target = _new_sqlite_db()
    admin = _make_user(target, "syncing_admin")
    target.commit()
    # The source's uploader ("local_uploader") has no account on target at
    # all -- attribution must fall back to the admin running the sync,
    # never leave the NOT NULL uploaded_by_id unset.
    _seed_batch_with_one_bill(source, uploader_username="local_uploader")

    report = sync_service.sync_delayed_cash(source, target, commit=True, current_admin_target_id=admin.id)

    assert report.committed is True
    assert report.rules_created == 1
    assert report.batches_created == 1
    assert report.bills_created == 1
    assert report.center_penalties_created == 1

    target_batch = target.query(DelayedCashUploadBatch).first()
    assert target_batch.uploaded_by_id == admin.id
    assert target_batch.source_filename == "week.xlsx"
    target_bill = target.query(DelayedCashBill).first()
    assert target_bill.sales_bill == "SB-1"
    assert target_bill.batch_id == target_batch.id


# ---------------------------------------------------------------------------
# Matched by natural key, never duplicated
# ---------------------------------------------------------------------------


def test_existing_bill_is_updated_not_duplicated_even_with_different_ids():
    source = _new_sqlite_db()
    target = _new_sqlite_db()
    admin_source = _make_user(source, "admin_a")
    admin_target = _make_user(target, "admin_b")
    source.commit()
    target.commit()

    _seed_batch_with_one_bill(source, uploader_username="admin_a")
    _seed_batch_with_one_bill(target, uploader_username="admin_b")  # same real batch, unrelated ids

    # Recompute this bill's penalty differently on the source side --
    # simulates a genuine post-review recompute.
    source_bill = source.query(DelayedCashBill).first()
    source_bill.calculated_penalty = 200
    source.commit()

    report = sync_service.sync_delayed_cash(source, target, commit=True, current_admin_target_id=admin_target.id)

    assert report.bills_created == 0  # matched by (batch key, sales_bill), not duplicated
    assert report.bills_updated == 1
    assert target.query(DelayedCashBill).count() == 1
    assert target.query(DelayedCashBill).first().calculated_penalty == 200


# ---------------------------------------------------------------------------
# Never overwrite a real response token / decision with a blank or a
# different one
# ---------------------------------------------------------------------------


def test_response_token_already_set_on_target_is_never_replaced():
    source = _new_sqlite_db()
    target = _new_sqlite_db()
    admin_s = _make_user(source, "admin_s")
    admin_t = _make_user(target, "admin_t")
    source.commit()
    target.commit()

    _seed_batch_with_one_bill(source, uploader_username="admin_s")
    _, _, _, target_cp = _seed_batch_with_one_bill(target, uploader_username="admin_t")
    target_cp.response_token = "already-emailed-token"
    target.commit()

    # Source also has a token minted (independently) for the same case.
    source_cp = source.query(DelayedCashCenterPenalty).first()
    source_cp.response_token = "a-completely-different-token"
    source.commit()

    sync_service.sync_delayed_cash(source, target, commit=True, current_admin_target_id=admin_t.id)

    # Target's real, already-emailed token must survive untouched.
    assert target.query(DelayedCashCenterPenalty).first().response_token == "already-emailed-token"


def test_response_token_is_filled_in_when_target_had_none():
    source = _new_sqlite_db()
    target = _new_sqlite_db()
    admin_s = _make_user(source, "admin_s2")
    admin_t = _make_user(target, "admin_t2")
    source.commit()
    target.commit()

    _seed_batch_with_one_bill(target, uploader_username="admin_t2")  # target has no token yet
    _, _, _, source_cp = _seed_batch_with_one_bill(source, uploader_username="admin_s2")
    source_cp.response_token = "freshly-minted-token"
    source.commit()

    sync_service.sync_delayed_cash(source, target, commit=True, current_admin_target_id=admin_t.id)

    assert target.query(DelayedCashCenterPenalty).first().response_token == "freshly-minted-token"


def test_review_decision_already_made_on_target_is_never_overwritten():
    source = _new_sqlite_db()
    target = _new_sqlite_db()
    admin_s = _make_user(source, "admin_s3")
    admin_t = _make_user(target, "admin_t3")
    source.commit()
    target.commit()

    _, _, target_bill, _ = _seed_batch_with_one_bill(target, uploader_username="admin_t3")
    target_bill.considered = "not_considered"
    target.commit()

    _, _, source_bill, _ = _seed_batch_with_one_bill(source, uploader_username="admin_s3")
    source_bill.considered = "considered"  # a DIFFERENT, conflicting verdict
    source.commit()

    sync_service.sync_delayed_cash(source, target, commit=True, current_admin_target_id=admin_t.id)

    assert target.query(DelayedCashBill).first().considered == "not_considered"


# ---------------------------------------------------------------------------
# Forward-only batch status
# ---------------------------------------------------------------------------


def test_batch_status_never_regresses():
    source = _new_sqlite_db()
    target = _new_sqlite_db()
    admin_s = _make_user(source, "admin_s4")
    admin_t = _make_user(target, "admin_t4")
    source.commit()
    target.commit()

    _, target_batch, _, _ = _seed_batch_with_one_bill(target, uploader_username="admin_t4")
    target_batch.status = "closed"
    target.commit()

    _seed_batch_with_one_bill(source, uploader_username="admin_s4")  # source still "uploaded"

    sync_service.sync_delayed_cash(source, target, commit=True, current_admin_target_id=admin_t.id)

    assert target.query(DelayedCashUploadBatch).first().status == "closed"  # not regressed to "uploaded"


# ---------------------------------------------------------------------------
# Never deletes
# ---------------------------------------------------------------------------


def test_a_bill_only_present_in_target_is_never_deleted():
    source = _new_sqlite_db()
    target = _new_sqlite_db()
    admin_s = _make_user(source, "admin_s5")
    admin_t = _make_user(target, "admin_t5")
    source.commit()
    target.commit()

    _seed_batch_with_one_bill(source, uploader_username="admin_s5")
    _, target_batch, _, _ = _seed_batch_with_one_bill(target, uploader_username="admin_t5")
    extra_bill = DelayedCashBill(
        batch_id=target_batch.id, centre_code="901-Y-C", centre_name="Extra", sales_bill="EXTRA-1",
        bill_date=date(2026, 7, 5), bill_created_time=datetime(2026, 7, 6, 9, 0, tzinfo=timezone.utc),
        created_date=date(2026, 7, 6), source_day_difference=1, calculated_day_difference=1,
        calculated_penalty=Decimal("100"),
    )
    target.add(extra_bill)
    target.commit()

    sync_service.sync_delayed_cash(source, target, commit=True, current_admin_target_id=admin_t.id)

    assert target.query(DelayedCashBill).filter(DelayedCashBill.sales_bill == "EXTRA-1").count() == 1


# ---------------------------------------------------------------------------
# API layer: RBAC + not-configured guard
# ---------------------------------------------------------------------------


def test_remote_sync_endpoints_require_admin_not_just_vigilance(client):
    _register(client, "dcbrs_auditor", "dcbrs_auditor@example.com")
    db = TestingSessionLocal()
    try:
        db.query(User).filter(User.username == "dcbrs_auditor").first().role = "Auditor"
        db.commit()
    finally:
        db.close()
    token = _login(client, "dcbrs_auditor")
    resp = client.post("/delayed-cash/sync/remote/push", headers=_auth(token))
    assert resp.status_code == 403


def test_remote_sync_returns_clear_400_when_not_configured(client, monkeypatch):
    monkeypatch.setattr("app.services.org_master_remote_sync_service.settings.REMOTE_DATABASE_URL", None)
    admin_token = _admin(client, "dcbrs_admin_noconfig", "dcbrs_admin_noconfig@example.com")
    resp = client.post("/delayed-cash/sync/remote/push", headers=_auth(admin_token))
    assert resp.status_code == 400
    assert "not set" in resp.json()["detail"].lower()

    resp = client.post("/delayed-cash/sync/remote/pull", headers=_auth(admin_token))
    assert resp.status_code == 400

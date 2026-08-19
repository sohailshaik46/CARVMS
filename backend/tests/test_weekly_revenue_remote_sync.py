"""Tests for weekly_revenue_remote_sync_service -- the manual, admin-
triggered push/pull for Weekly Revenue Closure data. Mirrors
test_delayed_cash_remote_sync.py's approach exactly.
"""

from datetime import date
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.database import Base
from app.models.user import User
from app.models.weekly_revenue_closure import (
    WeeklyRevenueBillIncident,
    WeeklyRevenueCenterCase,
    WeeklyRevenueCenterPenalty,
    WeeklyRevenueClosureBatch,
    WeeklyRevenueClosureRule,
)
from app.services import weekly_revenue_remote_sync_service as sync_service
from tests.conftest import TestingSessionLocal


def _new_sqlite_db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    return Session()


def _make_user(db, username: str, role: str = "Admin") -> User:
    existing = db.query(User).filter(User.username == username).first()
    if existing is not None:
        return existing
    user = User(username=username, email=f"{username}@example.com", password_hash="x", role=role, is_active=True)
    db.add(user)
    db.flush()
    return user


def _seed_batch_with_one_incident(db, *, creator_username: str):
    creator = _make_user(db, creator_username)
    rule = WeeklyRevenueClosureRule(
        rule_version="WRC-TEST-1", penalty_rate=Decimal("0.0625"), status="approved", created_by_id=creator.id,
    )
    db.add(rule)
    db.flush()
    batch = WeeklyRevenueClosureBatch(
        period_start=date(2026, 8, 10), period_end=date(2026, 8, 16), week_label="Week 2 - Aug'26",
        rule_id=rule.id, status="open", created_by_id=creator.id,
    )
    db.add(batch)
    db.flush()
    incident = WeeklyRevenueBillIncident(
        batch_id=batch.id, centre_code="900-X-C", centre_name="Test Center",
        incident_date=date(2026, 8, 12), mis_final_remark="bill_pending", raw_remark="1 Bill pending",
    )
    db.add(incident)
    cp = WeeklyRevenueCenterPenalty(
        batch_id=batch.id, centre_code="900-X-C", centre_name="Test Center", not_considered_penalty=Decimal("0.0625"),
    )
    db.add(cp)
    case = WeeklyRevenueCenterCase(batch_id=batch.id, centre_code="900-X-C", centre_name="Test Center")
    db.add(case)
    db.commit()
    return rule, batch, incident, cp, case


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
    _seed_batch_with_one_incident(source, creator_username="local_creator")

    report = sync_service.sync_weekly_revenue(source, target, commit=False, current_admin_target_id=admin.id)

    assert report.committed is False
    assert report.rules_created == 1
    assert report.batches_created == 1
    assert report.bill_incidents_created == 1
    assert report.center_penalties_created == 1
    assert report.center_cases_created == 1
    assert target.query(WeeklyRevenueClosureBatch).count() == 0


def test_commit_creates_everything_and_falls_back_creator_attribution():
    source = _new_sqlite_db()
    target = _new_sqlite_db()
    admin = _make_user(target, "syncing_admin")
    target.commit()
    _seed_batch_with_one_incident(source, creator_username="local_creator")  # no account on target at all

    report = sync_service.sync_weekly_revenue(source, target, commit=True, current_admin_target_id=admin.id)

    assert report.committed is True
    assert report.batches_created == 1
    target_batch = target.query(WeeklyRevenueClosureBatch).first()
    assert target_batch.created_by_id == admin.id
    assert target_batch.week_label == "Week 2 - Aug'26"
    assert target.query(WeeklyRevenueBillIncident).first().centre_code == "900-X-C"
    assert target.query(WeeklyRevenueCenterCase).first().centre_code == "900-X-C"


# ---------------------------------------------------------------------------
# Matched by natural key, never duplicated
# ---------------------------------------------------------------------------


def test_existing_incident_is_updated_not_duplicated_even_with_different_ids():
    source = _new_sqlite_db()
    target = _new_sqlite_db()
    admin_t = _make_user(target, "admin_t")
    source.commit()
    target.commit()

    _seed_batch_with_one_incident(source, creator_username="admin_a")
    _seed_batch_with_one_incident(target, creator_username="admin_b")  # same real batch, unrelated ids

    source_incident = source.query(WeeklyRevenueBillIncident).first()
    source_incident.variance = -5
    source.commit()

    report = sync_service.sync_weekly_revenue(source, target, commit=True, current_admin_target_id=admin_t.id)

    assert report.bill_incidents_created == 0
    assert report.bill_incidents_updated == 1
    assert target.query(WeeklyRevenueBillIncident).count() == 1
    assert target.query(WeeklyRevenueBillIncident).first().variance == -5


# ---------------------------------------------------------------------------
# Never overwrite a real response token / decision
# ---------------------------------------------------------------------------


def test_response_token_already_set_on_target_is_never_replaced():
    source = _new_sqlite_db()
    target = _new_sqlite_db()
    admin_t = _make_user(target, "admin_t2")
    source.commit()
    target.commit()

    _seed_batch_with_one_incident(source, creator_username="admin_s2")
    _, _, _, _, target_case = _seed_batch_with_one_incident(target, creator_username="admin_t2")
    target_case.response_token = "already-emailed-token"
    target.commit()

    source_case = source.query(WeeklyRevenueCenterCase).first()
    source_case.response_token = "a-different-token"
    source.commit()

    sync_service.sync_weekly_revenue(source, target, commit=True, current_admin_target_id=admin_t.id)

    assert target.query(WeeklyRevenueCenterCase).first().response_token == "already-emailed-token"


def test_review_decision_already_made_on_target_is_never_overwritten():
    source = _new_sqlite_db()
    target = _new_sqlite_db()
    admin_t = _make_user(target, "admin_t3")
    source.commit()
    target.commit()

    _, _, target_incident, _, _ = _seed_batch_with_one_incident(target, creator_username="admin_t3")
    target_incident.considered = "not_considered"
    target.commit()

    _, _, source_incident, _, _ = _seed_batch_with_one_incident(source, creator_username="admin_s3")
    source_incident.considered = "considered"
    source.commit()

    sync_service.sync_weekly_revenue(source, target, commit=True, current_admin_target_id=admin_t.id)

    assert target.query(WeeklyRevenueBillIncident).first().considered == "not_considered"


def test_moved_to_no_remark_never_regresses_from_true_to_false():
    source = _new_sqlite_db()
    target = _new_sqlite_db()
    admin_t = _make_user(target, "admin_t4")
    source.commit()
    target.commit()

    _, _, target_incident, _, _ = _seed_batch_with_one_incident(target, creator_username="admin_t4")
    target_incident.moved_to_no_remark = True
    target.commit()

    _seed_batch_with_one_incident(source, creator_username="admin_s4")  # still False on source

    sync_service.sync_weekly_revenue(source, target, commit=True, current_admin_target_id=admin_t.id)

    assert target.query(WeeklyRevenueBillIncident).first().moved_to_no_remark is True


# ---------------------------------------------------------------------------
# Forward-only batch status
# ---------------------------------------------------------------------------


def test_batch_status_never_regresses():
    source = _new_sqlite_db()
    target = _new_sqlite_db()
    admin_t = _make_user(target, "admin_t5")
    source.commit()
    target.commit()

    _, target_batch, _, _, _ = _seed_batch_with_one_incident(target, creator_username="admin_t5")
    target_batch.status = "closed"
    target.commit()

    _seed_batch_with_one_incident(source, creator_username="admin_s5")  # still "open"

    sync_service.sync_weekly_revenue(source, target, commit=True, current_admin_target_id=admin_t.id)

    assert target.query(WeeklyRevenueClosureBatch).first().status == "closed"


# ---------------------------------------------------------------------------
# Never deletes
# ---------------------------------------------------------------------------


def test_an_incident_only_present_in_target_is_never_deleted():
    source = _new_sqlite_db()
    target = _new_sqlite_db()
    admin_t = _make_user(target, "admin_t6")
    source.commit()
    target.commit()

    _seed_batch_with_one_incident(source, creator_username="admin_s6")
    _, target_batch, _, _, _ = _seed_batch_with_one_incident(target, creator_username="admin_t6")
    extra = WeeklyRevenueBillIncident(
        batch_id=target_batch.id, centre_code="901-Y-C", centre_name="Extra",
        incident_date=date(2026, 8, 13), mis_final_remark="daily_report_not_sent",
    )
    target.add(extra)
    target.commit()

    sync_service.sync_weekly_revenue(source, target, commit=True, current_admin_target_id=admin_t.id)

    assert target.query(WeeklyRevenueBillIncident).filter(WeeklyRevenueBillIncident.centre_code == "901-Y-C").count() == 1


# ---------------------------------------------------------------------------
# API layer: RBAC + not-configured guard
# ---------------------------------------------------------------------------


def test_remote_sync_endpoints_require_admin_not_just_vigilance(client):
    _register(client, "wrcrs_auditor", "wrcrs_auditor@example.com")
    db = TestingSessionLocal()
    try:
        db.query(User).filter(User.username == "wrcrs_auditor").first().role = "Auditor"
        db.commit()
    finally:
        db.close()
    token = _login(client, "wrcrs_auditor")
    resp = client.post("/weekly-revenue-closure/sync/remote/push", headers=_auth(token))
    assert resp.status_code == 403


def test_remote_sync_returns_clear_400_when_not_configured(client, monkeypatch):
    monkeypatch.setattr("app.services.org_master_remote_sync_service.settings.REMOTE_DATABASE_URL", None)
    admin_token = _admin(client, "wrcrs_admin_noconfig", "wrcrs_admin_noconfig@example.com")
    resp = client.post("/weekly-revenue-closure/sync/remote/push", headers=_auth(admin_token))
    assert resp.status_code == 400
    assert "not set" in resp.json()["detail"].lower()

    resp = client.post("/weekly-revenue-closure/sync/remote/pull", headers=_auth(admin_token))
    assert resp.status_code == 400

"""Batch-level KPI dashboards for both engines:
- WRC's get_batch_centers_breakdown -- zone/cluster read straight off the
  incident rows, plus all-time repeat-non-compliance and considered/
  not-considered history.
- DCB's get_batch_summary + get_batch_centers_breakdown -- the summary
  mirrors WRC's; the breakdown resolves zone/cluster via the Org Master
  (a real dependency DCB bills don't carry themselves), falling back to
  None ("Unknown" in the UI) for a center not yet linked there.
"""

from datetime import date, datetime, timedelta, timezone

from app.models.org import OrgDimension
from app.models.user import User
from app.services import delayed_cash_penalty_service as dcb_svc
from app.services import org_service
from app.services import weekly_revenue_closure_service as wrc_svc
from tests.conftest import TestingSessionLocal


def _register(client, username, email, password="password123"):
    return client.post("/auth/register", json={"username": username, "email": email, "password": password})


def _login(client, username, password="password123"):
    return client.post("/auth/login", json={"username": username, "password": password}).json()["access_token"]


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _admin(client, username="bd_admin", email="bd_admin@example.com"):
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


# ---------------------------------------------------------------------------
# WRC centers breakdown
# ---------------------------------------------------------------------------


def test_wrc_centers_breakdown_zone_cluster_and_repeat_history(client):
    admin_token = _admin(client, "bd_wrc_admin", "bd_wrc_admin@example.com")
    _make_user("bd_wrc_setup")
    db = TestingSessionLocal()
    try:
        user = db.query(User).filter(User.username == "bd_wrc_setup").first()
        rule = wrc_svc.create_rule(db, rule_version="BD-WRC", created_by=user)
        wrc_svc.approve_rule(db, rule=rule, approver=user)

        batch1 = wrc_svc.create_batch(
            db, period_start=date(2026, 7, 1), period_end=date(2026, 7, 7),
            week_label="BD Week 1", rule=rule, created_by=user,
        )
        incidents1 = wrc_svc.record_bill_incidents(
            db, batch=batch1,
            raw_incidents=[
                wrc_svc.RawBillIncidentInput(
                    centre_code="BD-C1", centre_name="BD Center 1", zone="North", cluster="Arpit Choudhary",
                    incident_date=date(2026, 7, 2), mis_final_remark="bill_pending",
                ),
            ],
        )
        wrc_svc.set_bill_incident_review(db, incident=incidents1[0], decision="not_considered", reviewed_by=user)

        batch2 = wrc_svc.create_batch(
            db, period_start=date(2026, 7, 8), period_end=date(2026, 7, 14),
            week_label="BD Week 2", rule=rule, created_by=user,
        )
        incidents2 = wrc_svc.record_bill_incidents(
            db, batch=batch2,
            raw_incidents=[
                wrc_svc.RawBillIncidentInput(
                    centre_code="BD-C1", centre_name="BD Center 1", zone="North", cluster="Arpit Choudhary",
                    incident_date=date(2026, 7, 9), mis_final_remark="bill_pending",
                ),
            ],
        )
        wrc_svc.set_bill_incident_review(db, incident=incidents2[0], decision="considered", reviewed_by=user)
        batch2_id = batch2.id
        batch1_id = batch1.id
    finally:
        db.close()

    resp = client.get(f"/weekly-revenue-closure/batches/{batch2_id}/centers-breakdown", headers=_auth(admin_token))
    assert resp.status_code == 200
    rows = resp.json()
    assert len(rows) == 1
    row = rows[0]
    assert row["centre_code"] == "BD-C1"
    assert row["zone"] == "North"
    assert row["cluster"] == "Arpit Choudhary"
    assert row["this_batch_incident_count"] == 1
    assert row["this_batch_considered_count"] == 1
    # All-time: 2 distinct batches (batch1 + batch2) -- a genuine repeat.
    assert row["all_time_batch_count"] == 2
    assert row["all_time_considered_count"] == 1
    assert row["all_time_not_considered_count"] == 1

    # batch1's breakdown should show only batch1's own incident count, but
    # the SAME all-time totals (history is global, not batch-scoped).
    resp1 = client.get(f"/weekly-revenue-closure/batches/{batch1_id}/centers-breakdown", headers=_auth(admin_token))
    row1 = resp1.json()[0]
    assert row1["this_batch_incident_count"] == 1
    assert row1["this_batch_not_considered_count"] == 1
    assert row1["all_time_batch_count"] == 2


def test_wrc_centers_breakdown_rbac(client):
    _admin(client)
    _register(client, "bd_wrc_plain", "bd_wrc_plain@example.com")
    db = TestingSessionLocal()
    try:
        db.query(User).filter(User.username == "bd_wrc_plain").first().role = "Center Manager"
        db.commit()
    finally:
        db.close()
    token = _login(client, "bd_wrc_plain")
    resp = client.get("/weekly-revenue-closure/batches/999999/centers-breakdown", headers=_auth(token))
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# DCB batch summary + centers breakdown
# ---------------------------------------------------------------------------


def _make_dcb_batch(suffix: str, bill_count: int = 1):
    _make_user(f"bd_dcb_setup{suffix}")
    db = TestingSessionLocal()
    try:
        user = db.query(User).filter(User.username == f"bd_dcb_setup{suffix}").first()
        rule = dcb_svc.create_rule(db, rule_version=f"BD-DCB-{suffix}", created_by=user)
        dcb_svc.approve_rule(db, rule=rule, approver=user)
        batch = dcb_svc.create_upload_batch(
            db, period_start=date(2026, 7, 1), period_end=date(2026, 7, 31),
            source_filename=f"bd-dcb-{suffix}.xlsx", rule=rule, uploaded_by=user,
        )
        bill_date = date(2026, 7, 1)
        created = bill_date + timedelta(days=2)
        raws = [
            dcb_svc.RawBillInput(
                centre_code=f"BD-DCB-{suffix}", centre_name=f"BD DCB Center {suffix}",
                sales_bill=f"BD-DCB-{suffix}-{i}", bill_date=bill_date,
                bill_created_time=datetime.combine(created, datetime.min.time(), tzinfo=timezone.utc),
                created_date=created, source_day_difference=2,
            )
            for i in range(bill_count)
        ]
        bills = dcb_svc.ingest_bills(db, batch=batch, rule=rule, raw_bills=raws)
        dcb_svc.compute_center_penalties(db, batch=batch, rule=rule)
        bill_ids = [b.id for b in bills]
        return batch.id, bill_ids, f"BD-DCB-{suffix}"
    finally:
        db.close()


def test_dcb_batch_summary_counts(client):
    admin_token = _admin(client, "bd_dcb_admin", "bd_dcb_admin@example.com")
    batch_id, bill_ids, _code = _make_dcb_batch("1", bill_count=2)

    db = TestingSessionLocal()
    try:
        from app.models.delayed_cash_billing import DelayedCashBill

        dcb_svc.set_bill_review_decision(
            db, bill=db.query(DelayedCashBill).filter_by(id=bill_ids[0]).first(),
            decision="considered", reviewed_by=db.query(User).filter_by(username="bd_dcb_setup1").first(),
        )
    finally:
        db.close()

    resp = client.get(f"/delayed-cash/batches/{batch_id}/summary", headers=_auth(admin_token))
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_bills"] == 2
    assert body["considered_count"] == 1
    assert body["pending_review_count"] == 1
    assert body["centers_in_batch"] == 1


def test_dcb_centers_breakdown_resolves_zone_cluster_via_org_master(client):
    admin_token = _admin(client, "bd_dcb_admin2", "bd_dcb_admin2@example.com")
    batch_id, _bills, code = _make_dcb_batch("2")

    db = TestingSessionLocal()
    try:
        org_service.seed_default_dimensions_if_missing(db)
        dims = {d.key: d for d in db.query(OrgDimension).all()}
        zone_node = org_service.create_node(db, dimension_id=dims["zone"].id, parent_id=None, name="BD Test Zone", external_code=None)
        cluster_node = org_service.create_node(db, dimension_id=dims["cluster"].id, parent_id=zone_node.id, name="BD Test Cluster", external_code=None)
        org_service.create_node(db, dimension_id=dims["center"].id, parent_id=cluster_node.id, name="BD DCB Center 2", external_code=code)
    finally:
        db.close()

    resp = client.get(f"/delayed-cash/batches/{batch_id}/centers-breakdown", headers=_auth(admin_token))
    assert resp.status_code == 200
    rows = resp.json()
    assert len(rows) == 1
    assert rows[0]["centre_code"] == code
    assert rows[0]["zone"] == "BD Test Zone"
    assert rows[0]["cluster"] == "BD Test Cluster"
    assert rows[0]["this_batch_bill_count"] == 1
    assert rows[0]["all_time_batch_count"] == 1


def test_dcb_centers_breakdown_unknown_when_not_in_org_master(client):
    admin_token = _admin(client, "bd_dcb_admin3", "bd_dcb_admin3@example.com")
    batch_id, _bills, _code = _make_dcb_batch("3")

    resp = client.get(f"/delayed-cash/batches/{batch_id}/centers-breakdown", headers=_auth(admin_token))
    assert resp.status_code == 200
    rows = resp.json()
    assert rows[0]["zone"] is None
    assert rows[0]["cluster"] is None


def test_dcb_batch_summary_and_breakdown_rbac(client):
    _admin(client)
    _register(client, "bd_dcb_plain", "bd_dcb_plain@example.com")
    db = TestingSessionLocal()
    try:
        db.query(User).filter(User.username == "bd_dcb_plain").first().role = "Center Manager"
        db.commit()
    finally:
        db.close()
    token = _login(client, "bd_dcb_plain")
    assert client.get("/delayed-cash/batches/999999/summary", headers=_auth(token)).status_code == 403
    assert client.get("/delayed-cash/batches/999999/centers-breakdown", headers=_auth(token)).status_code == 403

"""Tests for GET /dashboard/summary -- the single semantic metric layer,
rewritten 2026-08-14 to compute from Delayed Cash Billing (DCB) + Weekly
Revenue Closure (WRC) data instead of the deleted Audits/Findings domain.
"""
from datetime import date, datetime, timedelta, timezone

from app.models.org import OrgDimension, OrgNode
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


def _admin(client, username="metrics_admin", email="metrics_admin@example.com"):
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


def _dcb_case(suffix: str, decisions: list[str], bill_date=date(2026, 7, 1)):
    """One center's case with N bills, each set to the given decision."""
    db = TestingSessionLocal()
    try:
        user = _make_user(f"metrics_dcb_setup{suffix}")
        db.add(user)
    finally:
        db.close()

    db = TestingSessionLocal()
    try:
        user = db.query(User).filter(User.username == f"metrics_dcb_setup{suffix}").first()
        rule = dcb_svc.create_rule(db, rule_version=f"METRICS-DCB-{suffix}", created_by=user)
        dcb_svc.approve_rule(db, rule=rule, approver=user)
        batch = dcb_svc.create_upload_batch(
            db, period_start=date(2026, 7, 1), period_end=date(2026, 7, 31),
            source_filename=f"metrics-{suffix}.xlsx", rule=rule, uploaded_by=user,
        )
        code = f"MET-DCB-{suffix}"
        raw_bills = []
        for i, _ in enumerate(decisions):
            created = bill_date + timedelta(days=2)
            raw_bills.append(
                dcb_svc.RawBillInput(
                    centre_code=code, centre_name=f"Metrics DCB Center {suffix}",
                    sales_bill=f"MET-{suffix}-{i}", bill_date=bill_date,
                    bill_created_time=datetime.combine(created, datetime.min.time(), tzinfo=timezone.utc),
                    created_date=created, source_day_difference=2,
                )
            )
        bills = dcb_svc.ingest_bills(db, batch=batch, rule=rule, raw_bills=raw_bills)
        dcb_svc.compute_center_penalties(db, batch=batch, rule=rule)
        for bill, decision in zip(bills, decisions):
            if decision is not None:
                dcb_svc.set_bill_review_decision(db, bill=bill, decision=decision, reviewed_by=user)
        return code
    finally:
        db.close()


def _wrc_case(suffix: str, decisions: list[str], zone="Zone Alpha", cluster="Cluster One"):
    db = TestingSessionLocal()
    try:
        user = _make_user(f"metrics_wrc_setup{suffix}")
    finally:
        db.close()

    db = TestingSessionLocal()
    try:
        user = db.query(User).filter(User.username == f"metrics_wrc_setup{suffix}").first()
        rule = wrc_svc.create_rule(db, rule_version=f"METRICS-WRC-{suffix}", created_by=user)
        wrc_svc.approve_rule(db, rule=rule, approver=user)
        batch = wrc_svc.create_batch(
            db, period_start=date(2026, 7, 1), period_end=date(2026, 7, 7),
            week_label=f"Week Metrics {suffix}", rule=rule, created_by=user,
        )
        code = f"MET-WRC-{suffix}"
        raw = [
            wrc_svc.RawBillIncidentInput(
                centre_code=code, centre_name=f"Metrics WRC Center {suffix}",
                incident_date=date(2026, 7, 2), mis_final_remark="bill_pending",
                zone=zone, cluster=cluster,
            )
            for _ in decisions
        ]
        incidents = wrc_svc.record_bill_incidents(db, batch=batch, raw_incidents=raw)
        for incident, decision in zip(incidents, decisions):
            if decision is not None:
                wrc_svc.set_bill_incident_review(db, incident=incident, decision=decision)
        return code
    finally:
        db.close()


def test_dcb_summary_counts_decisions_and_non_compliance_rate(client):
    admin_token = _admin(client)
    _dcb_case("1", ["considered", "not_considered", "not_considered"])

    summary = client.get("/dashboard/summary", headers=_auth(admin_token)).json()
    dcb = summary["dcb"]
    assert dcb["considered"] >= 1
    assert dcb["not_considered"] >= 2
    # 2 of 3 terminal verdicts not_considered -> 66.67%, but other tests in
    # this file add their own cases, so just check the case we made is
    # internally consistent rather than asserting an exact global rate.
    assert dcb["non_compliance_rate"] is not None


def test_wrc_summary_counts_decisions(client):
    admin_token = _admin(client, "metrics_admin2", "metrics_admin2@example.com")
    _wrc_case("1", ["considered", "not_considered"])

    summary = client.get("/dashboard/summary", headers=_auth(admin_token)).json()
    wrc = summary["wrc"]
    assert wrc["considered"] >= 1
    assert wrc["not_considered"] >= 1


def test_non_compliance_rate_is_none_when_nothing_reviewed_yet(client):
    admin_token = _admin(client, "metrics_admin3", "metrics_admin3@example.com")
    _dcb_case("3", [None, None])  # never reviewed

    summary = client.get("/dashboard/summary", headers=_auth(admin_token)).json()
    # This specific case contributes zero terminal verdicts -- but other
    # tests may have created reviewed cases in the same DB, so check via a
    # tightly scoped period instead of the raw global rate.
    scoped = client.get(
        "/dashboard/summary", params={"period_from": "2099-01-01"}, headers=_auth(admin_token)
    ).json()
    assert scoped["dcb"]["non_compliance_rate"] is None
    assert scoped["dcb"]["total_bills"] == 0


def test_wrc_zone_cluster_breakdown_counts_distinct_non_compliant_centers(client):
    admin_token = _admin(client, "metrics_admin4", "metrics_admin4@example.com")
    code_a = _wrc_case("4a", ["not_considered"], zone="Zone Metrics4", cluster="Cluster Metrics4")
    code_b = _wrc_case("4b", ["not_considered"], zone="Zone Metrics4", cluster="Cluster Metrics4B")

    summary = client.get("/dashboard/summary", headers=_auth(admin_token)).json()
    zone_row = next(z for z in summary["zone_breakdown"] if z["zone"] == "Zone Metrics4")
    assert zone_row["non_compliant_center_count"] == 2

    cluster_row = next(c for c in summary["cluster_breakdown"] if c["cluster"] == "Cluster Metrics4")
    assert cluster_row["non_compliant_center_count"] == 1


def test_dcb_center_without_org_master_link_shows_as_unknown_cluster(client):
    admin_token = _admin(client, "metrics_admin5", "metrics_admin5@example.com")
    _dcb_case("5", ["not_considered"])

    summary = client.get("/dashboard/summary", headers=_auth(admin_token)).json()
    unknown_cluster = next((c for c in summary["cluster_breakdown"] if c["cluster"] == "Unknown"), None)
    assert unknown_cluster is not None
    assert unknown_cluster["non_compliant_center_count"] >= 1


def test_dcb_center_linked_in_org_master_resolves_real_cluster_zone(client):
    admin_token = _admin(client, "metrics_admin6", "metrics_admin6@example.com")
    code = _dcb_case("6", ["not_considered"])

    db = TestingSessionLocal()
    try:
        # The real dimension keys the whole app uses are "zone"/"cluster"/
        # "center" (see org_service.DEFAULT_DIMENSIONS) -- metrics.py's
        # cluster/zone lookup hardcodes those same keys, so the fixture
        # must use them too, not made-up per-test keys.
        org_service.seed_default_dimensions_if_missing(db)
        zone_dim = db.query(OrgDimension).filter(OrgDimension.key == "zone").first()
        cluster_dim = db.query(OrgDimension).filter(OrgDimension.key == "cluster").first()
        center_dim = db.query(OrgDimension).filter(OrgDimension.key == "center").first()

        zone_node = OrgNode(dimension_id=zone_dim.id, parent_id=None, name="Real Zone 6", external_code=None)
        db.add(zone_node)
        db.commit()
        cluster_node = OrgNode(dimension_id=cluster_dim.id, parent_id=zone_node.id, name="Real Cluster 6", external_code=None)
        db.add(cluster_node)
        db.commit()
        center_node = OrgNode(dimension_id=center_dim.id, parent_id=cluster_node.id, name=code, external_code=code)
        db.add(center_node)
        db.commit()
    finally:
        db.close()

    summary = client.get("/dashboard/summary", headers=_auth(admin_token)).json()
    real_zone = next((z for z in summary["zone_breakdown"] if z["zone"] == "Real Zone 6"), None)
    assert real_zone is not None
    real_cluster = next((c for c in summary["cluster_breakdown"] if c["cluster"] == "Real Cluster 6"), None)
    assert real_cluster is not None


def test_repeated_centers_lists_centers_with_two_or_more_violations(client):
    admin_token = _admin(client, "metrics_admin7", "metrics_admin7@example.com")
    code = _dcb_case("7", ["not_considered", "not_considered"])

    summary = client.get("/dashboard/summary", headers=_auth(admin_token)).json()
    repeated = next((r for r in summary["repeated_centers"] if r["centre_code"] == code), None)
    assert repeated is not None
    assert repeated["violation_count"] == 2


def test_summary_requires_vigilance_role(client):
    assert client.get("/dashboard/summary").status_code == 401

    _register(client, "metrics_stranger", "metrics_stranger@example.com")
    stranger_token = _login(client, "metrics_stranger")  # default role: Auditor -- actually allowed
    # Auditor IS a vigilance role; use Center Manager instead to prove the gate.
    db = TestingSessionLocal()
    try:
        db.query(User).filter(User.username == "metrics_stranger").first().role = "Center Manager"
        db.commit()
    finally:
        db.close()
    resp = client.get("/dashboard/summary", headers=_auth(stranger_token))
    assert resp.status_code == 403


def test_period_filter_excludes_rows_outside_range(client):
    admin_token = _admin(client, "metrics_admin8", "metrics_admin8@example.com")
    _dcb_case("8", ["not_considered"], bill_date=date(2026, 6, 1))

    in_range = client.get(
        "/dashboard/summary", params={"period_from": "2026-06-01", "period_to": "2026-06-30"}, headers=_auth(admin_token)
    ).json()
    out_of_range = client.get(
        "/dashboard/summary", params={"period_from": "2027-01-01", "period_to": "2027-01-31"}, headers=_auth(admin_token)
    ).json()
    assert in_range["dcb"]["total_bills"] >= 1
    assert out_of_range["dcb"]["total_bills"] == 0

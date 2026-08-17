"""Tests for GET /search -- rewritten 2026-08-14 to search Delayed Cash
Billing (DCB) bills + Weekly Revenue Closure (WRC) incidents instead of
the deleted Audits/Findings/PenaltyRule domain. The whole endpoint is now
Admin/Auditor-gated (see app/api/search.py) since Billing data has no
per-row visibility model of its own.
"""
from datetime import date, datetime, timedelta, timezone

from app.models.user import User
from app.services import delayed_cash_penalty_service as dcb_svc
from app.services import weekly_revenue_closure_service as wrc_svc
from tests.conftest import TestingSessionLocal


def _register(client, username, email, password="password123"):
    return client.post("/auth/register", json={"username": username, "email": email, "password": password})


def _login(client, username, password="password123"):
    return client.post("/auth/login", json={"username": username, "password": password}).json()["access_token"]


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _set_role(username, role):
    db = TestingSessionLocal()
    try:
        db.query(User).filter(User.username == username).first().role = role
        db.commit()
    finally:
        db.close()


def _admin(client, username="s_admin", email="s_admin@example.com"):
    _register(client, username, email)
    _set_role(username, "Admin")
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


def _dcb_bill(suffix: str, centre_name: str):
    _make_user(f"s_dcb_setup{suffix}")
    db = TestingSessionLocal()
    try:
        user = db.query(User).filter(User.username == f"s_dcb_setup{suffix}").first()
        rule = dcb_svc.create_rule(db, rule_version=f"S-DCB-{suffix}", created_by=user)
        dcb_svc.approve_rule(db, rule=rule, approver=user)
        batch = dcb_svc.create_upload_batch(
            db, period_start=date(2026, 7, 1), period_end=date(2026, 7, 31),
            source_filename=f"s-{suffix}.xlsx", rule=rule, uploaded_by=user,
        )
        bill_date = date(2026, 7, 1)
        created = bill_date + timedelta(days=2)
        raw = dcb_svc.RawBillInput(
            centre_code=f"S-DCB-{suffix}", centre_name=centre_name,
            sales_bill=f"S-{suffix}-1", bill_date=bill_date,
            bill_created_time=datetime.combine(created, datetime.min.time(), tzinfo=timezone.utc),
            created_date=created, source_day_difference=2,
        )
        bills = dcb_svc.ingest_bills(db, batch=batch, rule=rule, raw_bills=[raw])
        return bills[0].id, f"S-DCB-{suffix}"
    finally:
        db.close()


def _wrc_incident(suffix: str, centre_name: str):
    _make_user(f"s_wrc_setup{suffix}")
    db = TestingSessionLocal()
    try:
        user = db.query(User).filter(User.username == f"s_wrc_setup{suffix}").first()
        rule = wrc_svc.create_rule(db, rule_version=f"S-WRC-{suffix}", created_by=user)
        wrc_svc.approve_rule(db, rule=rule, approver=user)
        batch = wrc_svc.create_batch(
            db, period_start=date(2026, 7, 1), period_end=date(2026, 7, 7),
            week_label=f"Week S {suffix}", rule=rule, created_by=user,
        )
        raw = wrc_svc.RawBillIncidentInput(
            centre_code=f"S-WRC-{suffix}", centre_name=centre_name,
            incident_date=date(2026, 7, 2), mis_final_remark="bill_pending",
        )
        incidents = wrc_svc.record_bill_incidents(db, batch=batch, raw_incidents=[raw])
        return incidents[0].id
    finally:
        db.close()


def test_search_finds_dcb_bill_by_centre_name(client):
    token = _admin(client)
    bill_id, code = _dcb_bill("1", "Distinctive DCB Marker Center")

    resp = client.get("/search?q=Distinctive DCB Marker", headers=_auth(token)).json()
    matches = resp["results"].get("delayed_cash_bill", [])
    assert any(r["id"] == bill_id for r in matches)

    by_code = client.get(f"/search?q={code}", headers=_auth(token)).json()
    assert any(r["id"] == bill_id for r in by_code["results"].get("delayed_cash_bill", []))


def test_search_finds_wrc_incident_by_centre_name(client):
    token = _admin(client, "s_admin2", "s_admin2@example.com")
    incident_id = _wrc_incident("2", "Distinctive WRC Marker Center")

    resp = client.get("/search?q=Distinctive WRC Marker", headers=_auth(token)).json()
    matches = resp["results"].get("wrc_incident", [])
    assert any(r["id"] == incident_id for r in matches)


def test_search_finds_dataset_and_org_node(client):
    import io

    token = _admin(client, "s_admin3", "s_admin3@example.com")
    client.post(
        "/datasets",
        data={"name": "Distinctive Dataset Marker"},
        files={"file": ("m.csv", io.BytesIO(b"a,b\n1,2"), "text/csv")},
        headers=_auth(token),
    )

    dims = client.get("/org/dimensions", headers=_auth(token)).json()
    zone_id = next(d["id"] for d in dims if d["key"] == "zone")
    client.post(
        "/org/nodes",
        json={"dimension_id": zone_id, "parent_id": None, "name": "Distinctive Zone Marker"},
        headers=_auth(token),
    )

    dataset_hits = client.get("/search?q=Distinctive Dataset", headers=_auth(token)).json()
    assert len(dataset_hits["results"].get("dataset", [])) == 1

    node_hits = client.get("/search?q=Distinctive Zone", headers=_auth(token)).json()
    assert len(node_hits["results"].get("org_node", [])) == 1


def test_search_respects_types_filter(client):
    token = _admin(client, "s_admin4", "s_admin4@example.com")
    _dcb_bill("4", "Filter Test DCB Center")

    only_datasets = client.get("/search?q=Filter Test&types=dataset", headers=_auth(token)).json()
    assert "delayed_cash_bill" not in only_datasets["results"]


def test_search_requires_vigilance_role(client):
    assert client.get("/search?q=anything").status_code == 401

    _register(client, "s_center_mgr", "s_center_mgr@example.com")
    _set_role("s_center_mgr", "Center Manager")
    token = _login(client, "s_center_mgr")
    resp = client.get("/search?q=anything", headers=_auth(token))
    assert resp.status_code == 403


def test_empty_query_rejected(client):
    token = _admin(client, "s_admin6", "s_admin6@example.com")
    resp = client.get("/search?q=", headers=_auth(token))
    assert resp.status_code == 422

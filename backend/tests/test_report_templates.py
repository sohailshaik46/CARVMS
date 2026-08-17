"""Tests for /report-templates and /report-history -- rewritten 2026-08-14
for the Billing (DCB + WRC) filter shape ({period_from, period_to})
that replaced the deleted Audits-era {status, center_node_id, ...} shape.
report_service.py itself is unchanged -- these are the same generic
saved-filter-set / history-log behaviors, just against new filter data.
"""
from datetime import date, datetime, timedelta, timezone

from app.models.user import User
from app.services import delayed_cash_penalty_service as dcb_svc
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


def _admin(client, username="rt_admin", email="rt_admin@example.com"):
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


def _seed_dcb_bill(suffix: str, bill_date=date(2026, 7, 1)):
    _make_user(f"rt_dcb_setup{suffix}")
    db = TestingSessionLocal()
    try:
        user = db.query(User).filter(User.username == f"rt_dcb_setup{suffix}").first()
        rule = dcb_svc.create_rule(db, rule_version=f"RT-DCB-{suffix}", created_by=user)
        dcb_svc.approve_rule(db, rule=rule, approver=user)
        batch = dcb_svc.create_upload_batch(
            db, period_start=bill_date.replace(day=1), period_end=date(bill_date.year, bill_date.month, 28),
            source_filename=f"rt-{suffix}.xlsx", rule=rule, uploaded_by=user,
        )
        created = bill_date + timedelta(days=2)
        raw = dcb_svc.RawBillInput(
            centre_code=f"RT-DCB-{suffix}", centre_name=f"RT Center {suffix}",
            sales_bill=f"RT-{suffix}-1", bill_date=bill_date,
            bill_created_time=datetime.combine(created, datetime.min.time(), tzinfo=timezone.utc),
            created_date=created, source_day_difference=2,
        )
        dcb_svc.ingest_bills(db, batch=batch, rule=rule, raw_bills=[raw])
    finally:
        db.close()


# ---------- templates ----------

def test_create_and_list_template(client):
    token = _admin(client)
    resp = client.post(
        "/report-templates",
        json={"name": "Monthly Vigilance Report", "description": "Runs monthly", "filters": {"period_from": "2026-07-01", "period_to": "2026-07-31"}},
        headers=_auth(token),
    )
    assert resp.status_code == 201
    template = resp.json()
    assert template["name"] == "Monthly Vigilance Report"
    assert template["filters"]["period_from"] == "2026-07-01"

    listing = client.get("/report-templates", headers=_auth(token)).json()
    assert any(t["id"] == template["id"] for t in listing)


def test_delete_template_requires_creator_or_admin(client):
    owner_token = _admin(client, "rt_owner", "rt_owner@example.com")
    template = client.post(
        "/report-templates",
        json={"name": "Owner's template", "filters": {}},
        headers=_auth(owner_token),
    ).json()

    _register(client, "rt_stranger", "rt_stranger@example.com")
    _set_role("rt_stranger", "Auditor")
    stranger_token = _login(client, "rt_stranger")

    resp = client.delete(f"/report-templates/{template['id']}", headers=_auth(stranger_token))
    assert resp.status_code == 403

    ok = client.delete(f"/report-templates/{template['id']}", headers=_auth(owner_token))
    assert ok.status_code == 204


# ---------- run + history ----------

def test_running_a_template_matches_dashboard_and_logs_history(client):
    token = _admin(client, "rt_admin2", "rt_admin2@example.com")
    _seed_dcb_bill("2", bill_date=date(2026, 7, 5))

    template = client.post(
        "/report-templates",
        json={"name": "July Bills", "filters": {"period_from": "2026-07-01", "period_to": "2026-07-31"}},
        headers=_auth(token),
    ).json()

    summary = client.get(
        "/dashboard/summary", params={"period_from": "2026-07-01", "period_to": "2026-07-31"}, headers=_auth(token)
    ).json()

    resp = client.post(f"/report-templates/{template['id']}/run?format=csv", headers=_auth(token))
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/csv")
    assert "RT-DCB-2" in resp.text
    assert summary["dcb"]["total_bills"] >= 1

    history = client.get("/report-history", headers=_auth(token)).json()
    assert len(history) == 1
    assert history[0]["template_id"] == template["id"]
    assert history[0]["name"] == "July Bills"
    assert history[0]["format"] == "csv"
    assert history[0]["status"] == "completed"


def test_adhoc_export_also_logs_history(client):
    token = _admin(client, "rt_admin3", "rt_admin3@example.com")
    _seed_dcb_bill("3")

    client.get("/reports/billing/export.xlsx", headers=_auth(token))

    history = client.get("/report-history", headers=_auth(token)).json()
    assert len(history) == 1
    assert history[0]["template_id"] is None
    assert history[0]["name"] == "Ad-hoc Billing Export"
    assert history[0]["format"] == "xlsx"


def test_regenerate_uses_stored_filters_and_links_back(client):
    token = _admin(client, "rt_admin4", "rt_admin4@example.com")
    _seed_dcb_bill("4", bill_date=date(2026, 7, 10))

    client.get(
        "/reports/billing/export.csv", params={"period_from": "2026-07-01", "period_to": "2026-07-31"}, headers=_auth(token)
    )
    original = client.get("/report-history", headers=_auth(token)).json()[0]

    resp = client.post(f"/report-history/{original['id']}/regenerate", headers=_auth(token))
    assert resp.status_code == 200

    history = client.get("/report-history", headers=_auth(token)).json()
    assert len(history) == 2
    regenerated = next(h for h in history if h["id"] != original["id"])
    assert regenerated["regenerated_from_id"] == original["id"]
    assert regenerated["filters_used"]["period_from"] == "2026-07-01"


def test_regenerate_can_change_format(client):
    token = _admin(client, "rt_admin5", "rt_admin5@example.com")
    _seed_dcb_bill("5")

    client.get("/reports/billing/export.csv", headers=_auth(token))
    original = client.get("/report-history", headers=_auth(token)).json()[0]

    resp = client.post(f"/report-history/{original['id']}/regenerate?format=pdf", headers=_auth(token))
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/pdf")


def test_anonymous_cannot_access_templates_or_history(client):
    assert client.get("/report-templates").status_code == 401
    assert client.get("/report-history").status_code == 401
    assert client.post("/report-templates", json={"name": "x", "filters": {}}).status_code == 401


def test_non_vigilance_role_denied(client):
    _register(client, "rt_cm", "rt_cm@example.com")
    _set_role("rt_cm", "Center Manager")
    token = _login(client, "rt_cm")
    assert client.get("/report-templates", headers=_auth(token)).status_code == 403

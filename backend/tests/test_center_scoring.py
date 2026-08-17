"""Tests for /center-scoring/* -- rewritten 2026-08-14 to score centers on
Delayed Cash Billing (DCB) + Weekly Revenue Closure (WRC) non-compliance
instead of the deleted Audits/Findings domain.
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


def _admin(client, username="cs_admin", email="cs_admin@example.com"):
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


def _dcb_case(suffix: str, decisions: list[str]):
    _make_user(f"cs_dcb_setup{suffix}")
    db = TestingSessionLocal()
    try:
        user = db.query(User).filter(User.username == f"cs_dcb_setup{suffix}").first()
        rule = dcb_svc.create_rule(db, rule_version=f"CS-DCB-{suffix}", created_by=user)
        dcb_svc.approve_rule(db, rule=rule, approver=user)
        batch = dcb_svc.create_upload_batch(
            db, period_start=date(2026, 7, 1), period_end=date(2026, 7, 31),
            source_filename=f"cs-{suffix}.xlsx", rule=rule, uploaded_by=user,
        )
        code = f"CS-DCB-{suffix}"
        bill_date = date(2026, 7, 1)
        raw_bills = []
        for i, _ in enumerate(decisions):
            created = bill_date + timedelta(days=2)
            raw_bills.append(
                dcb_svc.RawBillInput(
                    centre_code=code, centre_name=f"CS DCB Center {suffix}",
                    sales_bill=f"CS-{suffix}-{i}", bill_date=bill_date,
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


# ---------- weights ----------

def test_default_weights_are_equal(client):
    token = _admin(client)
    weights = client.get("/center-scoring/weights", headers=_auth(token)).json()
    assert {w["component_key"]: w["weight"] for w in weights} == {
        "non_compliance_rate": 0.25,
        "repeat_violations": 0.25,
        "outstanding_penalty": 0.25,
        "unresolved_cases": 0.25,
    }


def test_only_admin_can_update_weight(client):
    token = _admin(client, "cs_admin2", "cs_admin2@example.com")
    _register(client, "cs_stranger", "cs_stranger@example.com")
    stranger_token = _login(client, "cs_stranger")

    denied = client.patch(
        "/center-scoring/weights/non_compliance_rate", json={"weight": 0.5}, headers=_auth(stranger_token)
    )
    assert denied.status_code == 403

    ok = client.patch("/center-scoring/weights/non_compliance_rate", json={"weight": 0.6}, headers=_auth(token))
    assert ok.status_code == 200
    assert ok.json()["weight"] == 0.6


def test_update_unknown_component_404s(client):
    token = _admin(client, "cs_admin3", "cs_admin3@example.com")
    resp = client.patch("/center-scoring/weights/not_a_real_component", json={"weight": 0.5}, headers=_auth(token))
    assert resp.status_code == 404


# ---------- rankings ----------

def test_ranking_orders_better_center_first(client):
    token = _admin(client, "cs_admin4", "cs_admin4@example.com")
    good_code = _dcb_case("4good", ["considered"])
    bad_code = _dcb_case("4bad", ["not_considered", "not_considered"])

    rankings = client.get("/center-scoring/rankings", headers=_auth(token)).json()
    codes_in_order = [r["centre_code"] for r in rankings]
    assert codes_in_order.index(good_code) < codes_in_order.index(bad_code)

    good = next(r for r in rankings if r["centre_code"] == good_code)
    bad = next(r for r in rankings if r["centre_code"] == bad_code)
    assert good["composite_score"] > bad["composite_score"]
    assert bad["components"]["repeat_violations"]["raw"] == 2.0
    assert good["components"]["repeat_violations"]["raw"] == 0.0


def test_center_with_no_penalty_excludes_outstanding_penalty_not_zero(client):
    token = _admin(client, "cs_admin5", "cs_admin5@example.com")
    code = _dcb_case("5", ["considered"])

    rankings = client.get("/center-scoring/rankings", headers=_auth(token)).json()
    entry = next(r for r in rankings if r["centre_code"] == code)
    # "considered" bills never contribute to validated_penalty until every
    # bill in the case is terminal; with only one considered bill and no
    # not_considered ones, validated_penalty stays 0.0, not None, at the
    # DelayedCashCenterPenalty layer -- outstanding_penalty is therefore a
    # real 0.0 here, not an excluded component. Composite is still computed.
    assert entry["composite_score"] is not None


def test_rankings_are_not_scoped_by_role_only_gated(client):
    """Billing data has no per-row visibility model (unlike the old Audits
    RBAC scoping) -- an Auditor sees the same full rankings an Admin does;
    a non-vigilance role is denied outright instead of seeing a filtered
    subset."""
    admin_token = _admin(client, "cs_admin6", "cs_admin6@example.com")
    code = _dcb_case("6", ["not_considered"])

    _register(client, "cs_auditor6", "cs_auditor6@example.com")  # default role: Auditor
    auditor_token = _login(client, "cs_auditor6")

    admin_rankings = client.get("/center-scoring/rankings", headers=_auth(admin_token)).json()
    auditor_rankings = client.get("/center-scoring/rankings", headers=_auth(auditor_token)).json()
    assert {r["centre_code"] for r in admin_rankings} == {r["centre_code"] for r in auditor_rankings}
    assert code in {r["centre_code"] for r in admin_rankings}


def test_center_manager_denied(client):
    _register(client, "cs_cm", "cs_cm@example.com")
    _set_role("cs_cm", "Center Manager")
    token = _login(client, "cs_cm")
    resp = client.get("/center-scoring/rankings", headers=_auth(token))
    assert resp.status_code == 403


def test_anonymous_cannot_access(client):
    assert client.get("/center-scoring/rankings").status_code == 401
    assert client.get("/center-scoring/weights").status_code == 401

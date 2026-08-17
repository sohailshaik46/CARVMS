from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from io import BytesIO

from app.models.user import User
from app.services import delayed_cash_penalty_service as calc_svc
from app.services import delayed_cash_response_service as resp_svc
from tests.conftest import TestingSessionLocal


def _register(client, username, email, password="password123"):
    return client.post("/auth/register", json={"username": username, "email": email, "password": password})


def _login(client, username, password="password123"):
    return client.post("/auth/login", json={"username": username, "password": password}).json()["access_token"]


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _admin(client, username="dcbp_admin", email="dcbp_admin@example.com"):
    _register(client, username, email)
    db = TestingSessionLocal()
    try:
        db.query(User).filter(User.username == username).first().role = "Admin"
        db.commit()
    finally:
        db.close()
    return _login(client, username)


def _make_center_penalty(username_suffix=""):
    """Builds one real center-penalty case through the actual calculator
    pipeline (not a hand-crafted row), so the portal is tested against a
    genuine case, matching how the rest of this suite avoids fabricated
    shortcuts."""
    db = TestingSessionLocal()
    try:
        user = db.query(User).filter(User.username == f"dcbp_setup{username_suffix}").first()
        if user is None:
            import bcrypt

            user = User(
                username=f"dcbp_setup{username_suffix}",
                email=f"dcbp_setup{username_suffix}@example.com",
                password_hash=bcrypt.hashpw(b"password123", bcrypt.gensalt()).decode(),
                role="Admin",
                is_active=True,
            )
            db.add(user)
            db.commit()
            db.refresh(user)

        rule = calc_svc.create_rule(db, rule_version=f"DCB-PORTAL-{username_suffix}", created_by=user)
        calc_svc.approve_rule(db, rule=rule, approver=user)
        batch = calc_svc.create_upload_batch(
            db, period_start=date(2026, 7, 1), period_end=date(2026, 7, 31),
            source_filename="portal-test.xlsx", rule=rule, uploaded_by=user,
        )
        bill_date = date(2026, 7, 1)
        created = bill_date + timedelta(days=2)
        raw = calc_svc.RawBillInput(
            centre_code=f"PORTAL-C{username_suffix}", centre_name="Portal Test Center",
            sales_bill=f"PORTAL-{username_suffix}-1", bill_date=bill_date,
            bill_created_time=datetime.combine(created, datetime.min.time(), tzinfo=timezone.utc),
            created_date=created, source_day_difference=2,
        )
        calc_svc.ingest_bills(db, batch=batch, rule=rule, raw_bills=[raw])
        center_penalties = calc_svc.compute_center_penalties(db, batch=batch, rule=rule)
        return center_penalties[0].id
    finally:
        db.close()


def _evidence_file(name="proof.pdf", content=b"%PDF-1.4 fake evidence content"):
    return {"evidence": (name, BytesIO(content), "application/pdf")}


# ---------- internal (Vigilance-role) surface ----------

def test_non_vigilance_role_cannot_generate_link(client):
    _admin(client)  # ensures at least one admin exists; not used here
    cp_id = _make_center_penalty("1")
    _register(client, "dcbp_plain", "dcbp_plain@example.com")
    db = TestingSessionLocal()
    try:
        # Auditor is one of VIGILANCE_ROLES -- use a role that genuinely
        # isn't, so this test actually exercises the restriction.
        db.query(User).filter(User.username == "dcbp_plain").first().role = "Center Manager"
        db.commit()
    finally:
        db.close()
    token = _login(client, "dcbp_plain")

    resp = client.post(f"/delayed-cash/center-penalties/{cp_id}/response-link", headers=_auth(token))
    assert resp.status_code == 403


def test_admin_can_generate_response_link(client):
    admin_token = _admin(client, "dcbp_admin2", "dcbp_admin2@example.com")
    cp_id = _make_center_penalty("2")

    resp = client.post(f"/delayed-cash/center-penalties/{cp_id}/response-link", headers=_auth(admin_token))
    assert resp.status_code == 200
    data = resp.json()
    assert data["response_token"]
    assert data["response_url"].endswith(f"/respond/delayed-cash/{data['response_token']}")
    assert "expires_at" in data


def test_regenerating_link_invalidates_the_old_token(client):
    admin_token = _admin(client, "dcbp_admin3", "dcbp_admin3@example.com")
    cp_id = _make_center_penalty("3")

    first = client.post(f"/delayed-cash/center-penalties/{cp_id}/response-link", headers=_auth(admin_token)).json()
    second = client.post(f"/delayed-cash/center-penalties/{cp_id}/response-link", headers=_auth(admin_token)).json()
    assert first["response_token"] != second["response_token"]

    old_lookup = client.get(f"/public/delayed-cash/cases/{first['response_token']}")
    assert old_lookup.status_code == 404
    new_lookup = client.get(f"/public/delayed-cash/cases/{second['response_token']}")
    assert new_lookup.status_code == 200


def test_response_link_404_for_unknown_case(client):
    admin_token = _admin(client, "dcbp_admin4", "dcbp_admin4@example.com")
    resp = client.post("/delayed-cash/center-penalties/999999/response-link", headers=_auth(admin_token))
    assert resp.status_code == 404


def test_list_and_get_center_penalties_requires_vigilance_role(client):
    admin_token = _admin(client, "dcbp_admin5", "dcbp_admin5@example.com")
    cp_id = _make_center_penalty("5")

    assert client.get("/delayed-cash/center-penalties").status_code == 401
    resp = client.get("/delayed-cash/center-penalties", headers=_auth(admin_token))
    assert resp.status_code == 200
    assert any(cp["id"] == cp_id for cp in resp.json())

    detail = client.get(f"/delayed-cash/center-penalties/{cp_id}", headers=_auth(admin_token))
    assert detail.status_code == 200
    assert detail.json()["centre_code"] == "PORTAL-C5"


# ---------- public portal surface ----------

def test_public_case_lookup_with_invalid_token_404s(client):
    resp = client.get("/public/delayed-cash/cases/not-a-real-token")
    assert resp.status_code == 404


def test_public_case_lookup_returns_safe_summary(client):
    admin_token = _admin(client, "dcbp_admin6", "dcbp_admin6@example.com")
    cp_id = _make_center_penalty("6")
    link = client.post(f"/delayed-cash/center-penalties/{cp_id}/response-link", headers=_auth(admin_token)).json()

    resp = client.get(f"/public/delayed-cash/cases/{link['response_token']}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["centre_code"] == "PORTAL-C6"
    assert data["centre_name"] == "Portal Test Center"
    assert data["total_bills"] == 1
    assert data["calculated_penalty"] == "200.00" or float(data["calculated_penalty"]) == 200.0
    assert data["tat_status"] == "within_window"
    assert data["already_responded"] is False


def test_submit_response_without_evidence_is_rejected(client):
    admin_token = _admin(client, "dcbp_admin7", "dcbp_admin7@example.com")
    cp_id = _make_center_penalty("7")
    link = client.post(f"/delayed-cash/center-penalties/{cp_id}/response-link", headers=_auth(admin_token)).json()

    resp = client.post(
        f"/public/delayed-cash/cases/{link['response_token']}/respond",
        data={
            "responder_name": "Test Manager",
            "responder_npid": "NP12345",
            "responder_email": "manager@example.com",
            "reason": "No proof, testing rejection",
        },
    )
    assert resp.status_code == 400
    assert "mandatory" in resp.json()["detail"].lower()


def test_submit_response_with_evidence_succeeds_and_is_recorded(client):
    admin_token = _admin(client, "dcbp_admin8", "dcbp_admin8@example.com")
    cp_id = _make_center_penalty("8")
    link = client.post(f"/delayed-cash/center-penalties/{cp_id}/response-link", headers=_auth(admin_token)).json()

    resp = client.post(
        f"/public/delayed-cash/cases/{link['response_token']}/respond",
        data={
            "responder_name": "Test Manager",
            "responder_npid": "NP12345",
            "responder_email": "manager@example.com",
            "reason": "Session ran late, proof attached",
        },
        files=_evidence_file(),
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["responder_name"] == "Test Manager"
    assert body["responder_npid"] == "NP12345"
    assert body["responder_email"] == "manager@example.com"
    assert body["evidence_original_filename"] == "proof.pdf"
    assert body["was_within_tat"] == "within_window"

    # already_responded now flips true for this case.
    case = client.get(f"/public/delayed-cash/cases/{link['response_token']}").json()
    assert case["already_responded"] is True


def test_submit_response_records_selected_center_even_when_it_differs_from_the_case(client):
    """The Center Code/Name dropdowns let the responder pick any center --
    a mismatch against the case's own centre_code must be recorded, not
    rejected or silently corrected."""
    admin_token = _admin(client, "dcbp_admin11", "dcbp_admin11@example.com")
    cp_id = _make_center_penalty("11")
    link = client.post(f"/delayed-cash/center-penalties/{cp_id}/response-link", headers=_auth(admin_token)).json()

    resp = client.post(
        f"/public/delayed-cash/cases/{link['response_token']}/respond",
        data={
            "responder_name": "Test Manager",
            "responder_npid": "NP12345",
            "responder_email": "manager@example.com",
            "reason": "Responding on behalf of a different center",
            "selected_center_code": "999-XX-TST-ABC-C",
            "selected_center_name": "Some Other Center",
        },
        files=_evidence_file(),
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["selected_center_code"] == "999-XX-TST-ABC-C"
    assert body["selected_center_name"] == "Some Other Center"


def test_submit_response_without_selected_center_leaves_it_null(client):
    admin_token = _admin(client, "dcbp_admin12", "dcbp_admin12@example.com")
    cp_id = _make_center_penalty("12")
    link = client.post(f"/delayed-cash/center-penalties/{cp_id}/response-link", headers=_auth(admin_token)).json()

    resp = client.post(
        f"/public/delayed-cash/cases/{link['response_token']}/respond",
        data={
            "responder_name": "Test Manager",
            "responder_npid": "NP12345",
            "responder_email": "manager@example.com",
            "reason": "No center selected",
        },
        files=_evidence_file(),
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["selected_center_code"] is None
    assert body["selected_center_name"] is None


def test_centers_directory_returns_only_active_centers_with_code_and_name(client):
    from app.models.org import OrgDimension, OrgNode
    from app.services import org_service

    db = TestingSessionLocal()
    try:
        org_service.seed_default_dimensions_if_missing(db)
        center_dim = db.query(OrgDimension).filter_by(key="center").first()
        active = org_service.create_node(
            db, dimension_id=center_dim.id, parent_id=None, name="Active Directory Center", external_code="DIR-ACTIVE-1"
        )
        inactive = org_service.create_node(
            db, dimension_id=center_dim.id, parent_id=None, name="Inactive Directory Center", external_code="DIR-INACTIVE-1"
        )
        org_service.update_node(db, node=inactive, is_active=False)
    finally:
        db.close()

    resp = client.get("/public/delayed-cash/centers-directory")
    assert resp.status_code == 200
    codes = {e["code"] for e in resp.json()}
    assert "DIR-ACTIVE-1" in codes
    assert "DIR-INACTIVE-1" not in codes


def test_second_submission_after_further_proof_request_is_recorded_too(client):
    """Append-only: a center can legitimately submit more than once (e.g.
    after Vigilance asks for further proof) -- the second submission must
    not overwrite or block the first."""
    admin_token = _admin(client, "dcbp_admin9", "dcbp_admin9@example.com")
    cp_id = _make_center_penalty("9")
    link = client.post(f"/delayed-cash/center-penalties/{cp_id}/response-link", headers=_auth(admin_token)).json()

    client.post(
        f"/public/delayed-cash/cases/{link['response_token']}/respond",
        data={
            "responder_name": "Test Manager",
            "responder_npid": "NP12345",
            "responder_email": "manager@example.com",
            "reason": "First submission",
        },
        files=_evidence_file("first.pdf"),
    )
    second = client.post(
        f"/public/delayed-cash/cases/{link['response_token']}/respond",
        data={
            "responder_name": "Test Manager",
            "responder_npid": "NP12345",
            "responder_email": "manager@example.com",
            "reason": "Further proof as requested",
        },
        files=_evidence_file("second.pdf"),
    )
    assert second.status_code == 201

    db = TestingSessionLocal()
    try:
        cp = resp_svc.get_case_by_token(db, link["response_token"])
        responses = resp_svc.list_responses(db, center_penalty=cp)
        assert len(responses) == 2
        assert [r.evidence_original_filename for r in responses] == ["first.pdf", "second.pdf"]
    finally:
        db.close()


def test_overdue_submission_is_flagged_but_still_accepted(client):
    admin_token = _admin(client, "dcbp_admin10", "dcbp_admin10@example.com")
    cp_id = _make_center_penalty("10")
    link = client.post(f"/delayed-cash/center-penalties/{cp_id}/response-link", headers=_auth(admin_token)).json()

    db = TestingSessionLocal()
    try:
        cp = resp_svc.get_case_by_token(db, link["response_token"])
        cp.response_token_expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
        db.commit()
    finally:
        db.close()

    case = client.get(f"/public/delayed-cash/cases/{link['response_token']}").json()
    assert case["tat_status"] == "overdue"

    resp = client.post(
        f"/public/delayed-cash/cases/{link['response_token']}/respond",
        data={
            "responder_name": "Late Manager",
            "responder_npid": "NP99999",
            "responder_email": "late.manager@example.com",
            "reason": "Sorry, submitting late",
        },
        files=_evidence_file(),
    )
    assert resp.status_code == 201
    assert resp.json()["was_within_tat"] == "overdue"


def test_anonymous_cannot_reach_internal_endpoints_but_can_reach_public_ones(client):
    assert client.get("/delayed-cash/center-penalties").status_code == 401
    # Public GET with a bogus token still resolves (404, not 401) -- proves
    # no auth dependency is silently guarding the public router.
    assert client.get("/public/delayed-cash/cases/whatever").status_code == 404

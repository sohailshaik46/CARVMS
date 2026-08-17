"""Tests for the center-manager contact-change-request workflow --
propose/list/approve/reject, and the end-to-end trigger from a real Delayed
Cash Billing response submission. Nothing here ever writes to
OrgNode.manager_* except through an explicit approve_request() call --
that's the entire point of this module, so it's asserted directly.
"""

from datetime import date, datetime, timedelta, timezone
from io import BytesIO

from app.models.org import OrgDimension, OrgNode
from app.models.user import User
from app.services import delayed_cash_penalty_service as calc_svc
from app.services import org_contact_change_service as change_svc
from app.services import org_service
from tests.conftest import TestingSessionLocal


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


def _make_center_node(db, code, name="Contact Test Center", manager_name=None, manager_npid=None, manager_email=None):
    org_service.seed_default_dimensions_if_missing(db)
    center_dim = db.query(OrgDimension).filter_by(key="center").first()
    node = org_service.create_node(db, dimension_id=center_dim.id, parent_id=None, name=name, external_code=code)
    if manager_name or manager_npid or manager_email:
        org_service.update_node(db, node=node, manager_name=manager_name, manager_npid=manager_npid, manager_email=manager_email)
    return node


def _get_or_create_user(db, username):
    user = db.query(User).filter(User.username == username).first()
    if user is None:
        import bcrypt

        user = User(
            username=username,
            email=f"{username}@example.com",
            password_hash=bcrypt.hashpw(b"password123", bcrypt.gensalt()).decode(),
            role="Admin",
            is_active=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    return user


# ---------------------------------------------------------------------------
# Service-level: propose
# ---------------------------------------------------------------------------


def test_propose_creates_pending_request_for_known_node():
    db = TestingSessionLocal()
    try:
        node = _make_center_node(db, "CCR-1")
        request = change_svc.propose_contact_change(
            db, centre_code="CCR-1", manager_name="Asha Rao", manager_npid="NP1001",
            manager_email="asha@example.com", source="test",
        )
        assert request is not None
        assert request.status == "pending"
        assert request.org_node_id == node.id
        assert request.proposed_manager_name == "Asha Rao"
    finally:
        db.close()


def test_propose_returns_none_when_nothing_submitted():
    db = TestingSessionLocal()
    try:
        result = change_svc.propose_contact_change(
            db, centre_code="CCR-NOTHING", manager_name=None, manager_npid=None, manager_email=None, source="test",
        )
        assert result is None
    finally:
        db.close()


def test_propose_returns_none_when_values_already_match_on_file():
    db = TestingSessionLocal()
    try:
        _make_center_node(db, "CCR-2", manager_name="Same Name", manager_npid="NP2002", manager_email="same@example.com")
        result = change_svc.propose_contact_change(
            db, centre_code="CCR-2", manager_name="Same Name", manager_npid="NP2002",
            manager_email="same@example.com", source="test",
        )
        assert result is None
    finally:
        db.close()


def test_propose_creates_unresolved_request_when_no_node_matches():
    db = TestingSessionLocal()
    try:
        request = change_svc.propose_contact_change(
            db, centre_code="CCR-UNKNOWN-CODE", manager_name="Nobody Here", manager_npid="NP0000",
            manager_email="nobody@example.com", source="test",
        )
        assert request is not None
        assert request.org_node_id is None
        assert request.centre_code_hint == "CCR-UNKNOWN-CODE"
    finally:
        db.close()


def test_propose_refreshes_existing_pending_request_instead_of_duplicating():
    db = TestingSessionLocal()
    try:
        _make_center_node(db, "CCR-3")
        first = change_svc.propose_contact_change(
            db, centre_code="CCR-3", manager_name="First Name", manager_npid="NP1", manager_email="a@example.com", source="test",
        )
        second = change_svc.propose_contact_change(
            db, centre_code="CCR-3", manager_name="Second Name", manager_npid="NP2", manager_email="b@example.com", source="test",
        )
        assert second.id == first.id
        assert second.proposed_manager_name == "Second Name"

        pending = change_svc.list_requests(db, status="pending")
        matching = [r for r in pending if r.centre_code_hint == "CCR-3"]
        assert len(matching) == 1
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Service-level: approve / reject
# ---------------------------------------------------------------------------


def test_approve_applies_change_to_org_node():
    db = TestingSessionLocal()
    try:
        approver = _get_or_create_user(db, "ccr_approver1")
        node = _make_center_node(db, "CCR-4")
        request = change_svc.propose_contact_change(
            db, centre_code="CCR-4", manager_name="New Manager", manager_npid="NP4004",
            manager_email="new@example.com", source="test",
        )
        change_svc.approve_request(db, request=request, approver=approver)

        db.refresh(node)
        assert node.manager_name == "New Manager"
        assert node.manager_npid == "NP4004"
        assert node.manager_email == "new@example.com"
        assert request.status == "approved"
        assert request.reviewed_by_id == approver.id
    finally:
        db.close()


def test_approve_without_matching_node_raises():
    db = TestingSessionLocal()
    try:
        approver = _get_or_create_user(db, "ccr_approver2")
        request = change_svc.propose_contact_change(
            db, centre_code="CCR-NO-NODE", manager_name="X", manager_npid="Y", manager_email="z@example.com", source="test",
        )
        import pytest

        with pytest.raises(change_svc.NoMatchingOrgNodeError):
            change_svc.approve_request(db, request=request, approver=approver)
    finally:
        db.close()


def test_reject_leaves_org_node_unchanged():
    db = TestingSessionLocal()
    try:
        approver = _get_or_create_user(db, "ccr_approver3")
        node = _make_center_node(db, "CCR-5", manager_name="Original", manager_npid="NP-ORIG", manager_email="orig@example.com")
        request = change_svc.propose_contact_change(
            db, centre_code="CCR-5", manager_name="Different", manager_npid="NP-DIFF", manager_email="diff@example.com", source="test",
        )
        change_svc.reject_request(db, request=request, approver=approver)

        db.refresh(node)
        assert node.manager_name == "Original"
        assert request.status == "rejected"
    finally:
        db.close()


def test_cannot_review_an_already_reviewed_request():
    db = TestingSessionLocal()
    try:
        approver = _get_or_create_user(db, "ccr_approver4")
        _make_center_node(db, "CCR-6")
        request = change_svc.propose_contact_change(
            db, centre_code="CCR-6", manager_name="X", manager_npid="Y", manager_email="z@example.com", source="test",
        )
        change_svc.approve_request(db, request=request, approver=approver)

        import pytest

        with pytest.raises(change_svc.AlreadyReviewedError):
            change_svc.approve_request(db, request=request, approver=approver)
        with pytest.raises(change_svc.AlreadyReviewedError):
            change_svc.reject_request(db, request=request, approver=approver)
    finally:
        db.close()


# ---------------------------------------------------------------------------
# API: RBAC + happy path
# ---------------------------------------------------------------------------


def test_contact_change_endpoints_require_admin(client):
    resp = client.get("/org/contact-change-requests")
    assert resp.status_code == 401

    _register(client, "ccr_auditor", "ccr_auditor@example.com")
    db = TestingSessionLocal()
    try:
        db.query(User).filter(User.username == "ccr_auditor").first().role = "Auditor"
        db.commit()
    finally:
        db.close()
    token = _login(client, "ccr_auditor")
    # Auditor is Vigilance for delayed-cash but NOT Admin -- this domain is
    # Admin-only since it mutates the Org Master.
    assert client.get("/org/contact-change-requests", headers=_auth(token)).status_code == 403


def test_list_approve_reject_via_api(client):
    admin_token = _admin(client, "ccr_admin1", "ccr_admin1@example.com")
    db = TestingSessionLocal()
    try:
        _make_center_node(db, "CCR-API-1")
        change_svc.propose_contact_change(
            db, centre_code="CCR-API-1", manager_name="API Manager", manager_npid="NPAPI1",
            manager_email="api@example.com", source="test",
        )
    finally:
        db.close()

    listing = client.get("/org/contact-change-requests?status=pending", headers=_auth(admin_token))
    assert listing.status_code == 200
    matches = [r for r in listing.json() if r["centre_code_hint"] == "CCR-API-1"]
    assert len(matches) == 1
    request_id = matches[0]["id"]

    approve = client.post(f"/org/contact-change-requests/{request_id}/approve", headers=_auth(admin_token))
    assert approve.status_code == 200
    assert approve.json()["status"] == "approved"

    # Approving twice is rejected, not silently re-applied.
    again = client.post(f"/org/contact-change-requests/{request_id}/approve", headers=_auth(admin_token))
    assert again.status_code == 409


def test_approve_unknown_request_404s(client):
    admin_token = _admin(client, "ccr_admin2", "ccr_admin2@example.com")
    resp = client.post("/org/contact-change-requests/999999/approve", headers=_auth(admin_token))
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# End-to-end: a real Delayed Cash Billing submission triggers a proposal
# ---------------------------------------------------------------------------


def _evidence_file():
    return {"evidence": ("proof.pdf", BytesIO(b"%PDF-1.4 fake"), "application/pdf")}


def test_response_submission_proposes_a_contact_change_end_to_end(client):
    admin_token = _admin(client, "ccr_e2e_admin", "ccr_e2e_admin@example.com")

    db = TestingSessionLocal()
    try:
        user = _get_or_create_user(db, "ccr_e2e_setup")
        _make_center_node(db, "CCR-E2E-C")  # no contact info on file yet

        rule = calc_svc.create_rule(db, rule_version="DCB-CCR-E2E", created_by=user)
        calc_svc.approve_rule(db, rule=rule, approver=user)
        batch = calc_svc.create_upload_batch(
            db, period_start=date(2026, 7, 1), period_end=date(2026, 7, 31),
            source_filename="ccr-e2e.xlsx", rule=rule, uploaded_by=user,
        )
        bill_date = date(2026, 7, 1)
        created = bill_date + timedelta(days=1)
        raw = calc_svc.RawBillInput(
            centre_code="CCR-E2E-C", centre_name="E2E Contact Center", sales_bill="CCR-E2E-1",
            bill_date=bill_date,
            bill_created_time=datetime.combine(created, datetime.min.time(), tzinfo=timezone.utc),
            created_date=created, source_day_difference=1,
        )
        calc_svc.ingest_bills(db, batch=batch, rule=rule, raw_bills=[raw])
        cp_id = calc_svc.compute_center_penalties(db, batch=batch, rule=rule)[0].id
    finally:
        db.close()

    link = client.post(f"/delayed-cash/center-penalties/{cp_id}/response-link", headers=_auth(admin_token)).json()
    submit = client.post(
        f"/public/delayed-cash/cases/{link['response_token']}/respond",
        data={
            "responder_name": "E2E Manager",
            "responder_npid": "NP-E2E",
            "responder_email": "e2e.manager@example.com",
            "reason": "Testing the contact-change proposal end to end",
        },
        files=_evidence_file(),
    )
    assert submit.status_code == 201

    pending = client.get("/org/contact-change-requests?status=pending", headers=_auth(admin_token)).json()
    matches = [r for r in pending if r["centre_code_hint"] == "CCR-E2E-C"]
    assert len(matches) == 1
    assert matches[0]["proposed_manager_name"] == "E2E Manager"
    assert matches[0]["proposed_manager_npid"] == "NP-E2E"
    assert matches[0]["proposed_manager_email"] == "e2e.manager@example.com"

    # And the OrgNode itself is untouched until approved.
    db = TestingSessionLocal()
    try:
        node = org_service.get_node_by_external_code(db, "CCR-E2E-C")
        assert node.manager_name is None
    finally:
        db.close()

    approve = client.post(f"/org/contact-change-requests/{matches[0]['id']}/approve", headers=_auth(admin_token))
    assert approve.status_code == 200

    db = TestingSessionLocal()
    try:
        node = org_service.get_node_by_external_code(db, "CCR-E2E-C")
        assert node.manager_name == "E2E Manager"
        assert node.manager_email == "e2e.manager@example.com"
    finally:
        db.close()

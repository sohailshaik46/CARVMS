"""Tests for the per-bill review queue: GET /delayed-cash/bills/review-queue,
GET /delayed-cash/center-penalties/{id}/bills, POST /delayed-cash/bills/{id}/review.
"""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from app.models.delayed_cash_billing import DelayedCashBill
from app.models.user import User
from app.services import delayed_cash_penalty_service as calc_svc
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


def _make_case_with_bills(username_suffix, day_diffs=(1, 2)):
    """Builds one real case through the actual calculator pipeline with N
    bills, so review-queue tests exercise real rows, not fabricated ones."""
    db = TestingSessionLocal()
    try:
        user = db.query(User).filter(User.username == f"dcbrq_setup{username_suffix}").first()
        if user is None:
            import bcrypt

            user = User(
                username=f"dcbrq_setup{username_suffix}",
                email=f"dcbrq_setup{username_suffix}@example.com",
                password_hash=bcrypt.hashpw(b"password123", bcrypt.gensalt()).decode(),
                role="Admin",
                is_active=True,
            )
            db.add(user)
            db.commit()
            db.refresh(user)

        rule = calc_svc.create_rule(db, rule_version=f"DCB-RQ-{username_suffix}", created_by=user)
        calc_svc.approve_rule(db, rule=rule, approver=user)
        batch = calc_svc.create_upload_batch(
            db, period_start=date(2026, 7, 1), period_end=date(2026, 7, 31),
            source_filename="rq-test.xlsx", rule=rule, uploaded_by=user,
        )
        bill_date = date(2026, 7, 1)
        raw_bills = []
        for i, dd in enumerate(day_diffs):
            created = bill_date + timedelta(days=dd)
            raw_bills.append(
                calc_svc.RawBillInput(
                    centre_code=f"RQ-C{username_suffix}", centre_name="Review Queue Test Center",
                    sales_bill=f"RQ-{username_suffix}-{i}", bill_date=bill_date,
                    bill_created_time=datetime.combine(created, datetime.min.time(), tzinfo=timezone.utc),
                    created_date=created, source_day_difference=dd,
                )
            )
        calc_svc.ingest_bills(db, batch=batch, rule=rule, raw_bills=raw_bills)
        center_penalties = calc_svc.compute_center_penalties(db, batch=batch, rule=rule)
        cp_id = center_penalties[0].id
        bill_ids = (
            db.query(DelayedCashBill.id)
            .filter(DelayedCashBill.batch_id == batch.id, DelayedCashBill.centre_code == f"RQ-C{username_suffix}")
            .order_by(DelayedCashBill.sales_bill)
            .all()
        )
        return cp_id, [b.id for b in bill_ids], rule.id
    finally:
        db.close()


# ---------------------------------------------------------------------------
# RBAC
# ---------------------------------------------------------------------------


def test_review_queue_requires_vigilance_role(client):
    assert client.get("/delayed-cash/bills/review-queue").status_code == 401

    _register(client, "dcbrq_plain", "dcbrq_plain@example.com")
    db = TestingSessionLocal()
    try:
        db.query(User).filter(User.username == "dcbrq_plain").first().role = "Center Manager"
        db.commit()
    finally:
        db.close()
    token = _login(client, "dcbrq_plain")
    assert client.get("/delayed-cash/bills/review-queue", headers=_auth(token)).status_code == 403


def test_review_bill_requires_vigilance_role(client):
    admin_token = _admin(client, "dcbrq_admin_rbac", "dcbrq_admin_rbac@example.com")
    _, bill_ids, _ = _make_case_with_bills("rbac")

    _register(client, "dcbrq_plain2", "dcbrq_plain2@example.com")
    db = TestingSessionLocal()
    try:
        db.query(User).filter(User.username == "dcbrq_plain2").first().role = "Center Manager"
        db.commit()
    finally:
        db.close()
    token = _login(client, "dcbrq_plain2")

    resp = client.post(
        f"/delayed-cash/bills/{bill_ids[0]}/review", json={"decision": "considered"}, headers=_auth(token)
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Review queue listing
# ---------------------------------------------------------------------------


def test_new_bills_appear_in_review_queue(client):
    admin_token = _admin(client, "dcbrq_admin1", "dcbrq_admin1@example.com")
    cp_id, bill_ids, _ = _make_case_with_bills("1")

    resp = client.get("/delayed-cash/bills/review-queue", headers=_auth(admin_token))
    assert resp.status_code == 200
    queue_ids = {b["id"] for b in resp.json()}
    assert set(bill_ids).issubset(queue_ids)
    for b in resp.json():
        if b["id"] in bill_ids:
            assert b["considered"] is None


def test_review_queue_bills_carry_their_center_penalty_id(client):
    """A bill has no FK to its case (the link is batch_id+centre_code) --
    the API layer resolves it so the frontend can fetch remarks/evidence
    for the right case without a second lookup."""
    admin_token = _admin(client, "dcbrq_admin_cpid", "dcbrq_admin_cpid@example.com")
    cp_id, bill_ids, _ = _make_case_with_bills("cpid")

    queue = client.get("/delayed-cash/bills/review-queue", headers=_auth(admin_token)).json()
    ours = [b for b in queue if b["id"] in bill_ids]
    assert len(ours) == 2
    for b in ours:
        assert b["center_penalty_id"] == cp_id


def test_list_bills_for_a_case(client):
    admin_token = _admin(client, "dcbrq_admin2", "dcbrq_admin2@example.com")
    cp_id, bill_ids, _ = _make_case_with_bills("2", day_diffs=(1, 2, 3))

    resp = client.get(f"/delayed-cash/center-penalties/{cp_id}/bills", headers=_auth(admin_token))
    assert resp.status_code == 200
    assert len(resp.json()) == 3
    assert {b["id"] for b in resp.json()} == set(bill_ids)


# ---------------------------------------------------------------------------
# Setting a decision
# ---------------------------------------------------------------------------


def test_marking_considered_removes_bill_from_queue(client):
    admin_token = _admin(client, "dcbrq_admin3", "dcbrq_admin3@example.com")
    cp_id, bill_ids, _ = _make_case_with_bills("3")

    resp = client.post(
        f"/delayed-cash/bills/{bill_ids[0]}/review", json={"decision": "considered"}, headers=_auth(admin_token)
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["bill"]["considered"] == "considered"
    assert body["bill"]["reviewed_at"] is not None
    assert body["response_link"] is None  # terminal decision -- no need to re-contact the center

    queue = client.get("/delayed-cash/bills/review-queue", headers=_auth(admin_token)).json()
    assert bill_ids[0] not in {b["id"] for b in queue}
    assert bill_ids[1] in {b["id"] for b in queue}  # the other bill is untouched


def test_needs_proof_decision_mints_a_response_link(client):
    admin_token = _admin(client, "dcbrq_admin4", "dcbrq_admin4@example.com")
    cp_id, bill_ids, _ = _make_case_with_bills("4")

    resp = client.post(
        f"/delayed-cash/bills/{bill_ids[0]}/review", json={"decision": "needs_proof"}, headers=_auth(admin_token)
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["bill"]["considered"] == "needs_proof"
    assert body["response_link"] is not None
    assert body["response_link"]["centre_code"] == "RQ-C4"

    # The link is real -- it resolves through the actual public portal.
    token = body["response_link"]["response_token"]
    public = client.get(f"/public/delayed-cash/cases/{token}")
    assert public.status_code == 200
    assert public.json()["centre_code"] == "RQ-C4"

    # A bill kicked back is still "pending" -- it stays in the queue.
    queue = client.get("/delayed-cash/bills/review-queue", headers=_auth(admin_token)).json()
    assert bill_ids[0] in {b["id"] for b in queue}


def test_needs_more_detail_decision_also_mints_a_response_link(client):
    admin_token = _admin(client, "dcbrq_admin5", "dcbrq_admin5@example.com")
    cp_id, bill_ids, _ = _make_case_with_bills("5")

    resp = client.post(
        f"/delayed-cash/bills/{bill_ids[0]}/review",
        json={"decision": "needs_more_detail"},
        headers=_auth(admin_token),
    )
    assert resp.status_code == 200
    assert resp.json()["response_link"] is not None


def test_invalid_decision_rejected(client):
    admin_token = _admin(client, "dcbrq_admin6", "dcbrq_admin6@example.com")
    _, bill_ids, _ = _make_case_with_bills("6")

    resp = client.post(
        f"/delayed-cash/bills/{bill_ids[0]}/review", json={"decision": "maybe"}, headers=_auth(admin_token)
    )
    assert resp.status_code == 400


def test_unknown_bill_404s(client):
    admin_token = _admin(client, "dcbrq_admin7", "dcbrq_admin7@example.com")
    resp = client.post(
        "/delayed-cash/bills/999999/review", json={"decision": "considered"}, headers=_auth(admin_token)
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# validated_penalty guard treats needs_more_detail/needs_proof as unreviewed
# ---------------------------------------------------------------------------


def test_validated_penalty_blocked_while_any_bill_needs_followup(client):
    admin_token = _admin(client, "dcbrq_admin8", "dcbrq_admin8@example.com")
    cp_id, bill_ids, rule_id = _make_case_with_bills("8", day_diffs=(1, 2))

    client.post(f"/delayed-cash/bills/{bill_ids[0]}/review", json={"decision": "not_considered"}, headers=_auth(admin_token))
    client.post(f"/delayed-cash/bills/{bill_ids[1]}/review", json={"decision": "needs_proof"}, headers=_auth(admin_token))

    db = TestingSessionLocal()
    try:
        from app.models.delayed_cash_billing import DelayedCashCenterPenalty, DelayedCashPenaltyRule

        cp = db.query(DelayedCashCenterPenalty).filter(DelayedCashCenterPenalty.id == cp_id).first()
        rule = db.query(DelayedCashPenaltyRule).filter(DelayedCashPenaltyRule.id == rule_id).first()
        import pytest as _pytest

        with _pytest.raises(calc_svc.ConfigurationError):
            calc_svc.recompute_validated_penalty(db, center_penalty=cp, rule=rule)
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Action Taken -- the complement of the pending review queue
# ---------------------------------------------------------------------------


def test_action_taken_only_shows_terminal_decisions(client):
    admin_token = _admin(client, "dcbrq_admin_at1", "dcbrq_admin_at1@example.com")
    cp_id, bill_ids, _ = _make_case_with_bills("at1", day_diffs=(1, 2, 3))

    client.post(f"/delayed-cash/bills/{bill_ids[0]}/review", json={"decision": "considered"}, headers=_auth(admin_token))
    client.post(f"/delayed-cash/bills/{bill_ids[1]}/review", json={"decision": "not_considered"}, headers=_auth(admin_token))
    client.post(f"/delayed-cash/bills/{bill_ids[2]}/review", json={"decision": "needs_proof"}, headers=_auth(admin_token))

    action_taken = client.get("/delayed-cash/bills/action-taken", headers=_auth(admin_token)).json()
    action_ids = {b["id"] for b in action_taken}
    assert bill_ids[0] in action_ids
    assert bill_ids[1] in action_ids
    assert bill_ids[2] not in action_ids  # needs_proof isn't terminal -- stays out

    queue_ids = {b["id"] for b in client.get("/delayed-cash/bills/review-queue", headers=_auth(admin_token)).json()}
    assert bill_ids[2] in queue_ids
    assert bill_ids[0] not in queue_ids
    assert bill_ids[1] not in queue_ids


def test_action_taken_can_be_scoped_to_a_batch(client):
    admin_token = _admin(client, "dcbrq_admin_at2", "dcbrq_admin_at2@example.com")
    cp_id_a, bill_ids_a, _ = _make_case_with_bills("at2a")
    cp_id_b, bill_ids_b, _ = _make_case_with_bills("at2b")

    client.post(f"/delayed-cash/bills/{bill_ids_a[0]}/review", json={"decision": "considered"}, headers=_auth(admin_token))
    client.post(f"/delayed-cash/bills/{bill_ids_b[0]}/review", json={"decision": "considered"}, headers=_auth(admin_token))

    db = TestingSessionLocal()
    try:
        batch_a_id = db.query(DelayedCashBill).filter(DelayedCashBill.id == bill_ids_a[0]).first().batch_id
    finally:
        db.close()

    scoped = client.get(
        "/delayed-cash/bills/action-taken", params={"batch_id": batch_a_id}, headers=_auth(admin_token)
    ).json()
    scoped_ids = {b["id"] for b in scoped}
    assert bill_ids_a[0] in scoped_ids
    assert bill_ids_b[0] not in scoped_ids


def test_action_taken_requires_vigilance_role(client):
    assert client.get("/delayed-cash/bills/action-taken").status_code == 401


def test_validated_penalty_succeeds_once_every_bill_is_terminal(client):
    admin_token = _admin(client, "dcbrq_admin9", "dcbrq_admin9@example.com")
    cp_id, bill_ids, rule_id = _make_case_with_bills("9", day_diffs=(1, 2))

    client.post(f"/delayed-cash/bills/{bill_ids[0]}/review", json={"decision": "not_considered"}, headers=_auth(admin_token))
    client.post(f"/delayed-cash/bills/{bill_ids[1]}/review", json={"decision": "considered"}, headers=_auth(admin_token))

    db = TestingSessionLocal()
    try:
        from app.models.delayed_cash_billing import DelayedCashCenterPenalty, DelayedCashPenaltyRule

        cp = db.query(DelayedCashCenterPenalty).filter(DelayedCashCenterPenalty.id == cp_id).first()
        rule = db.query(DelayedCashPenaltyRule).filter(DelayedCashPenaltyRule.id == rule_id).first()
        result = calc_svc.recompute_validated_penalty(db, center_penalty=cp, rule=rule)
        assert result.validated_penalty == Decimal("100")  # only the not_considered (1-day) bill counted
    finally:
        db.close()

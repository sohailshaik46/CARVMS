"""Tests for the Weekly Revenue Closure penalty calculator.

The two fixtures (tests/fixtures/weekly_revenue_closure_week{2,3}.json) are
extracted programmatically -- not hand-transcribed -- from the two real
reference workbooks the user supplied. Week 2 reconciles against the
source workbook's own rollup numbers with ZERO mismatches (verified
independently, see docs/CARVMS_WEEKLY_REVENUE_CLOSURE_FORMULA_ANALYSIS.md
S2). Week 3's fixture intentionally uses the mathematically CORRECT
distinct-center counts rather than the source workbook's own rollup
figures for 4 specific entries, because those 4 are confirmed arithmetic
errors in that file's pivot tables (documented in the same doc, S6.1) --
this suite asserts the corrected numbers, not the known-wrong ones.
"""

import json
import os
from datetime import date
from decimal import Decimal

from app.models.user import User
from app.services import weekly_revenue_closure_service as svc
from tests.conftest import TestingSessionLocal

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


def _load_fixture(name):
    with open(os.path.join(FIXTURES_DIR, name), "r", encoding="utf-8") as f:
        return json.load(f)


def _get_or_create_user(db, username="wrc_tester"):
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
# Rule lifecycle -- mirrors delayed_cash_penalty_service's own tests.
# ---------------------------------------------------------------------------


def test_rule_lifecycle_create_approve_get_active():
    db = TestingSessionLocal()
    try:
        user = _get_or_create_user(db, "wrc_lifecycle")
        rule = svc.create_rule(db, rule_version="WRC-TEST-v1", created_by=user)
        assert rule.status == "draft"
        assert rule.penalty_rate == svc.PROVEN_PENALTY_RATE

        svc.approve_rule(db, rule=rule, approver=user)
        active = svc.get_active_rule(db)
        assert active.id == rule.id
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Full reconciliation against both real reference weeks.
# ---------------------------------------------------------------------------


def _run_batch(db, rule, user, fixture, week_label):
    batch = svc.create_batch(
        db, period_start=date(2026, 7, 1), period_end=date(2026, 7, 31), week_label=week_label,
        rule=rule, created_by=user,
    )
    bill_inputs = [
        svc.RawBillIncidentInput(
            centre_code=b["centre_code"], centre_name=b["centre_name"], zone=b["zone"], cluster=b["cluster"],
            incident_date=date.fromisoformat(b["incident_date"]), mis_final_remark=b["mis_final_remark"],
            billed_sessions=b["billed_sessions"], daily_report=b["daily_report"], variance=b["variance"],
            raw_remark=b["raw_remark"], center_remarks=b["center_remarks"], penalty_remarks=b["penalty_remarks"],
        )
        for b in fixture["bill_incidents"]
    ]
    svc.record_bill_incidents(db, batch=batch, raw_incidents=bill_inputs)

    no_remark_inputs = [
        svc.RawNoRemarkIncidentInput(
            centre_code=n["centre_code"], centre_name=n["centre_name"], zone=n["zone"], cluster=n["cluster"],
            zonal_manager=n["zonal_manager"], center_manager=n["center_manager"],
            center_manager_npid=n["center_manager_npid"], incident_type=n["incident_type"],
            incident_count=n["incident_count"],
        )
        for n in fixture["no_remark_incidents"]
    ]
    svc.record_no_remark_incidents(db, batch=batch, raw_incidents=no_remark_inputs)

    center_penalties = svc.compute_center_penalties(db, batch=batch, rule=rule)
    role_penalties = svc.compute_role_penalties(db, batch=batch, rule=rule)
    return batch, center_penalties, role_penalties


def test_week2_center_penalties_reconcile_exactly():
    fixture = _load_fixture("weekly_revenue_closure_week2.json")
    db = TestingSessionLocal()
    try:
        user = _get_or_create_user(db, "wrc_week2")
        rule = svc.create_rule(db, rule_version="WRC-WEEK2", created_by=user)
        svc.approve_rule(db, rule=rule, approver=user)

        _, center_penalties, _ = _run_batch(db, rule, user, fixture, "Week 2 - Jul'26")

        assert len(center_penalties) == len(fixture["expected_center_penalties"])
        by_code = {cp.centre_code: cp for cp in center_penalties}
        for code, expected in fixture["expected_center_penalties"].items():
            cp = by_code[code]
            assert cp.not_considered_penalty == Decimal(str(expected["not_considered_penalty"])), code
            assert cp.no_remark_penalty == Decimal(str(expected["no_remark_penalty"])), code
    finally:
        db.close()


def test_week2_role_penalties_reconcile_exactly():
    """Week 2's rollups matched the source workbook's own stated numbers
    23/23 -- zero mismatches, verified independently before this test was
    written (see formula analysis doc S2)."""
    fixture = _load_fixture("weekly_revenue_closure_week2.json")
    db = TestingSessionLocal()
    try:
        user = _get_or_create_user(db, "wrc_week2_roles")
        rule = svc.create_rule(db, rule_version="WRC-WEEK2-ROLES", created_by=user)
        svc.approve_rule(db, rule=rule, approver=user)

        _, _, role_penalties = _run_batch(db, rule, user, fixture, "Week 2 - Jul'26")

        assert len(role_penalties) == len(fixture["expected_role_penalties"])
        actual_by_key = {(r.role, r.section, r.person_name): r for r in role_penalties}
        for expected in fixture["expected_role_penalties"]:
            key = (expected["role"], expected["section"], expected["person_name"])
            actual = actual_by_key[key]
            assert actual.distinct_center_count == expected["distinct_center_count"], key
            assert actual.penalty_amount == Decimal(str(expected["penalty_amount"])), key

        # Zonal Manager never escalates for "not_considered" (confirmed rule).
        assert not any(r.role == "zonal_manager" and r.section == "not_considered" for r in role_penalties)
    finally:
        db.close()


def test_week3_center_penalties_reconcile_exactly():
    fixture = _load_fixture("weekly_revenue_closure_week3.json")
    db = TestingSessionLocal()
    try:
        user = _get_or_create_user(db, "wrc_week3")
        rule = svc.create_rule(db, rule_version="WRC-WEEK3", created_by=user)
        svc.approve_rule(db, rule=rule, approver=user)

        _, center_penalties, _ = _run_batch(db, rule, user, fixture, "Week 3 - Jul'26")

        assert len(center_penalties) == len(fixture["expected_center_penalties"])
        by_code = {cp.centre_code: cp for cp in center_penalties}
        for code, expected in fixture["expected_center_penalties"].items():
            cp = by_code[code]
            assert cp.not_considered_penalty == Decimal(str(expected["not_considered_penalty"])), code
            assert cp.no_remark_penalty == Decimal(str(expected["no_remark_penalty"])), code
    finally:
        db.close()


def test_week3_role_penalties_reconcile_to_corrected_counts():
    """Week 3's own rollup pivots have 4 confirmed arithmetic errors
    (undercounts) -- this asserts the CALCULATOR's mathematically correct
    output, which deliberately differs from those 4 specific stated
    figures in the source file. See formula analysis doc S6.1 for the full
    per-person before/after table."""
    fixture = _load_fixture("weekly_revenue_closure_week3.json")
    db = TestingSessionLocal()
    try:
        user = _get_or_create_user(db, "wrc_week3_roles")
        rule = svc.create_rule(db, rule_version="WRC-WEEK3-ROLES", created_by=user)
        svc.approve_rule(db, rule=rule, approver=user)

        _, _, role_penalties = _run_batch(db, rule, user, fixture, "Week 3 - Jul'26")

        actual_by_key = {(r.role, r.section, r.person_name): r for r in role_penalties}
        for expected in fixture["expected_role_penalties"]:
            key = (expected["role"], expected["section"], expected["person_name"])
            actual = actual_by_key[key]
            assert actual.distinct_center_count == expected["distinct_center_count"], key
            assert actual.penalty_amount == Decimal(str(expected["penalty_amount"])), key

        # The 4 specific corrections, called out explicitly (not just implied
        # by the loop above) -- each one intentionally differs from the
        # source workbook's own stated (wrong) figure.
        corrections = {
            ("cluster_manager", "no_remark", "Ankit Kumar Singh"): 4,  # sheet stated 3
            ("cluster_manager", "no_remark", "Yashwant"): 2,  # sheet stated 1
            ("zonal_manager", "no_remark", "Krunal"): 4,  # sheet stated 2
            ("zonal_manager", "no_remark", "Nishant Kumar Singh"): 7,  # sheet stated 6
        }
        for key, correct_count in corrections.items():
            assert actual_by_key[key].distinct_center_count == correct_count, key
    finally:
        db.close()


def test_grand_total_penalty_matches_independent_recomputation():
    """A coarser, independent cross-check on top of the per-entity
    assertions above: the total rupee-equivalent penalty rate summed
    across every center + role entry for each week matches summing the
    fixture's own expected values (itself independently recomputed from
    raw membership, not copied from the sheet's stated totals)."""
    for fixture_name in ("weekly_revenue_closure_week2.json", "weekly_revenue_closure_week3.json"):
        fixture = _load_fixture(fixture_name)
        db = TestingSessionLocal()
        try:
            user = _get_or_create_user(db, f"wrc_grand_{fixture_name}")
            rule = svc.create_rule(db, rule_version=f"WRC-GRAND-{fixture_name}", created_by=user)
            svc.approve_rule(db, rule=rule, approver=user)

            _, center_penalties, role_penalties = _run_batch(db, rule, user, fixture, fixture_name)

            actual_total = sum((cp.not_considered_penalty + cp.no_remark_penalty for cp in center_penalties), Decimal("0"))
            actual_total += sum((r.penalty_amount for r in role_penalties), Decimal("0"))

            expected_total = sum(
                Decimal(str(v["not_considered_penalty"])) + Decimal(str(v["no_remark_penalty"]))
                for v in fixture["expected_center_penalties"].values()
            )
            expected_total += sum(Decimal(str(r["penalty_amount"])) for r in fixture["expected_role_penalties"])

            assert actual_total == expected_total, fixture_name
        finally:
            db.close()


# ---------------------------------------------------------------------------
# Data-quality behaviors -- "Considered" excludes; flat-per-center; both
# sections independent.
# ---------------------------------------------------------------------------


def test_considered_incident_produces_no_penalty():
    db = TestingSessionLocal()
    try:
        user = _get_or_create_user(db, "wrc_considered")
        rule = svc.create_rule(db, rule_version="WRC-CONSIDERED", created_by=user)
        svc.approve_rule(db, rule=rule, approver=user)
        batch = svc.create_batch(
            db, period_start=date(2026, 7, 1), period_end=date(2026, 7, 31), week_label="Test Week",
            rule=rule, created_by=user,
        )
        svc.record_bill_incidents(
            db, batch=batch,
            raw_incidents=[
                svc.RawBillIncidentInput(
                    centre_code="TEST-C", centre_name="Test Center", cluster="Test Cluster",
                    incident_date=date(2026, 7, 5), mis_final_remark="bill_pending",
                    penalty_remarks="Considered - Proof Available",
                )
            ],
        )
        center_penalties = svc.compute_center_penalties(db, batch=batch, rule=rule)
        assert center_penalties == []
    finally:
        db.close()


def test_multiple_not_considered_incidents_same_center_still_flat_penalty():
    db = TestingSessionLocal()
    try:
        user = _get_or_create_user(db, "wrc_flat")
        rule = svc.create_rule(db, rule_version="WRC-FLAT", created_by=user)
        svc.approve_rule(db, rule=rule, approver=user)
        batch = svc.create_batch(
            db, period_start=date(2026, 7, 1), period_end=date(2026, 7, 31), week_label="Test Week",
            rule=rule, created_by=user,
        )
        svc.record_bill_incidents(
            db, batch=batch,
            raw_incidents=[
                svc.RawBillIncidentInput(
                    centre_code="TEST-C", centre_name="Test Center", cluster="Test Cluster",
                    incident_date=date(2026, 7, d), mis_final_remark="bill_pending",
                    penalty_remarks="Not Considered - Center Lapse",
                )
                for d in (5, 6, 7)
            ],
        )
        center_penalties = svc.compute_center_penalties(db, batch=batch, rule=rule)
        assert len(center_penalties) == 1
        assert center_penalties[0].not_considered_penalty == svc.PROVEN_PENALTY_RATE  # not 3x
    finally:
        db.close()


def test_center_can_be_penalized_under_both_sections_independently():
    db = TestingSessionLocal()
    try:
        user = _get_or_create_user(db, "wrc_both_sections")
        rule = svc.create_rule(db, rule_version="WRC-BOTH", created_by=user)
        svc.approve_rule(db, rule=rule, approver=user)
        batch = svc.create_batch(
            db, period_start=date(2026, 7, 1), period_end=date(2026, 7, 31), week_label="Test Week",
            rule=rule, created_by=user,
        )
        svc.record_bill_incidents(
            db, batch=batch,
            raw_incidents=[
                svc.RawBillIncidentInput(
                    centre_code="TEST-C", centre_name="Test Center", cluster="Test Cluster",
                    incident_date=date(2026, 7, 5), mis_final_remark="bill_pending",
                    penalty_remarks="Not Considered - Center Lapse",
                )
            ],
        )
        svc.record_no_remark_incidents(
            db, batch=batch,
            raw_incidents=[
                svc.RawNoRemarkIncidentInput(
                    centre_code="TEST-C", centre_name="Test Center", cluster="Test Cluster",
                    incident_type="daily_report_not_sent",
                )
            ],
        )
        center_penalties = svc.compute_center_penalties(db, batch=batch, rule=rule)
        assert len(center_penalties) == 1
        cp = center_penalties[0]
        assert cp.not_considered_penalty == svc.PROVEN_PENALTY_RATE
        assert cp.no_remark_penalty == svc.PROVEN_PENALTY_RATE
    finally:
        db.close()

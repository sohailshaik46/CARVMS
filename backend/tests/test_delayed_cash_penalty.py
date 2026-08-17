"""Tests for the Delayed Cash Billing penalty calculator.

The reference fixture (tests/fixtures/delayed_cash_reference_bills.json) is
the exact (centre_code -> day_differences) breakdown extracted from the real
reference workbook the user supplied -- 93 centers, 585 bills, Rs.137,900
total. See docs/CARVMS_DELAYED_CASH_PENALTY_FORMULA_ANALYSIS.md for the full
derivation. Nothing here is hand-typed or approximated; every number below is
either the proven formula's output or copied verbatim from that fixture.
"""

import json
import os
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.models.delayed_cash_billing import DelayedCashCenterPenalty
from app.models.user import User
from app.services import delayed_cash_penalty_service as svc
from app.services.delayed_cash_penalty_service import BillRecord
from tests.conftest import TestingSessionLocal

FIXTURE_PATH = os.path.join(os.path.dirname(__file__), "fixtures", "delayed_cash_reference_bills.json")

REFERENCE_TOTAL_BILLS = 585
REFERENCE_TOTAL_PENALTY = Decimal("137900")

NAMED_CENTERS = {
    "106-BH-PTN-KHM-C": Decimal("2200"),   # Khemnichak
    "107-JH-RNC-MRD-C": Decimal("500"),    # Main Road Ranchi
    "11-TN-CHE-TNG-C": Decimal("100"),     # T Nagar Chennai
    "123-BH-MTH-BYP-C": Decimal("1000"),   # Motihari
    "139-OD-BLS-KRD-C": Decimal("900"),    # Balasore
    "176-TN-CHE-KPK3-C": Decimal("3600"),  # Kilpauk3
    "196-KA-BLR-STN-S": Decimal("8500"),   # Shantinagar Bengaluru
    "213-GJ-VDD-WGD-C": Decimal("13900"),  # Waghodia Vadodara
    "54-TN-CMB-GPP-C": Decimal("15800"),   # Coimbatore
}

ALL_DELAY_BUCKETS = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 20, 21, 25, 27, 28, 29, 34]


def _load_fixture():
    with open(FIXTURE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _make_rule(rule_version="TEST-v1"):
    """A bare (non-persisted) rule object -- calculate_penalty() is pure and
    only reads rate_per_day/rule_version off it, so a plain object works
    fine for the pure-calculator tests."""

    class _Rule:
        pass

    r = _Rule()
    r.rate_per_day = svc.PROVEN_RATE_PER_DAY
    r.rule_version = rule_version
    return r


# ---------------------------------------------------------------------------
# 1. One test per delay bucket actually present in the reference data
#    (requirement #19: "Continue for EVERY delay bucket in the source").
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("day_difference", ALL_DELAY_BUCKETS)
def test_bucket_rate_is_day_times_100(day_difference):
    rule = _make_rule()
    result = svc.calculate_penalty([BillRecord(sales_bill="X", day_difference=day_difference)], rule)
    assert result.calculated_penalty == Decimal(day_difference) * Decimal("100")
    assert result.total_bills == 1
    assert result.delay_distribution == {day_difference: 1}


# ---------------------------------------------------------------------------
# 2. Every named reference center reproduces its exact reference penalty.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("centre_code,expected_penalty", list(NAMED_CENTERS.items()))
def test_named_center_matches_reference(centre_code, expected_penalty):
    fixture = _load_fixture()
    entry = fixture[centre_code]
    rule = _make_rule()
    records = [
        BillRecord(sales_bill=f"{centre_code}-{i}", day_difference=dd)
        for i, dd in enumerate(entry["day_differences"])
    ]
    result = svc.calculate_penalty(records, rule)
    assert result.calculated_penalty == expected_penalty, (
        f"{centre_code} ({entry['name']}): expected Rs.{expected_penalty}, got Rs.{result.calculated_penalty}"
    )
    assert result.total_bills == len(entry["day_differences"])


# ---------------------------------------------------------------------------
# 3. Full reference dataset: all 93 centers / 585 bills / Rs.137,900.
# ---------------------------------------------------------------------------


def test_full_reference_dataset_reconciles_exactly():
    fixture = _load_fixture()
    rule = _make_rule()

    assert len(fixture) == 93, f"Expected 93 reference centers, fixture has {len(fixture)}"

    grand_total_bills = 0
    grand_total_penalty = Decimal("0")
    mismatches = []

    for centre_code, entry in fixture.items():
        records = [
            BillRecord(sales_bill=f"{centre_code}-{i}", day_difference=dd)
            for i, dd in enumerate(entry["day_differences"])
        ]
        result = svc.calculate_penalty(records, rule)
        grand_total_bills += result.total_bills
        grand_total_penalty += result.calculated_penalty

    assert grand_total_bills == REFERENCE_TOTAL_BILLS
    assert grand_total_penalty == REFERENCE_TOTAL_PENALTY
    assert not mismatches


def test_calculation_trace_explains_every_bill():
    rule = _make_rule()
    records = [BillRecord(sales_bill="C0001-B40936", day_difference=1)]
    result = svc.calculate_penalty(records, rule)
    assert len(result.calculation_trace) == 1
    trace = result.calculation_trace[0]
    assert trace.sales_bill == "C0001-B40936"
    assert trace.day_difference == 1
    assert trace.rate_per_day == Decimal("100.00")
    assert trace.penalty == Decimal("100")


# ---------------------------------------------------------------------------
# 4. Data-quality cross-check (source day_difference vs. date arithmetic).
# ---------------------------------------------------------------------------


def test_day_difference_validation_matches_when_consistent():
    calculated, check, quality = svc.validate_day_difference(
        bill_date=date(2026, 7, 8), created_date=date(2026, 7, 9), source_day_difference=1
    )
    assert calculated == 1
    assert check == "match"
    assert quality == "ok"


def test_day_difference_validation_flags_mismatch_without_overwriting():
    calculated, check, quality = svc.validate_day_difference(
        bill_date=date(2026, 7, 8), created_date=date(2026, 7, 9), source_day_difference=5
    )
    # The calculated value (1) differs from the (deliberately wrong) source
    # value (5) -- the function returns the calculated value AND flags it;
    # the caller is responsible for keeping source_day_difference untouched.
    assert calculated == 1
    assert check == "mismatch"
    assert quality == "flagged"


# ---------------------------------------------------------------------------
# 5. DB-integration: rule lifecycle, ingestion, aggregation, cap application.
# ---------------------------------------------------------------------------


def _get_or_create_user(db, username="dcb_tester"):
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


def test_no_approved_rule_raises():
    db = TestingSessionLocal()
    try:
        with pytest.raises(svc.NoApprovedRuleError):
            svc.get_active_rule(db)
    finally:
        db.close()


def test_rule_lifecycle_create_approve_get_active():
    db = TestingSessionLocal()
    try:
        user = _get_or_create_user(db)
        rule = svc.create_rule(db, rule_version="DCB-TEST-v1", created_by=user)
        assert rule.status == "draft"
        assert rule.rate_per_day == svc.PROVEN_RATE_PER_DAY
        assert rule.monthly_cap_percentage == svc.PROVEN_MONTHLY_CAP_PERCENTAGE

        with pytest.raises(svc.NoApprovedRuleError):
            svc.get_active_rule(db)

        svc.approve_rule(db, rule=rule, approver=user)
        active = svc.get_active_rule(db)
        assert active.id == rule.id
    finally:
        db.close()


def test_ingest_and_aggregate_reproduces_khemnichak():
    db = TestingSessionLocal()
    try:
        user = _get_or_create_user(db, "dcb_tester2")
        rule = svc.create_rule(db, rule_version="DCB-TEST-v2", created_by=user)
        svc.approve_rule(db, rule=rule, approver=user)

        batch = svc.create_upload_batch(
            db,
            period_start=date(2026, 7, 1),
            period_end=date(2026, 7, 31),
            source_filename="test.xlsx",
            rule=rule,
            uploaded_by=user,
        )

        fixture = _load_fixture()
        entry = fixture["106-BH-PTN-KHM-C"]
        raw_bills = []
        for i, dd in enumerate(entry["day_differences"]):
            bill_date = date(2026, 7, 1)
            created = bill_date + timedelta(days=dd)
            raw_bills.append(
                svc.RawBillInput(
                    centre_code="106-BH-PTN-KHM-C",
                    centre_name=entry["name"],
                    sales_bill=f"KHM-{i}",
                    bill_date=bill_date,
                    bill_created_time=datetime.combine(created, datetime.min.time(), tzinfo=timezone.utc),
                    created_date=created,
                    source_day_difference=dd,
                )
            )
        bills = svc.ingest_bills(db, batch=batch, rule=rule, raw_bills=raw_bills)
        assert len(bills) == 18
        assert all(b.difference_check == "match" for b in bills)
        assert all(b.data_quality_status == "ok" for b in bills)

        center_penalties = svc.compute_center_penalties(db, batch=batch, rule=rule)
        assert len(center_penalties) == 1
        cp = center_penalties[0]
        assert cp.total_bills == 18
        assert cp.calculated_penalty == Decimal("2200")
        assert cp.penalty_status == "published"
        assert cp.validated_penalty is None
        assert cp.final_penalty is None
    finally:
        db.close()


def test_ingest_flags_mismatched_day_difference_without_overwriting_source():
    db = TestingSessionLocal()
    try:
        user = _get_or_create_user(db, "dcb_tester3")
        rule = svc.create_rule(db, rule_version="DCB-TEST-v3", created_by=user)
        svc.approve_rule(db, rule=rule, approver=user)
        batch = svc.create_upload_batch(
            db, period_start=date(2026, 7, 1), period_end=date(2026, 7, 31),
            source_filename="test.xlsx", rule=rule, uploaded_by=user,
        )

        bill_date = date(2026, 7, 1)
        created = date(2026, 7, 2)  # true delay = 1 day
        raw = svc.RawBillInput(
            centre_code="X-C", centre_name="Test Center", sales_bill="BAD-1",
            bill_date=bill_date,
            bill_created_time=datetime.combine(created, datetime.min.time(), tzinfo=timezone.utc),
            created_date=created,
            source_day_difference=9,  # deliberately wrong
        )
        bills = svc.ingest_bills(db, batch=batch, rule=rule, raw_bills=[raw])
        bill = bills[0]

        # source value preserved exactly as uploaded, never overwritten
        assert bill.source_day_difference == 9
        assert bill.calculated_day_difference == 1
        assert bill.difference_check == "mismatch"
        assert bill.data_quality_status == "flagged"
        # penalty computed from the calculated (trustworthy) value, not the
        # unverified source value
        assert bill.calculated_penalty == Decimal("100")
    finally:
        db.close()


def test_validated_penalty_excludes_considered_bills():
    db = TestingSessionLocal()
    try:
        user = _get_or_create_user(db, "dcb_tester4")
        rule = svc.create_rule(db, rule_version="DCB-TEST-v4", created_by=user)
        svc.approve_rule(db, rule=rule, approver=user)
        batch = svc.create_upload_batch(
            db, period_start=date(2026, 7, 1), period_end=date(2026, 7, 31),
            source_filename="test.xlsx", rule=rule, uploaded_by=user,
        )

        bill_date = date(2026, 7, 1)
        raw_bills = [
            svc.RawBillInput(
                centre_code="Y-C", centre_name="Test Center 2", sales_bill="Y-1",
                bill_date=bill_date,
                bill_created_time=datetime.combine(bill_date + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc),
                created_date=bill_date + timedelta(days=1),
                source_day_difference=1,
                penalty_remarks="Considered - Zero Billing",
            ),
            svc.RawBillInput(
                centre_code="Y-C", centre_name="Test Center 2", sales_bill="Y-2",
                bill_date=bill_date,
                bill_created_time=datetime.combine(bill_date + timedelta(days=2), datetime.min.time(), tzinfo=timezone.utc),
                created_date=bill_date + timedelta(days=2),
                source_day_difference=2,
                penalty_remarks="Not Considered - Center Lapse",
            ),
        ]
        svc.ingest_bills(db, batch=batch, rule=rule, raw_bills=raw_bills)
        center_penalties = svc.compute_center_penalties(db, batch=batch, rule=rule)
        cp = center_penalties[0]

        # Publishing stage includes BOTH bills (100 + 200 = 300), matching
        # the reference workbook's Penalty Data behavior.
        assert cp.calculated_penalty == Decimal("300")

        cp = svc.recompute_validated_penalty(db, center_penalty=cp, rule=rule)
        # Validated stage excludes the "Considered" bill -> only the Rs.200
        # Not-Considered bill survives.
        assert cp.validated_penalty == Decimal("200")
        assert cp.penalty_status == "validated"
    finally:
        db.close()


def test_validated_penalty_raises_if_bills_not_reviewed():
    db = TestingSessionLocal()
    try:
        user = _get_or_create_user(db, "dcb_tester5")
        rule = svc.create_rule(db, rule_version="DCB-TEST-v5", created_by=user)
        svc.approve_rule(db, rule=rule, approver=user)
        batch = svc.create_upload_batch(
            db, period_start=date(2026, 7, 1), period_end=date(2026, 7, 31),
            source_filename="test.xlsx", rule=rule, uploaded_by=user,
        )
        bill_date = date(2026, 7, 1)
        raw = svc.RawBillInput(
            centre_code="Z-C", centre_name="Test Center 3", sales_bill="Z-1",
            bill_date=bill_date,
            bill_created_time=datetime.combine(bill_date + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc),
            created_date=bill_date + timedelta(days=1),
            source_day_difference=1,
            # no penalty_remarks -- not yet reviewed
        )
        svc.ingest_bills(db, batch=batch, rule=rule, raw_bills=[raw])
        center_penalties = svc.compute_center_penalties(db, batch=batch, rule=rule)

        with pytest.raises(svc.ConfigurationError):
            svc.recompute_validated_penalty(db, center_penalty=center_penalties[0], rule=rule)
    finally:
        db.close()


def test_monthly_cap_applies_minimum_and_requires_validated_penalty_first():
    db = TestingSessionLocal()
    try:
        user = _get_or_create_user(db, "dcb_tester6")
        rule = svc.create_rule(db, rule_version="DCB-TEST-v6", created_by=user)
        svc.approve_rule(db, rule=rule, approver=user)
        batch = svc.create_upload_batch(
            db, period_start=date(2026, 7, 1), period_end=date(2026, 7, 31),
            source_filename="test.xlsx", rule=rule, uploaded_by=user,
        )
        bill_date = date(2026, 7, 1)
        raw = svc.RawBillInput(
            centre_code="CAP-C", centre_name="Cap Test Center", sales_bill="CAP-1",
            bill_date=bill_date,
            bill_created_time=datetime.combine(bill_date + timedelta(days=10), datetime.min.time(), tzinfo=timezone.utc),
            created_date=bill_date + timedelta(days=10),
            source_day_difference=10,
            penalty_remarks="Not Considered - Center Lapse",
        )
        svc.ingest_bills(db, batch=batch, rule=rule, raw_bills=[raw])
        center_penalties = svc.compute_center_penalties(db, batch=batch, rule=rule)
        cp = center_penalties[0]

        # Cap not applied yet -- must not silently fall back to anything.
        with pytest.raises(svc.ConfigurationError):
            svc.apply_monthly_cap(db, center_penalty=cp, monthly_cap_amount=Decimal("500"))

        cp = svc.recompute_validated_penalty(db, center_penalty=cp, rule=rule)
        assert cp.validated_penalty == Decimal("1000")  # 10 days x Rs.100

        # Cap below the validated penalty -> final_penalty is the cap.
        cp = svc.apply_monthly_cap(db, center_penalty=cp, monthly_cap_amount=Decimal("500"))
        assert cp.final_penalty == Decimal("500")
        assert cp.penalty_status == "capped"

        # Cap above the validated penalty -> final_penalty is the validated amount.
        cp.validated_penalty = Decimal("1000")
        db.commit()
        cp = svc.apply_monthly_cap(db, center_penalty=cp, monthly_cap_amount=Decimal("5000"))
        assert cp.final_penalty == Decimal("1000")
    finally:
        db.close()


def test_reconciliation_pass_and_fail():
    db = TestingSessionLocal()
    try:
        user = _get_or_create_user(db, "dcb_tester7")
        rule = svc.create_rule(db, rule_version="DCB-TEST-v7", created_by=user)
        svc.approve_rule(db, rule=rule, approver=user)
        batch = svc.create_upload_batch(
            db, period_start=date(2026, 7, 1), period_end=date(2026, 7, 31),
            source_filename="test.xlsx", rule=rule, uploaded_by=user,
        )
        bill_date = date(2026, 7, 1)
        raw = svc.RawBillInput(
            centre_code="REC-C", centre_name="Reconcile Test Center", sales_bill="REC-1",
            bill_date=bill_date,
            bill_created_time=datetime.combine(bill_date + timedelta(days=2), datetime.min.time(), tzinfo=timezone.utc),
            created_date=bill_date + timedelta(days=2),
            source_day_difference=2,
        )
        svc.ingest_bills(db, batch=batch, rule=rule, raw_bills=[raw])
        svc.compute_center_penalties(db, batch=batch, rule=rule)

        passing = svc.reconcile(db, batch=batch, reference_total_bills=1, reference_total_penalty=Decimal("200"))
        assert passing.status == "PASS"
        assert passing.difference == 0

        failing = svc.reconcile(db, batch=batch, reference_total_bills=1, reference_total_penalty=Decimal("999"))
        assert failing.status == "FAIL"
        assert failing.difference == Decimal("200") - Decimal("999")
    finally:
        db.close()


def test_full_585_bill_dataset_ingests_and_reconciles_in_db():
    """The end-to-end proof: ingest all 585 reference bills through the real
    DB-backed pipeline (not the pure calculator in isolation) and confirm the
    system reproduces Rs.137,900 exactly, matching the reference total."""
    db = TestingSessionLocal()
    try:
        user = _get_or_create_user(db, "dcb_tester_full")
        rule = svc.create_rule(db, rule_version="DCB-TEST-FULL", created_by=user)
        svc.approve_rule(db, rule=rule, approver=user)
        batch = svc.create_upload_batch(
            db, period_start=date(2026, 7, 1), period_end=date(2026, 7, 31),
            source_filename="reference.xlsx", rule=rule, uploaded_by=user,
        )

        fixture = _load_fixture()
        raw_bills = []
        bill_date = date(2026, 7, 1)
        for centre_code, entry in fixture.items():
            for i, dd in enumerate(entry["day_differences"]):
                created = bill_date + timedelta(days=dd)
                raw_bills.append(
                    svc.RawBillInput(
                        centre_code=centre_code,
                        centre_name=entry["name"],
                        sales_bill=f"{centre_code}-{i}",
                        bill_date=bill_date,
                        bill_created_time=datetime.combine(created, datetime.min.time(), tzinfo=timezone.utc),
                        created_date=created,
                        source_day_difference=dd,
                    )
                )

        svc.ingest_bills(db, batch=batch, rule=rule, raw_bills=raw_bills)
        center_penalties = svc.compute_center_penalties(db, batch=batch, rule=rule)

        assert len(center_penalties) == 93
        reconciliation = svc.reconcile(
            db, batch=batch,
            reference_total_bills=REFERENCE_TOTAL_BILLS,
            reference_total_penalty=REFERENCE_TOTAL_PENALTY,
        )
        assert reconciliation.status == "PASS"
        assert reconciliation.system_total_bills == REFERENCE_TOTAL_BILLS
        assert reconciliation.system_total_penalty == REFERENCE_TOTAL_PENALTY
        assert reconciliation.difference == 0
    finally:
        db.close()

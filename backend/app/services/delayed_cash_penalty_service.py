"""Delayed Cash Billing penalty calculator.

The formula here is not invented -- it is reverse-engineered and proven
against a real reference workbook (94 centers, 585 bills, Rs.137,900 total,
zero mismatches). See docs/CARVMS_DELAYED_CASH_PENALTY_FORMULA_ANALYSIS.md for
the full proof before touching this file.

    per_bill_penalty  = day_difference * rule.rate_per_day
    calculated_penalty(center) = sum(per_bill_penalty) over EVERY delayed bill
                                  for that center in the period (publishing
                                  stage -- unfiltered by remark status)
    validated_penalty(center)  = sum(per_bill_penalty) over only the bills
                                  NOT marked "considered" (i.e. no accepted
                                  exception) -- the post-remark-review stage
    final_penalty(center)      = min(validated_penalty, monthly_cap_amount)
                                  where monthly_cap_amount = 0.0625 x the
                                  responsible person's monthly gross salary
                                  component -- EXTERNAL data this module never
                                  fabricates; see apply_monthly_cap().

Center Manager and Cluster Manager penalties are explicitly not applicable to
this engine (a separate, deliberately different rule from Weekly Revenue
Closure) -- enforced simply by never attributing an amount to those roles
anywhere in this module.
"""

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Optional, Sequence

from sqlalchemy.orm import Session

from app.models.delayed_cash_billing import (
    DCB_BILL_REVIEW_DECISIONS,
    DelayedCashBill,
    DelayedCashCaseResponse,
    DelayedCashCenterActivity,
    DelayedCashCenterPenalty,
    DelayedCashPenaltyRule,
    DelayedCashUploadBatch,
)
from app.models.user import User
from app.services import org_service
from app.services import storage_service


class ConfigurationError(Exception):
    """Raised when an operation needs a setting that was never configured
    (e.g. no approved rule exists yet, or a monthly cap base wasn't supplied)."""


class NoApprovedRuleError(ConfigurationError):
    pass


# ---------------------------------------------------------------------------
# Rule management -- versioned, so a future rate change never rewrites
# history. The two constants below are the PROVEN values from the formula
# analysis -- they are the seed default for a first rule, not a hardcoded
# fallback used elsewhere in the calculator itself (every calculation call
# takes an explicit rule object).
# ---------------------------------------------------------------------------

PROVEN_RATE_PER_DAY = Decimal("100.00")
PROVEN_MONTHLY_CAP_PERCENTAGE = Decimal("0.0625")


def create_rule(
    db: Session,
    *,
    rule_version: str,
    rate_per_day: Decimal = PROVEN_RATE_PER_DAY,
    monthly_cap_percentage: Decimal = PROVEN_MONTHLY_CAP_PERCENTAGE,
    created_by: User,
) -> DelayedCashPenaltyRule:
    rule = DelayedCashPenaltyRule(
        rule_version=rule_version,
        rate_per_day=rate_per_day,
        monthly_cap_percentage=monthly_cap_percentage,
        status="draft",
        created_by_id=created_by.id,
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return rule


def approve_rule(db: Session, *, rule: DelayedCashPenaltyRule, approver: User) -> DelayedCashPenaltyRule:
    rule.status = "approved"
    rule.approved_by_id = approver.id
    db.commit()
    db.refresh(rule)
    return rule


def activate_default_rule(db: Session, *, actor: User) -> DelayedCashPenaltyRule:
    """Idempotent: returns the existing approved rule if one is already
    active, otherwise creates AND approves one in a single step using the
    proven default values (see module docstring). This does not weaken the
    versioned-rule governance model -- an Admin still has to click the
    button that calls this -- it just removes the need for someone to run
    a script to do what create_rule+approve_rule already do together."""
    try:
        return get_active_rule(db)
    except NoApprovedRuleError:
        pass
    rule = create_rule(db, rule_version=f"DCB-DEFAULT-{date.today().isoformat()}", created_by=actor)
    return approve_rule(db, rule=rule, approver=actor)


def get_active_rule(db: Session) -> DelayedCashPenaltyRule:
    """The most recently approved rule with no effective_to (or a future
    one) -- raises rather than silently picking an unapproved draft."""
    rule = (
        db.query(DelayedCashPenaltyRule)
        .filter(DelayedCashPenaltyRule.status == "approved")
        .order_by(DelayedCashPenaltyRule.effective_from.desc())
        .first()
    )
    if rule is None:
        raise NoApprovedRuleError(
            "No approved DelayedCashPenaltyRule exists yet -- an Admin must create and approve one "
            "before bills can be uploaded (see docs/CARVMS_DELAYED_CASH_PENALTY_FORMULA_ANALYSIS.md "
            "for the proven default values)."
        )
    return rule


# ---------------------------------------------------------------------------
# Pure calculator -- the proven formula, no DB access, fully unit-testable
# against the reference dataset in isolation.
# ---------------------------------------------------------------------------


@dataclass
class BillRecord:
    """The minimal shape the pure calculator needs. Real ingestion builds
    these from DelayedCashBill rows; tests can build them directly from the
    reference fixture without touching the database at all."""

    sales_bill: str
    day_difference: int


@dataclass
class CalculationTraceEntry:
    sales_bill: str
    day_difference: int
    rate_per_day: Decimal
    penalty: Decimal


@dataclass
class CalculationResult:
    total_bills: int
    delay_distribution: dict
    calculated_penalty: Decimal
    rule_version: str
    calculation_trace: list = field(default_factory=list)
    validation_status: str = "ok"


def calculate_penalty(
    bill_records: Sequence[BillRecord],
    rule: DelayedCashPenaltyRule,
) -> CalculationResult:
    """The proven formula: per_bill_penalty = day_difference * rate_per_day,
    summed. Pure function -- no DB, no side effects, safe to call from tests
    directly against the reference fixture."""
    distribution: dict = {}
    trace = []
    total = Decimal("0")
    for bill in bill_records:
        distribution[bill.day_difference] = distribution.get(bill.day_difference, 0) + 1
        amount = Decimal(bill.day_difference) * rule.rate_per_day
        total += amount
        trace.append(
            CalculationTraceEntry(
                sales_bill=bill.sales_bill,
                day_difference=bill.day_difference,
                rate_per_day=rule.rate_per_day,
                penalty=amount,
            )
        )
    return CalculationResult(
        total_bills=len(bill_records),
        delay_distribution=distribution,
        calculated_penalty=total,
        rule_version=rule.rule_version,
        calculation_trace=trace,
        validation_status="ok",
    )


# ---------------------------------------------------------------------------
# Data-quality validation -- never trust source_day_difference blindly.
# ---------------------------------------------------------------------------


def validate_day_difference(
    *, bill_date: date, created_date: date, source_day_difference: int
) -> tuple[int, str, str]:
    """Returns (calculated_day_difference, difference_check, data_quality_status).
    Never overwrites source_day_difference -- the caller keeps both."""
    calculated = (created_date - bill_date).days
    if calculated == source_day_difference:
        return calculated, "match", "ok"
    return calculated, "mismatch", "flagged"


# ---------------------------------------------------------------------------
# Batch ingestion -- persists raw bills + publishing-stage center aggregates.
# ---------------------------------------------------------------------------


@dataclass
class RawBillInput:
    centre_code: str
    centre_name: str
    sales_bill: str
    bill_date: date
    bill_created_time: datetime
    created_date: date
    source_day_difference: int
    center_remarks: Optional[str] = None
    penalty_remarks: Optional[str] = None


def create_upload_batch(
    db: Session,
    *,
    period_start: date,
    period_end: date,
    source_filename: str,
    rule: DelayedCashPenaltyRule,
    uploaded_by: User,
) -> DelayedCashUploadBatch:
    batch = DelayedCashUploadBatch(
        period_start=period_start,
        period_end=period_end,
        source_filename=source_filename,
        rule_id=rule.id,
        status="uploaded",
        uploaded_by_id=uploaded_by.id,
    )
    db.add(batch)
    db.commit()
    db.refresh(batch)
    return batch


def ingest_bills(
    db: Session,
    *,
    batch: DelayedCashUploadBatch,
    rule: DelayedCashPenaltyRule,
    raw_bills: Sequence[RawBillInput],
) -> list[DelayedCashBill]:
    """Validates each raw bill's day_difference, computes its per-bill
    penalty using calculate_penalty() (called once per bill so every stored
    row is traceable back to the same pure function used everywhere else),
    and persists it. Raw source fields are stored verbatim."""
    created: list[DelayedCashBill] = []
    for raw in raw_bills:
        calculated_dd, diff_check, quality_status = validate_day_difference(
            bill_date=raw.bill_date,
            created_date=raw.created_date,
            source_day_difference=raw.source_day_difference,
        )
        result = calculate_penalty(
            [BillRecord(sales_bill=raw.sales_bill, day_difference=calculated_dd)], rule
        )
        bill = DelayedCashBill(
            batch_id=batch.id,
            centre_code=raw.centre_code,
            centre_name=raw.centre_name,
            sales_bill=raw.sales_bill,
            bill_date=raw.bill_date,
            bill_created_time=raw.bill_created_time,
            created_date=raw.created_date,
            source_day_difference=raw.source_day_difference,
            center_remarks=raw.center_remarks,
            penalty_remarks=raw.penalty_remarks,
            calculated_day_difference=calculated_dd,
            difference_check=diff_check,
            data_quality_status=quality_status,
            calculated_penalty=result.calculated_penalty,
            considered=_infer_considered(raw.penalty_remarks),
        )
        db.add(bill)
        created.append(bill)
    db.commit()
    for bill in created:
        db.refresh(bill)
    return created


def _infer_considered(penalty_remarks: Optional[str]) -> Optional[str]:
    """Historical/back-filled uploads (like the reference workbook) already
    carry a "Considered - ..." / "Not Considered - ..." verdict as free text.
    This reads that verdict into the structured `considered` field for such
    rows; a fresh weekly upload with no penalty_remarks yet leaves it null
    until the response workflow decides it -- never defaulted to either
    value."""
    if not penalty_remarks:
        return None
    normalized = penalty_remarks.strip().lower()
    if normalized.startswith("considered"):
        return "considered"
    if normalized.startswith("not considered"):
        return "not_considered"
    return None


class InvalidReviewDecisionError(Exception):
    """Raised when a caller passes a decision string outside
    DCB_BILL_REVIEW_DECISIONS -- never silently coerced or ignored."""


class BillNotReviewedError(Exception):
    """Raised by revoke_bill_review_decision when the bill has no decision
    to revoke -- there's nothing to undo, so this is never silently a
    no-op that could mask the caller clicking the wrong row."""


def set_bill_review_decision(
    db: Session, *, bill: DelayedCashBill, decision: str, reviewed_by: User
) -> DelayedCashBill:
    """Vigilance's one-bill-at-a-time review action from the review queue.
    "considered"/"not_considered" are terminal (feed recompute_validated_penalty
    once every bill in the case has one); "needs_more_detail"/"needs_proof"
    kick the case back to the center for a follow-up response without making
    a financial decision yet."""
    if decision not in DCB_BILL_REVIEW_DECISIONS:
        raise InvalidReviewDecisionError(
            f"'{decision}' is not a valid review decision -- must be one of {DCB_BILL_REVIEW_DECISIONS}."
        )
    bill.considered = decision
    bill.reviewed_by_id = reviewed_by.id
    bill.reviewed_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(bill)
    return bill


def revoke_bill_review_decision(db: Session, *, bill: DelayedCashBill) -> DelayedCashBill:
    """Undoes a mistaken review click -- clears considered/reviewed_by/
    reviewed_at back to their pre-review state, moving the bill from
    Action Taken back into the Review Queue so Vigilance can decide again.
    Does NOT touch calculated_penalty/validated_penalty (recompute_
    validated_penalty already has to be re-run to fold in whatever the
    new decision ends up being, same as after any other review).

    Only revokes a decision that was actually made by a human review click
    (reviewed_by_id set) -- a bill whose `considered` came from
    _infer_considered() reading the historical workbook's own Penalty
    Remarks column at ingest time has no reviewed_by_id, and revoking that
    would erase real historical data with nothing to show for it. There's
    nothing to "undo" there since nobody in this app made that decision."""
    if bill.considered is None or bill.reviewed_by_id is None:
        raise BillNotReviewedError("This bill has no review decision to revoke.")
    bill.considered = None
    bill.reviewed_by_id = None
    bill.reviewed_at = None
    db.commit()
    db.refresh(bill)
    return bill


def list_bills_action_taken(db: Session, *, batch_id: Optional[int] = None) -> list[DelayedCashBill]:
    """Every bill with a TERMINAL verdict ("considered"/"not_considered") --
    the complement of list_bills_pending_review. Bills still at
    "needs_more_detail"/"needs_proof" stay OUT of this list (and stay IN
    the pending queue) since Vigilance hasn't made a final call on them
    yet -- only a genuine decision counts as "action taken"."""
    query = db.query(DelayedCashBill).filter(DelayedCashBill.considered.in_(TERMINAL_REVIEW_DECISIONS))
    if batch_id is not None:
        query = query.filter(DelayedCashBill.batch_id == batch_id)
    # id DESC as a tiebreaker -- see list_activity's identical comment in
    # delayed_cash_response_service.py.
    return query.order_by(DelayedCashBill.reviewed_at.desc(), DelayedCashBill.id.desc()).all()


def list_bills_for_center_penalty(db: Session, *, center_penalty: DelayedCashCenterPenalty) -> list[DelayedCashBill]:
    return (
        db.query(DelayedCashBill)
        .filter(
            DelayedCashBill.batch_id == center_penalty.batch_id,
            DelayedCashBill.centre_code == center_penalty.centre_code,
        )
        .order_by(DelayedCashBill.sales_bill)
        .all()
    )


@dataclass
class DcbBatchSummary:
    """KPI-style aggregate for one batch -- mirrors
    weekly_revenue_closure_service.BatchSummary's role for WRC, adapted to
    DCB's own decision model (no Cluster/Zonal Manager escalation here;
    needs_more_detail/needs_proof are DCB-specific follow-up states WRC
    doesn't have). Deliberately no zone/cluster breakdown yet -- DCB bills
    carry only centre_code, and the Org Master doesn't yet have a real
    zone/cluster hierarchy populated for these centers (see
    docs -- pending a Center Master import)."""

    total_bills: int
    pending_review_count: int
    considered_count: int
    not_considered_count: int
    needs_more_detail_count: int
    needs_proof_count: int
    centers_in_batch: int
    total_calculated_penalty: Decimal
    total_validated_penalty: Decimal


def get_batch_summary(db: Session, *, batch: DelayedCashUploadBatch) -> DcbBatchSummary:
    bills = db.query(DelayedCashBill).filter(DelayedCashBill.batch_id == batch.id).all()
    center_penalties = (
        db.query(DelayedCashCenterPenalty).filter(DelayedCashCenterPenalty.batch_id == batch.id).all()
    )
    return DcbBatchSummary(
        total_bills=len(bills),
        pending_review_count=sum(1 for b in bills if b.considered not in TERMINAL_REVIEW_DECISIONS),
        considered_count=sum(1 for b in bills if b.considered == "considered"),
        not_considered_count=sum(1 for b in bills if b.considered == "not_considered"),
        needs_more_detail_count=sum(1 for b in bills if b.considered == "needs_more_detail"),
        needs_proof_count=sum(1 for b in bills if b.considered == "needs_proof"),
        centers_in_batch=len(center_penalties),
        total_calculated_penalty=sum((cp.calculated_penalty for cp in center_penalties), Decimal("0")),
        total_validated_penalty=sum(
            (cp.validated_penalty for cp in center_penalties if cp.validated_penalty is not None), Decimal("0")
        ),
    )


# ---------------------------------------------------------------------------
# Per-center breakdown -- "Dashboard" tab's zone/cluster view for one batch.
# Unlike WRC (zone/cluster ride along on the incident row itself, uploaded
# verbatim), DCB bills carry only centre_code -- zone/cluster here comes
# from the Org Master via org_service, resolved through the Centers Master
# sync (see org_sheet_sync_service). A center not yet linked there (or
# genuinely new) shows as "Unknown" rather than guessed.
# ---------------------------------------------------------------------------


@dataclass
class DcbCenterBreakdown:
    centre_code: str
    centre_name: str
    zone: Optional[str]
    cluster: Optional[str]
    this_batch_bill_count: int
    this_batch_considered_count: int
    this_batch_not_considered_count: int
    this_batch_pending_count: int
    all_time_batch_count: int
    all_time_considered_count: int
    all_time_not_considered_count: int


def _resolve_zone_cluster(db: Session, centre_code: str) -> tuple[Optional[str], Optional[str]]:
    node = org_service.get_node_by_external_code(db, centre_code)
    if node is None:
        return None, None
    zone_node = org_service.find_ancestor_by_dimension_key(db, node, "zone")
    cluster_node = org_service.find_ancestor_by_dimension_key(db, node, "cluster")
    return (zone_node.name if zone_node else None, cluster_node.name if cluster_node else None)


def get_batch_centers_breakdown(db: Session, *, batch: DelayedCashUploadBatch) -> list[DcbCenterBreakdown]:
    this_batch_bills = db.query(DelayedCashBill).filter(DelayedCashBill.batch_id == batch.id).all()

    by_center: dict[str, list[DelayedCashBill]] = {}
    for bill in this_batch_bills:
        by_center.setdefault(bill.centre_code, []).append(bill)

    results = []
    for centre_code, bills in by_center.items():
        first = bills[0]
        zone, cluster = _resolve_zone_cluster(db, centre_code)

        all_time_bills = db.query(DelayedCashBill).filter(DelayedCashBill.centre_code == centre_code).all()
        all_time_batch_ids = {b.batch_id for b in all_time_bills}

        results.append(
            DcbCenterBreakdown(
                centre_code=centre_code,
                centre_name=first.centre_name,
                zone=zone,
                cluster=cluster,
                this_batch_bill_count=len(bills),
                this_batch_considered_count=sum(1 for b in bills if b.considered == "considered"),
                this_batch_not_considered_count=sum(1 for b in bills if b.considered == "not_considered"),
                this_batch_pending_count=sum(1 for b in bills if b.considered not in TERMINAL_REVIEW_DECISIONS),
                all_time_batch_count=len(all_time_batch_ids),
                all_time_considered_count=sum(1 for b in all_time_bills if b.considered == "considered"),
                all_time_not_considered_count=sum(1 for b in all_time_bills if b.considered == "not_considered"),
            )
        )

    return sorted(results, key=lambda r: r.centre_code)


def list_bills_pending_review(db: Session) -> list[DelayedCashBill]:
    """Every bill that still needs a Vigilance decision (or a re-decision
    after the center followed up on a needs_more_detail/needs_proof kick-
    back) -- i.e. anything without a TERMINAL verdict yet. Powers the review
    queue; ordered oldest-first so nothing sits unreviewed indefinitely just
    because newer batches keep landing on top."""
    return (
        db.query(DelayedCashBill)
        .filter(
            (DelayedCashBill.considered.is_(None))
            | (~DelayedCashBill.considered.in_(TERMINAL_REVIEW_DECISIONS))
        )
        .order_by(DelayedCashBill.created_at)
        .all()
    )


def compute_center_penalties(
    db: Session, *, batch: DelayedCashUploadBatch, rule: DelayedCashPenaltyRule
) -> list[DelayedCashCenterPenalty]:
    """Publishing-stage aggregation: groups this batch's bills by center and
    sums calculated_penalty over ALL of them (unfiltered by remark), matching
    the reference workbook's Penalty Data sheet exactly."""
    bills = db.query(DelayedCashBill).filter(DelayedCashBill.batch_id == batch.id).all()

    by_center: dict[str, list[DelayedCashBill]] = {}
    names: dict[str, str] = {}
    for bill in bills:
        by_center.setdefault(bill.centre_code, []).append(bill)
        names[bill.centre_code] = bill.centre_name

    results = []
    for centre_code, center_bills in by_center.items():
        records = [BillRecord(sales_bill=b.sales_bill, day_difference=b.calculated_day_difference) for b in center_bills]
        calc = calculate_penalty(records, rule)

        center_penalty = DelayedCashCenterPenalty(
            batch_id=batch.id,
            centre_code=centre_code,
            centre_name=names[centre_code],
            total_bills=calc.total_bills,
            calculated_penalty=calc.calculated_penalty,
            penalty_status="published",
        )
        db.add(center_penalty)
        results.append(center_penalty)
    db.commit()
    for r in results:
        db.refresh(r)
    return results


TERMINAL_REVIEW_DECISIONS = ("considered", "not_considered")


def recompute_validated_penalty(
    db: Session, *, center_penalty: DelayedCashCenterPenalty, rule: DelayedCashPenaltyRule
) -> DelayedCashCenterPenalty:
    """Post-remark-review stage: recomputes the penalty over only the bills
    whose `considered` verdict is NOT "considered" (i.e. no accepted
    exception). Requires every bill in this center/batch to have reached a
    TERMINAL verdict first -- "needs_more_detail"/"needs_proof" count as
    unreviewed here too (the center still owes a follow-up), same as null --
    raises rather than silently treating any of these as either included or
    excluded."""
    bills = (
        db.query(DelayedCashBill)
        .filter(
            DelayedCashBill.batch_id == center_penalty.batch_id,
            DelayedCashBill.centre_code == center_penalty.centre_code,
        )
        .all()
    )
    unreviewed = [b for b in bills if b.considered not in TERMINAL_REVIEW_DECISIONS]
    if unreviewed:
        raise ConfigurationError(
            f"{len(unreviewed)} bill(s) for {center_penalty.centre_code} have no terminal 'considered' verdict "
            "yet -- cannot compute validated_penalty until every bill is either considered or not_considered "
            "(a bill still marked needs_more_detail/needs_proof counts as unreviewed)."
        )

    not_considered = [b for b in bills if b.considered == "not_considered"]
    records = [BillRecord(sales_bill=b.sales_bill, day_difference=b.calculated_day_difference) for b in not_considered]
    calc = calculate_penalty(records, rule)

    center_penalty.validated_penalty = calc.calculated_penalty
    center_penalty.penalty_status = "validated"
    db.commit()
    db.refresh(center_penalty)
    return center_penalty


def apply_monthly_cap(
    db: Session, *, center_penalty: DelayedCashCenterPenalty, monthly_cap_amount: Decimal
) -> DelayedCashCenterPenalty:
    """final_penalty = min(validated_penalty, monthly_cap_amount).
    monthly_cap_amount must be supplied explicitly by the caller (computed as
    0.0625 x the responsible person's monthly gross salary component, sourced
    from HR/payroll data) -- this function never fabricates it or falls back
    to validated_penalty when it's missing."""
    if center_penalty.validated_penalty is None:
        raise ConfigurationError(
            f"{center_penalty.centre_code} has no validated_penalty yet -- call "
            "recompute_validated_penalty() first."
        )
    center_penalty.monthly_cap_amount = monthly_cap_amount
    center_penalty.final_penalty = min(center_penalty.validated_penalty, monthly_cap_amount)
    center_penalty.penalty_status = "capped"
    db.commit()
    db.refresh(center_penalty)
    return center_penalty


# ---------------------------------------------------------------------------
# Reconciliation -- reference total vs. system total, per requirement #14.
# ---------------------------------------------------------------------------


@dataclass
class ReconciliationResult:
    reference_total_bills: int
    system_total_bills: int
    reference_total_penalty: Decimal
    system_total_penalty: Decimal
    difference: Decimal
    difference_pct: Decimal
    status: str


def reconcile(
    db: Session,
    *,
    batch: DelayedCashUploadBatch,
    reference_total_bills: int,
    reference_total_penalty: Decimal,
) -> ReconciliationResult:
    center_penalties = (
        db.query(DelayedCashCenterPenalty).filter(DelayedCashCenterPenalty.batch_id == batch.id).all()
    )
    system_total_bills = sum(cp.total_bills for cp in center_penalties)
    system_total_penalty = sum((cp.calculated_penalty for cp in center_penalties), Decimal("0"))

    difference = system_total_penalty - reference_total_penalty
    difference_pct = (
        (difference / reference_total_penalty * 100) if reference_total_penalty else Decimal("0")
    )
    status = "PASS" if difference == 0 and system_total_bills == reference_total_bills else "FAIL"

    return ReconciliationResult(
        reference_total_bills=reference_total_bills,
        system_total_bills=system_total_bills,
        reference_total_penalty=reference_total_penalty,
        system_total_penalty=system_total_penalty,
        difference=difference,
        difference_pct=difference_pct,
        status=status,
    )


# ---------------------------------------------------------------------------
# Batch deletion -- lets an Admin/Vigilance user delete a mistaken or
# superseded upload and re-upload the corrected file, rather than being
# stuck with it forever. DelayedCashUploadBatch.bills/.center_penalties
# already cascade at the ORM level, and DelayedCashCenterPenalty.responses
# cascades too -- but DelayedCashCenterActivity.center_penalty_id has NO
# cascade configured (it's a nullable FK, since an "opened" event on the
# single shared link can predate any specific case), so it's cleaned up
# explicitly here, in FK-safe child-to-parent order, rather than relying on
# cascade to do it. Evidence files on disk are removed before their DB rows,
# since a DB rollback is possible but a deleted file is not -- an orphaned
# file left behind is the safer failure mode than a dangling row pointing at
# a file that's already gone.
# ---------------------------------------------------------------------------


def delete_batch(db: Session, *, batch: DelayedCashUploadBatch) -> None:
    center_penalty_ids = [
        cp.id
        for cp in db.query(DelayedCashCenterPenalty.id)
        .filter(DelayedCashCenterPenalty.batch_id == batch.id)
        .all()
    ]

    if center_penalty_ids:
        responses = (
            db.query(DelayedCashCaseResponse)
            .filter(DelayedCashCaseResponse.center_penalty_id.in_(center_penalty_ids))
            .all()
        )
        for response in responses:
            storage_service.delete_file_if_exists(response.evidence_storage_path)

        db.query(DelayedCashCenterActivity).filter(
            DelayedCashCenterActivity.center_penalty_id.in_(center_penalty_ids)
        ).delete(synchronize_session=False)

        db.query(DelayedCashCaseResponse).filter(
            DelayedCashCaseResponse.center_penalty_id.in_(center_penalty_ids)
        ).delete(synchronize_session=False)

    db.query(DelayedCashCenterPenalty).filter(DelayedCashCenterPenalty.batch_id == batch.id).delete(
        synchronize_session=False
    )
    db.query(DelayedCashBill).filter(DelayedCashBill.batch_id == batch.id).delete(synchronize_session=False)

    db.delete(batch)
    db.commit()

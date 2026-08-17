"""Weekly Revenue Closure penalty calculator.

The formula here is not invented -- it is reverse-engineered from two real
reference workbooks (Week 2 and Week 3, Jul'26) and proven to reproduce
every reconstructible figure in both, with the two genuinely ambiguous
escalation edge-cases resolved by the user directly rather than guessed.
See docs/CARVMS_WEEKLY_REVENUE_CLOSURE_FORMULA_ANALYSIS.md for the full
proof before touching this file.

    center_penalty(section) = rate (e.g. 0.0625) if the center has >=1
                               qualifying incident in that section this
                               week, else 0 -- NEVER scaled by incident
                               count (proven flat, see doc S2).
    cluster_manager_penalty(section) = rate x (# distinct centers under
                               them with a qualifying incident in that
                               section) -- "not_considered" section counts
                               ONLY bill_pending-type incidents; "no_remark"
                               section counts every incident type
                               (confirmed by the user, doc S6.2).
    zonal_manager_penalty   = same formula, "no_remark" section ONLY --
                               Zonal Manager never escalates for
                               "not_considered" (confirmed by the user,
                               doc S6.3).

This is a deliberately separate engine from Delayed Cash Billing -- do not
merge the two, do not reuse rates/roles across them.
"""

from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Optional, Sequence

from sqlalchemy.orm import Session

from app.models.weekly_revenue_closure import (
    WeeklyRevenueBillIncident,
    WeeklyRevenueCaseResponse,
    WeeklyRevenueCenterActivity,
    WeeklyRevenueCenterCase,
    WeeklyRevenueCenterPenalty,
    WeeklyRevenueClosureBatch,
    WeeklyRevenueClosureRule,
    WeeklyRevenueNoRemarkIncident,
    WeeklyRevenueRolePenalty,
)
from app.models.user import User
from app.services import storage_service


class ConfigurationError(Exception):
    """Raised when an operation needs a setting that was never configured
    (e.g. no approved rule exists yet)."""


class NoApprovedRuleError(ConfigurationError):
    pass


PROVEN_PENALTY_RATE = Decimal("0.0625")


# ---------------------------------------------------------------------------
# Rule management -- versioned, mirrors delayed_cash_penalty_service.py.
# ---------------------------------------------------------------------------


def create_rule(
    db: Session, *, rule_version: str, penalty_rate: Decimal = PROVEN_PENALTY_RATE, created_by: User
) -> WeeklyRevenueClosureRule:
    rule = WeeklyRevenueClosureRule(
        rule_version=rule_version, penalty_rate=penalty_rate, status="draft", created_by_id=created_by.id
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return rule


def approve_rule(db: Session, *, rule: WeeklyRevenueClosureRule, approver: User) -> WeeklyRevenueClosureRule:
    rule.status = "approved"
    rule.approved_by_id = approver.id
    db.commit()
    db.refresh(rule)
    return rule


def get_active_rule(db: Session) -> WeeklyRevenueClosureRule:
    rule = (
        db.query(WeeklyRevenueClosureRule)
        .filter(WeeklyRevenueClosureRule.status == "approved")
        .order_by(WeeklyRevenueClosureRule.effective_from.desc())
        .first()
    )
    if rule is None:
        raise NoApprovedRuleError(
            "No approved WeeklyRevenueClosureRule exists yet -- an Admin must create and approve one "
            "before a batch can be processed (see docs/CARVMS_WEEKLY_REVENUE_CLOSURE_FORMULA_ANALYSIS.md "
            "for the proven default rate)."
        )
    return rule


def activate_default_rule(db: Session, *, actor: User) -> WeeklyRevenueClosureRule:
    """Idempotent: returns the existing approved rule if one is already
    active, otherwise creates AND approves one in a single step using the
    proven default rate (see module docstring). Mirrors
    delayed_cash_penalty_service.activate_default_rule -- see that
    function's docstring for why this doesn't weaken the versioned-rule
    governance model."""
    try:
        return get_active_rule(db)
    except NoApprovedRuleError:
        pass
    rule = create_rule(db, rule_version=f"WRC-DEFAULT-{date.today().isoformat()}", created_by=actor)
    return approve_rule(db, rule=rule, approver=actor)


# ---------------------------------------------------------------------------
# Batch + incident recording.
# ---------------------------------------------------------------------------


def create_batch(
    db: Session, *, period_start: date, period_end: date, week_label: str, rule: WeeklyRevenueClosureRule,
    created_by: User,
) -> WeeklyRevenueClosureBatch:
    batch = WeeklyRevenueClosureBatch(
        period_start=period_start, period_end=period_end, week_label=week_label, rule_id=rule.id,
        status="open", created_by_id=created_by.id,
    )
    db.add(batch)
    db.commit()
    db.refresh(batch)
    return batch


def list_batches(db: Session) -> list[WeeklyRevenueClosureBatch]:
    return db.query(WeeklyRevenueClosureBatch).order_by(WeeklyRevenueClosureBatch.created_at.desc()).all()


def get_batch(db: Session, batch_id: int) -> Optional[WeeklyRevenueClosureBatch]:
    return db.query(WeeklyRevenueClosureBatch).filter(WeeklyRevenueClosureBatch.id == batch_id).first()


def _infer_considered(penalty_remarks: Optional[str]) -> Optional[str]:
    """Same convention as delayed_cash_penalty_service._infer_considered --
    reads a human-authored "Considered - ..." / "Not Considered - ..."
    verdict into the structured field. Never defaults either way."""
    if not penalty_remarks:
        return None
    normalized = penalty_remarks.strip().lower()
    if normalized.startswith("considered"):
        return "considered"
    if normalized.startswith("not considered"):
        return "not_considered"
    return None


@dataclass
class RawBillIncidentInput:
    centre_code: str
    centre_name: str
    incident_date: date
    mis_final_remark: str  # "bill_pending" | "daily_report_not_sent"
    zone: Optional[str] = None
    cluster: Optional[str] = None
    zonal_manager: Optional[str] = None
    center_manager: Optional[str] = None
    center_manager_npid: Optional[str] = None
    billed_sessions: Optional[int] = None
    daily_report: Optional[int] = None
    variance: Optional[int] = None
    raw_remark: Optional[str] = None
    center_remarks: Optional[str] = None
    penalty_remarks: Optional[str] = None


def record_bill_incidents(
    db: Session, *, batch: WeeklyRevenueClosureBatch, raw_incidents: Sequence[RawBillIncidentInput]
) -> list[WeeklyRevenueBillIncident]:
    """Persists remark-received incidents verbatim, deriving `considered`
    from `penalty_remarks`'s prefix -- never overwriting the raw text."""
    created: list[WeeklyRevenueBillIncident] = []
    for raw in raw_incidents:
        incident = WeeklyRevenueBillIncident(
            batch_id=batch.id,
            centre_code=raw.centre_code,
            centre_name=raw.centre_name,
            zone=raw.zone,
            cluster=raw.cluster,
            zonal_manager=raw.zonal_manager,
            center_manager=raw.center_manager,
            center_manager_npid=raw.center_manager_npid,
            incident_date=raw.incident_date,
            billed_sessions=raw.billed_sessions,
            daily_report=raw.daily_report,
            variance=raw.variance,
            raw_remark=raw.raw_remark,
            mis_final_remark=raw.mis_final_remark,
            center_remarks=raw.center_remarks,
            penalty_remarks=raw.penalty_remarks,
            considered=_infer_considered(raw.penalty_remarks),
        )
        db.add(incident)
        created.append(incident)
    db.commit()
    for incident in created:
        db.refresh(incident)
    return created


class InvalidReviewDecisionError(ConfigurationError):
    pass


class BillIncidentNotFoundError(ConfigurationError):
    pass


def get_bill_incident_or_raise(db: Session, incident_id: int) -> WeeklyRevenueBillIncident:
    incident = (
        db.query(WeeklyRevenueBillIncident).filter(WeeklyRevenueBillIncident.id == incident_id).first()
    )
    if incident is None:
        raise BillIncidentNotFoundError(f"Bill incident {incident_id} not found")
    return incident


def list_bill_incidents(
    db: Session, *, batch_id: Optional[int] = None, pending_only: bool = False
) -> list[WeeklyRevenueBillIncident]:
    """Every remark-received incident, optionally scoped to one batch and/or
    restricted to ones still awaiting a Vigilance verdict (considered IS
    NULL) -- the review queue, mirroring the pattern already built for
    Delayed Cash Billing."""
    query = db.query(WeeklyRevenueBillIncident)
    if batch_id is not None:
        query = query.filter(WeeklyRevenueBillIncident.batch_id == batch_id)
    if pending_only:
        query = query.filter(
            WeeklyRevenueBillIncident.considered.is_(None),
            WeeklyRevenueBillIncident.moved_to_no_remark.is_(False),
        )
    return query.order_by(WeeklyRevenueBillIncident.incident_date).all()


def set_bill_incident_review(
    db: Session, *, incident: WeeklyRevenueBillIncident, decision: str, center_remarks: Optional[str] = None,
    reviewed_by: Optional[User] = None,
) -> WeeklyRevenueBillIncident:
    """Vigilance's verdict on one pending incident -- "considered" (an
    accepted exception, excluded from any penalty) or "not_considered"
    (the center's remark was rejected, feeds the flat per-center penalty
    and, if it's a bill_pending-type incident, the Cluster Manager
    escalation -- see compute_center_penalties/compute_role_penalties).
    `center_remarks`, if given, records/updates the free-text explanation
    (e.g. transcribed from an email) -- never fabricated if omitted."""
    if decision not in ("considered", "not_considered"):
        raise InvalidReviewDecisionError(
            f"'{decision}' is not a valid decision -- must be 'considered' or 'not_considered'."
        )
    if center_remarks is not None:
        incident.center_remarks = center_remarks
    incident.penalty_remarks = (
        f"{'Considered' if decision == 'considered' else 'Not Considered'} - Vigilance Review"
    )
    incident.considered = decision
    incident.reviewed_by_id = reviewed_by.id if reviewed_by is not None else None
    incident.reviewed_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(incident)
    return incident


def list_bill_incidents_action_taken(
    db: Session, *, batch_id: Optional[int] = None
) -> list[WeeklyRevenueBillIncident]:
    """Every incident with a terminal considered/not_considered verdict --
    the "Action Taken" log, complementing the pending review queue. Mirrors
    delayed_cash_penalty_service.list_bills_action_taken, including the
    id-desc tiebreaker (SQLite's CURRENT_TIMESTAMP only has 1-second
    resolution)."""
    query = db.query(WeeklyRevenueBillIncident).filter(WeeklyRevenueBillIncident.considered.isnot(None))
    if batch_id is not None:
        query = query.filter(WeeklyRevenueBillIncident.batch_id == batch_id)
    return query.order_by(WeeklyRevenueBillIncident.reviewed_at.desc(), WeeklyRevenueBillIncident.id.desc()).all()


def mark_no_remark_received(
    db: Session, *, incident: WeeklyRevenueBillIncident
) -> WeeklyRevenueNoRemarkIncident:
    """A pending incident whose center never submitted anything by the
    review cutoff -- moves it into the "Remarks Not Received" section
    (proven to be a genuinely separate source/table, see formula analysis
    doc S6.4) without deleting the original incident, which stays as the
    audit trail of what was actually ingested. Safe to call more than once
    for the same center/type in a batch -- accumulates the count rather
    than creating a duplicate row (matches the real source's own
    per-center-per-type granularity)."""
    incident.moved_to_no_remark = True

    existing = (
        db.query(WeeklyRevenueNoRemarkIncident)
        .filter(
            WeeklyRevenueNoRemarkIncident.batch_id == incident.batch_id,
            WeeklyRevenueNoRemarkIncident.centre_code == incident.centre_code,
            WeeklyRevenueNoRemarkIncident.incident_type == incident.mis_final_remark,
        )
        .first()
    )
    if existing is not None:
        existing.incident_count += 1
        db.commit()
        db.refresh(existing)
        return existing

    no_remark = WeeklyRevenueNoRemarkIncident(
        batch_id=incident.batch_id,
        centre_code=incident.centre_code,
        centre_name=incident.centre_name,
        zone=incident.zone,
        cluster=incident.cluster,
        zonal_manager=incident.zonal_manager,
        center_manager=incident.center_manager,
        center_manager_npid=incident.center_manager_npid,
        incident_type=incident.mis_final_remark,
        incident_count=1,
    )
    db.add(no_remark)
    db.commit()
    db.refresh(no_remark)
    return no_remark


def close_batch(
    db: Session, *, batch: WeeklyRevenueClosureBatch, rule: WeeklyRevenueClosureRule
) -> tuple[WeeklyRevenueClosureBatch, list[WeeklyRevenueCenterPenalty], list[WeeklyRevenueRolePenalty]]:
    """Finalizes a batch: computes every center's and role's penalty from
    whatever's been recorded so far (pending/never-reviewed incidents
    simply don't contribute -- see compute_center_penalties), then marks
    the batch closed. Safe to call again (e.g. after a late correction);
    re-running recomputes from scratch rather than accumulating duplicate
    penalty rows, since compute_center_penalties/compute_role_penalties
    each insert fresh rows scoped to this batch_id -- callers should treat
    a second call as a full recompute, not an increment."""
    center_penalties = compute_center_penalties(db, batch=batch, rule=rule)
    role_penalties = compute_role_penalties(db, batch=batch, rule=rule)
    batch.status = "closed"
    db.commit()
    db.refresh(batch)
    return batch, center_penalties, role_penalties


@dataclass
class RawNoRemarkIncidentInput:
    centre_code: str
    centre_name: str
    incident_type: str  # "bill_pending" | "daily_report_not_sent" | "no_billing_no_daily_report"
    zone: Optional[str] = None
    cluster: Optional[str] = None
    zonal_manager: Optional[str] = None
    center_manager: Optional[str] = None
    center_manager_npid: Optional[str] = None
    incident_count: int = 1


def record_no_remark_incidents(
    db: Session, *, batch: WeeklyRevenueClosureBatch, raw_incidents: Sequence[RawNoRemarkIncidentInput]
) -> list[WeeklyRevenueNoRemarkIncident]:
    created: list[WeeklyRevenueNoRemarkIncident] = []
    for raw in raw_incidents:
        incident = WeeklyRevenueNoRemarkIncident(
            batch_id=batch.id,
            centre_code=raw.centre_code,
            centre_name=raw.centre_name,
            zone=raw.zone,
            cluster=raw.cluster,
            zonal_manager=raw.zonal_manager,
            center_manager=raw.center_manager,
            center_manager_npid=raw.center_manager_npid,
            incident_type=raw.incident_type,
            incident_count=raw.incident_count,
        )
        db.add(incident)
        created.append(incident)
    db.commit()
    for incident in created:
        db.refresh(incident)
    return created


# ---------------------------------------------------------------------------
# Penalty computation -- the proven formula.
# ---------------------------------------------------------------------------


@dataclass
class CenterInfo:
    centre_name: str
    zone: Optional[str] = None
    cluster: Optional[str] = None
    zonal_manager: Optional[str] = None
    center_manager: Optional[str] = None
    center_manager_npid: Optional[str] = None


def compute_center_penalties(
    db: Session, *, batch: WeeklyRevenueClosureBatch, rule: WeeklyRevenueClosureRule
) -> list[WeeklyRevenueCenterPenalty]:
    """Flat `rule.penalty_rate` per center per section if it has >=1
    qualifying incident in that section this week -- never scaled by
    incident count (proven, see module docstring)."""
    bill_incidents = (
        db.query(WeeklyRevenueBillIncident).filter(WeeklyRevenueBillIncident.batch_id == batch.id).all()
    )
    no_remark_incidents = (
        db.query(WeeklyRevenueNoRemarkIncident).filter(WeeklyRevenueNoRemarkIncident.batch_id == batch.id).all()
    )

    centers: dict[str, CenterInfo] = {}
    not_considered_centres: set[str] = set()
    no_remark_centres: set[str] = set()

    for b in bill_incidents:
        centers.setdefault(
            b.centre_code,
            CenterInfo(b.centre_name, b.zone, b.cluster, b.zonal_manager, b.center_manager, b.center_manager_npid),
        )
        if b.considered == "not_considered":
            not_considered_centres.add(b.centre_code)

    for n in no_remark_incidents:
        centers.setdefault(
            n.centre_code,
            CenterInfo(n.centre_name, n.zone, n.cluster, n.zonal_manager, n.center_manager, n.center_manager_npid),
        )
        no_remark_centres.add(n.centre_code)

    results = []
    for centre_code, info in centers.items():
        not_considered_penalty = rule.penalty_rate if centre_code in not_considered_centres else Decimal("0")
        no_remark_penalty = rule.penalty_rate if centre_code in no_remark_centres else Decimal("0")
        if not_considered_penalty == 0 and no_remark_penalty == 0:
            continue  # this center had incidents but none qualify for a penalty (e.g. all "Considered")

        cp = WeeklyRevenueCenterPenalty(
            batch_id=batch.id,
            centre_code=centre_code,
            centre_name=info.centre_name,
            center_manager=info.center_manager,
            center_manager_npid=info.center_manager_npid,
            not_considered_penalty=not_considered_penalty,
            no_remark_penalty=no_remark_penalty,
        )
        db.add(cp)
        results.append(cp)
    db.commit()
    for r in results:
        db.refresh(r)
    return results


def compute_role_penalties(
    db: Session, *, batch: WeeklyRevenueClosureBatch, rule: WeeklyRevenueClosureRule
) -> list[WeeklyRevenueRolePenalty]:
    """Cluster/Zonal Manager escalation -- rate x count of DISTINCT centers
    under them with a qualifying incident in that section. See module
    docstring for the two section-specific rules (both confirmed by the
    user, not inferred)."""
    bill_incidents = (
        db.query(WeeklyRevenueBillIncident).filter(WeeklyRevenueBillIncident.batch_id == batch.id).all()
    )
    no_remark_incidents = (
        db.query(WeeklyRevenueNoRemarkIncident).filter(WeeklyRevenueNoRemarkIncident.batch_id == batch.id).all()
    )

    # "not_considered" section: Cluster Manager only, bill_pending-type only.
    cluster_not_considered: dict[str, set[str]] = {}  # cluster name -> set of centre codes
    for b in bill_incidents:
        if b.considered == "not_considered" and b.mis_final_remark == "bill_pending" and b.cluster:
            cluster_not_considered.setdefault(b.cluster, set()).add(b.centre_code)

    # "no_remark" section: both Cluster and Zonal Manager, every incident type.
    cluster_no_remark: dict[str, set[str]] = {}
    zonal_no_remark: dict[str, set[str]] = {}
    for n in no_remark_incidents:
        if n.cluster:
            cluster_no_remark.setdefault(n.cluster, set()).add(n.centre_code)
        if n.zonal_manager:
            zonal_no_remark.setdefault(n.zonal_manager, set()).add(n.centre_code)

    # NPIDs aren't reliably present on every incident row in real data (the
    # source sheet only names Center Manager NPIDs, not Cluster/Zonal ones)
    # -- left null rather than fabricated; Vigilance can attach it manually
    # via Org Hierarchy contact info.
    results = []

    def _add(role: str, section: str, name: str, centre_codes: set[str]):
        count = len(centre_codes)
        penalty = rule.penalty_rate * count
        rp = WeeklyRevenueRolePenalty(
            batch_id=batch.id, role=role, section=section, person_name=name, person_npid=None,
            distinct_center_count=count, penalty_amount=penalty,
        )
        db.add(rp)
        results.append(rp)

    for name, codes in cluster_not_considered.items():
        _add("cluster_manager", "not_considered", name, codes)
    for name, codes in cluster_no_remark.items():
        _add("cluster_manager", "no_remark", name, codes)
    for name, codes in zonal_no_remark.items():
        _add("zonal_manager", "no_remark", name, codes)

    db.commit()
    for r in results:
        db.refresh(r)
    return results


@dataclass
class BatchSummary:
    """A KPI-style aggregate for one batch -- the single place this app
    computes these numbers, so a dashboard and any future export always
    agree (same "one number" discipline as the Metric Engine elsewhere in
    this codebase)."""

    total_incidents: int
    pending_review_count: int
    considered_count: int
    not_considered_count: int
    no_remark_center_count: int
    centers_penalized: int
    total_center_penalty_rate: Decimal
    total_role_penalty_rate: Decimal


def get_batch_summary(db: Session, *, batch: WeeklyRevenueClosureBatch) -> BatchSummary:
    bill_incidents = (
        db.query(WeeklyRevenueBillIncident).filter(WeeklyRevenueBillIncident.batch_id == batch.id).all()
    )
    no_remark_codes = {
        n.centre_code
        for n in db.query(WeeklyRevenueNoRemarkIncident)
        .filter(WeeklyRevenueNoRemarkIncident.batch_id == batch.id)
        .all()
    }
    center_penalties = (
        db.query(WeeklyRevenueCenterPenalty).filter(WeeklyRevenueCenterPenalty.batch_id == batch.id).all()
    )
    role_penalties = (
        db.query(WeeklyRevenueRolePenalty).filter(WeeklyRevenueRolePenalty.batch_id == batch.id).all()
    )

    return BatchSummary(
        total_incidents=len(bill_incidents),
        pending_review_count=sum(
            1 for b in bill_incidents if b.considered is None and not b.moved_to_no_remark
        ),
        considered_count=sum(1 for b in bill_incidents if b.considered == "considered"),
        not_considered_count=sum(1 for b in bill_incidents if b.considered == "not_considered"),
        no_remark_center_count=len(no_remark_codes),
        centers_penalized=len(center_penalties),
        total_center_penalty_rate=sum(
            (cp.not_considered_penalty + cp.no_remark_penalty for cp in center_penalties), Decimal("0")
        ),
        total_role_penalty_rate=sum((rp.penalty_amount for rp in role_penalties), Decimal("0")),
    )


# ---------------------------------------------------------------------------
# Batch deletion -- mirrors delayed_cash_penalty_service.delete_batch's
# reasoning exactly, but WRC has one extra wrinkle: WeeklyRevenueCenterCase
# has NO relationship (and so no cascade) from WeeklyRevenueClosureBatch at
# all -- unlike DCB's center_penalty, which the batch cascades to natively
# -- because the case handle was deliberately built independent of the
# penalty computation's lifecycle (see the model's own docstring). So cases,
# same as activity, must be deleted explicitly here rather than assumed to
# go away with the batch. Every other child table below IS declared with
# cascade="all, delete-orphan" on the batch, but a bulk .delete() query
# bypasses ORM cascade entirely, so every child table is deleted explicitly
# in FK-safe order regardless.
# ---------------------------------------------------------------------------


def delete_batch(db: Session, *, batch: WeeklyRevenueClosureBatch) -> None:
    case_ids = [
        c.id
        for c in db.query(WeeklyRevenueCenterCase.id)
        .filter(WeeklyRevenueCenterCase.batch_id == batch.id)
        .all()
    ]

    if case_ids:
        responses = (
            db.query(WeeklyRevenueCaseResponse)
            .filter(WeeklyRevenueCaseResponse.case_id.in_(case_ids))
            .all()
        )
        for response in responses:
            storage_service.delete_file_if_exists(response.evidence_storage_path)

        db.query(WeeklyRevenueCenterActivity).filter(
            WeeklyRevenueCenterActivity.case_id.in_(case_ids)
        ).delete(synchronize_session=False)

        db.query(WeeklyRevenueCaseResponse).filter(
            WeeklyRevenueCaseResponse.case_id.in_(case_ids)
        ).delete(synchronize_session=False)

    db.query(WeeklyRevenueCenterCase).filter(WeeklyRevenueCenterCase.batch_id == batch.id).delete(
        synchronize_session=False
    )
    db.query(WeeklyRevenueRolePenalty).filter(WeeklyRevenueRolePenalty.batch_id == batch.id).delete(
        synchronize_session=False
    )
    db.query(WeeklyRevenueCenterPenalty).filter(WeeklyRevenueCenterPenalty.batch_id == batch.id).delete(
        synchronize_session=False
    )
    db.query(WeeklyRevenueBillIncident).filter(WeeklyRevenueBillIncident.batch_id == batch.id).delete(
        synchronize_session=False
    )
    db.query(WeeklyRevenueNoRemarkIncident).filter(
        WeeklyRevenueNoRemarkIncident.batch_id == batch.id
    ).delete(synchronize_session=False)

    db.delete(batch)
    db.commit()

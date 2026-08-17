"""The single semantic metric layer for Billing data.

The Audits/Findings domain this used to compute over was deleted
(2026-08-14) per explicit user request -- "iam not performing any audits
from here". Every dashboard tile, export, and Center Ranking figure now
computes from Delayed Cash Billing (DCB) + Weekly Revenue Closure (WRC)
data, and MUST be computed here, never re-derived with a second query
elsewhere -- same discipline as before: one number, everywhere it's shown.

Two different date granularities are used deliberately:
- Row-level filtering (which bills/incidents count) uses the row's own
  date (bill_date / incident_date).
- Batch-level totals (total_batches, penalty sums) use batch overlap with
  the requested range (period_start/period_end), since a penalty total is
  a property of the batch, not of any single row.
"""
from dataclasses import dataclass
from datetime import date
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.delayed_cash_billing import (
    DelayedCashBill,
    DelayedCashCenterPenalty,
    DelayedCashUploadBatch,
)
from app.models.weekly_revenue_closure import (
    WeeklyRevenueBillIncident,
    WeeklyRevenueCenterPenalty,
    WeeklyRevenueClosureBatch,
    WeeklyRevenueRolePenalty,
)
from app.services import org_service

# Both DCB and WRC only ever finalize a row to one of these two -- see
# TERMINAL_REVIEW_DECISIONS in delayed_cash_penalty_service.py and
# WRC_CONSIDERED_STATUSES in app/models/weekly_revenue_closure.py.
TERMINAL_CONSIDERED = ("considered", "not_considered")

# The repeated-centers list is capped, not silently truncated -- callers get
# `repeated_centers_truncated` alongside the (already-sorted, worst-first)
# slice so the UI can say "showing top N of M" rather than imply completeness.
REPEATED_CENTERS_LIMIT = 25


@dataclass
class MetricFilters:
    period_from: Optional[date] = None
    period_to: Optional[date] = None


def dcb_bills_query(db: Session, filters: MetricFilters):
    query = db.query(DelayedCashBill)
    if filters.period_from is not None:
        query = query.filter(DelayedCashBill.bill_date >= filters.period_from)
    if filters.period_to is not None:
        query = query.filter(DelayedCashBill.bill_date <= filters.period_to)
    return query


def wrc_incidents_query(db: Session, filters: MetricFilters):
    query = db.query(WeeklyRevenueBillIncident)
    if filters.period_from is not None:
        query = query.filter(WeeklyRevenueBillIncident.incident_date >= filters.period_from)
    if filters.period_to is not None:
        query = query.filter(WeeklyRevenueBillIncident.incident_date <= filters.period_to)
    return query


def dcb_batch_ids_in_range(db: Session, filters: MetricFilters):
    query = db.query(DelayedCashUploadBatch.id)
    if filters.period_from is not None:
        query = query.filter(DelayedCashUploadBatch.period_end >= filters.period_from)
    if filters.period_to is not None:
        query = query.filter(DelayedCashUploadBatch.period_start <= filters.period_to)
    return query


def wrc_batch_ids_in_range(db: Session, filters: MetricFilters):
    query = db.query(WeeklyRevenueClosureBatch.id)
    if filters.period_from is not None:
        query = query.filter(WeeklyRevenueClosureBatch.period_end >= filters.period_from)
    if filters.period_to is not None:
        query = query.filter(WeeklyRevenueClosureBatch.period_start <= filters.period_to)
    return query


def _non_compliance_rate(not_considered: int, considered: int) -> Optional[float]:
    """None (not 0) when nothing has reached a terminal verdict yet -- a
    rate of 0% would falsely read as "fully compliant" instead of "not
    reviewed yet"."""
    total = not_considered + considered
    if total == 0:
        return None
    return round(not_considered / total * 100, 2)


def _dcb_summary(db: Session, filters: MetricFilters) -> dict:
    bills_query = dcb_bills_query(db, filters)
    total_bills = bills_query.count()

    status_rows = (
        bills_query.with_entities(DelayedCashBill.considered, func.count(DelayedCashBill.id))
        .group_by(DelayedCashBill.considered)
        .all()
    )
    counts = {(status or "unreviewed"): count for status, count in status_rows}

    batch_ids = dcb_batch_ids_in_range(db, filters)
    total_batches = batch_ids.count()
    total_validated_penalty = (
        db.query(func.coalesce(func.sum(DelayedCashCenterPenalty.validated_penalty), 0))
        .filter(DelayedCashCenterPenalty.batch_id.in_(batch_ids))
        .scalar()
        or 0
    )

    considered = counts.get("considered", 0)
    not_considered = counts.get("not_considered", 0)
    return {
        "total_batches": total_batches,
        "total_bills": total_bills,
        "considered": considered,
        "not_considered": not_considered,
        "needs_more_detail": counts.get("needs_more_detail", 0),
        "needs_proof": counts.get("needs_proof", 0),
        "unreviewed": counts.get("unreviewed", 0),
        "non_compliance_rate": _non_compliance_rate(not_considered, considered),
        "total_validated_penalty": float(total_validated_penalty),
    }


def _wrc_summary(db: Session, filters: MetricFilters) -> dict:
    incidents_query = wrc_incidents_query(db, filters)
    total_incidents = incidents_query.count()

    status_rows = (
        incidents_query.with_entities(WeeklyRevenueBillIncident.considered, func.count(WeeklyRevenueBillIncident.id))
        .group_by(WeeklyRevenueBillIncident.considered)
        .all()
    )
    counts = {(status or "unreviewed"): count for status, count in status_rows}

    batch_ids = wrc_batch_ids_in_range(db, filters)
    total_batches = batch_ids.count()
    total_center_penalty = (
        db.query(
            func.coalesce(
                func.sum(WeeklyRevenueCenterPenalty.not_considered_penalty + WeeklyRevenueCenterPenalty.no_remark_penalty),
                0,
            )
        )
        .filter(WeeklyRevenueCenterPenalty.batch_id.in_(batch_ids))
        .scalar()
        or 0
    )
    total_role_penalty = (
        db.query(func.coalesce(func.sum(WeeklyRevenueRolePenalty.penalty_amount), 0))
        .filter(WeeklyRevenueRolePenalty.batch_id.in_(batch_ids))
        .scalar()
        or 0
    )

    considered = counts.get("considered", 0)
    not_considered = counts.get("not_considered", 0)
    return {
        "total_batches": total_batches,
        "total_incidents": total_incidents,
        "considered": considered,
        "not_considered": not_considered,
        "unreviewed": counts.get("unreviewed", 0),
        "non_compliance_rate": _non_compliance_rate(not_considered, considered),
        "total_center_penalty": float(total_center_penalty),
        "total_role_penalty": float(total_role_penalty),
    }


def _cluster_zone_breakdown(db: Session, filters: MetricFilters) -> tuple[list[dict], list[dict]]:
    """Distinct non-compliant (not_considered) centers per cluster/zone.

    WRC incidents already carry zone/cluster exactly as uploaded, so those
    are used directly. DCB bills carry only centre_code -- cluster/zone for
    those comes from the Org Master; a DCB center not yet linked there
    shows under "Unknown" rather than being silently dropped.
    """
    cluster_centers: dict[str, set[str]] = {}
    zone_centers: dict[str, set[str]] = {}

    wrc_rows = (
        wrc_incidents_query(db, filters)
        .filter(WeeklyRevenueBillIncident.considered == "not_considered")
        .with_entities(WeeklyRevenueBillIncident.centre_code, WeeklyRevenueBillIncident.cluster, WeeklyRevenueBillIncident.zone)
        .distinct()
        .all()
    )
    for centre_code, cluster, zone in wrc_rows:
        cluster_centers.setdefault(cluster or "Unknown", set()).add(centre_code)
        zone_centers.setdefault(zone or "Unknown", set()).add(centre_code)

    dcb_codes = (
        dcb_bills_query(db, filters)
        .filter(DelayedCashBill.considered == "not_considered")
        .with_entities(DelayedCashBill.centre_code)
        .distinct()
        .all()
    )
    for (centre_code,) in dcb_codes:
        node = org_service.get_node_by_external_code(db, centre_code)
        cluster_name = "Unknown"
        zone_name = "Unknown"
        if node is not None:
            cluster_node = org_service.find_ancestor_by_dimension_key(db, node, "cluster")
            zone_node = org_service.find_ancestor_by_dimension_key(db, node, "zone")
            cluster_name = cluster_node.name if cluster_node else "Unknown"
            zone_name = zone_node.name if zone_node else "Unknown"
        cluster_centers.setdefault(cluster_name, set()).add(centre_code)
        zone_centers.setdefault(zone_name, set()).add(centre_code)

    cluster_breakdown = sorted(
        ({"cluster": k, "non_compliant_center_count": len(v)} for k, v in cluster_centers.items()),
        key=lambda r: -r["non_compliant_center_count"],
    )
    zone_breakdown = sorted(
        ({"zone": k, "non_compliant_center_count": len(v)} for k, v in zone_centers.items()),
        key=lambda r: -r["non_compliant_center_count"],
    )
    return cluster_breakdown, zone_breakdown


def _repeated_centers(db: Session, filters: MetricFilters) -> list[dict]:
    """Centers with 2+ not_considered verdicts across DCB + WRC combined --
    the repeat-SOP-violator list the user asked for. Sorted worst-first;
    callers slice to REPEATED_CENTERS_LIMIT and check the true count to
    know whether that slice is a truncation."""
    counts: dict[str, dict] = {}

    dcb_rows = (
        dcb_bills_query(db, filters)
        .filter(DelayedCashBill.considered == "not_considered")
        .with_entities(DelayedCashBill.centre_code, DelayedCashBill.centre_name, func.count(DelayedCashBill.id))
        .group_by(DelayedCashBill.centre_code, DelayedCashBill.centre_name)
        .all()
    )
    for code, name, count in dcb_rows:
        entry = counts.setdefault(code, {"centre_name": name, "count": 0})
        entry["count"] += count

    wrc_rows = (
        wrc_incidents_query(db, filters)
        .filter(WeeklyRevenueBillIncident.considered == "not_considered")
        .with_entities(WeeklyRevenueBillIncident.centre_code, WeeklyRevenueBillIncident.centre_name, func.count(WeeklyRevenueBillIncident.id))
        .group_by(WeeklyRevenueBillIncident.centre_code, WeeklyRevenueBillIncident.centre_name)
        .all()
    )
    for code, name, count in wrc_rows:
        entry = counts.setdefault(code, {"centre_name": name, "count": 0})
        entry["count"] += count

    repeated = [
        {"centre_code": code, "centre_name": v["centre_name"], "violation_count": v["count"]}
        for code, v in counts.items()
        if v["count"] >= 2
    ]
    repeated.sort(key=lambda r: -r["violation_count"])
    return repeated


def compute_summary(db: Session, filters: MetricFilters) -> dict:
    cluster_breakdown, zone_breakdown = _cluster_zone_breakdown(db, filters)
    repeated = _repeated_centers(db, filters)

    return {
        "dcb": _dcb_summary(db, filters),
        "wrc": _wrc_summary(db, filters),
        "cluster_breakdown": cluster_breakdown,
        "zone_breakdown": zone_breakdown,
        "repeated_centers": repeated[:REPEATED_CENTERS_LIMIT],
        "repeated_centers_truncated": len(repeated) > REPEATED_CENTERS_LIMIT,
    }

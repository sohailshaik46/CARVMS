"""Center performance scoring -- a configurable, weighted composite score
per center, computed from Delayed Cash Billing (DCB) + Weekly Revenue
Closure (WRC) non-compliance data. Rewritten 2026-08-14 when the Audits/
Findings domain this used to score against was deleted; the same two
things are still deliberately NOT fabricated:

1. The weights. Seeded equal (0.25 each) by migration; admin-editable via
   PATCH /center-scoring/weights/{key}, never hardcoded in this module.
2. What "good" looks like in absolute terms. There is no externally-given
   target for any component, so this uses relative min-max normalization
   across the centers actually being compared -- a center's normalized
   score says "better/worse than the other centers in this result set",
   not "meets an absolute bar". If a component has no data for a center,
   that component is excluded from that center's composite instead of
   being defaulted to 0 or 1.

Billing data is Admin/Auditor-only everywhere else in this codebase, so
there is no per-role subtree scoping here (unlike the old Audits version)
-- app/api/center_scoring.py gates the whole endpoint the same way.
"""
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.center_scoring import CENTER_SCORE_COMPONENTS, COMPONENT_LOWER_IS_BETTER, CenterScoringWeight
from app.models.delayed_cash_billing import DelayedCashBill, DelayedCashCenterPenalty
from app.models.user import User
from app.models.weekly_revenue_closure import WeeklyRevenueBillIncident, WeeklyRevenueCenterPenalty
from app.services.metrics import (
    MetricFilters,
    dcb_batch_ids_in_range,
    dcb_bills_query,
    wrc_batch_ids_in_range,
    wrc_incidents_query,
)


def seed_default_weights_if_missing(db: Session) -> None:
    """Idempotent equal-weight seed -- mirrors the real migration's data
    step for tests, which build schema via create_all and never run
    migration data steps. Same reasoning as
    org_service.seed_default_dimensions_if_missing."""
    if db.query(CenterScoringWeight).first() is not None:
        return
    for component in CENTER_SCORE_COMPONENTS:
        db.add(CenterScoringWeight(component_key=component, weight=1.0 / len(CENTER_SCORE_COMPONENTS)))
    db.commit()


def list_weights(db: Session) -> list[CenterScoringWeight]:
    return db.query(CenterScoringWeight).order_by(CenterScoringWeight.component_key).all()


def get_weight(db: Session, component_key: str) -> Optional[CenterScoringWeight]:
    return db.query(CenterScoringWeight).filter(CenterScoringWeight.component_key == component_key).first()


def update_weight(db: Session, *, weight_row: CenterScoringWeight, new_weight: float, actor: User) -> CenterScoringWeight:
    weight_row.weight = new_weight
    weight_row.updated_by_id = actor.id
    db.commit()
    db.refresh(weight_row)
    return weight_row


def _raw_metrics_by_center(db: Session, filters: MetricFilters) -> dict[str, dict]:
    """One row per centre_code seen in DCB and/or WRC, with the four raw
    (pre-normalization) component values plus a display name."""
    raw: dict[str, dict] = {}

    def _entry(centre_code: str, centre_name: str) -> dict:
        e = raw.get(centre_code)
        if e is None:
            e = {
                "centre_name": centre_name,
                "considered": 0,
                "not_considered": 0,
                "unresolved": 0,
                "penalty": 0.0,
            }
            raw[centre_code] = e
        return e

    dcb_status_rows = (
        dcb_bills_query(db, filters)
        .with_entities(DelayedCashBill.centre_code, DelayedCashBill.centre_name, DelayedCashBill.considered, func.count(DelayedCashBill.id))
        .group_by(DelayedCashBill.centre_code, DelayedCashBill.centre_name, DelayedCashBill.considered)
        .all()
    )
    for centre_code, centre_name, considered, count in dcb_status_rows:
        entry = _entry(centre_code, centre_name)
        if considered == "considered":
            entry["considered"] += count
        elif considered == "not_considered":
            entry["not_considered"] += count
        else:
            entry["unresolved"] += count

    dcb_penalty_rows = (
        db.query(DelayedCashCenterPenalty.centre_code, func.coalesce(func.sum(DelayedCashCenterPenalty.validated_penalty), 0))
        .filter(DelayedCashCenterPenalty.batch_id.in_(dcb_batch_ids_in_range(db, filters)))
        .group_by(DelayedCashCenterPenalty.centre_code)
        .all()
    )
    for centre_code, penalty in dcb_penalty_rows:
        if centre_code in raw:
            raw[centre_code]["penalty"] += float(penalty)

    wrc_status_rows = (
        wrc_incidents_query(db, filters)
        .with_entities(
            WeeklyRevenueBillIncident.centre_code,
            WeeklyRevenueBillIncident.centre_name,
            WeeklyRevenueBillIncident.considered,
            func.count(WeeklyRevenueBillIncident.id),
        )
        .group_by(WeeklyRevenueBillIncident.centre_code, WeeklyRevenueBillIncident.centre_name, WeeklyRevenueBillIncident.considered)
        .all()
    )
    for centre_code, centre_name, considered, count in wrc_status_rows:
        entry = _entry(centre_code, centre_name)
        if considered == "considered":
            entry["considered"] += count
        elif considered == "not_considered":
            entry["not_considered"] += count
        else:
            entry["unresolved"] += count

    wrc_penalty_rows = (
        db.query(
            WeeklyRevenueCenterPenalty.centre_code,
            func.coalesce(func.sum(WeeklyRevenueCenterPenalty.not_considered_penalty + WeeklyRevenueCenterPenalty.no_remark_penalty), 0),
        )
        .filter(WeeklyRevenueCenterPenalty.batch_id.in_(wrc_batch_ids_in_range(db, filters)))
        .group_by(WeeklyRevenueCenterPenalty.centre_code)
        .all()
    )
    for centre_code, penalty in wrc_penalty_rows:
        if centre_code in raw:
            raw[centre_code]["penalty"] += float(penalty)

    components: dict[str, dict] = {}
    for centre_code, e in raw.items():
        terminal_total = e["considered"] + e["not_considered"]
        non_compliance_rate = (e["not_considered"] / terminal_total * 100) if terminal_total > 0 else None
        components[centre_code] = {
            "centre_name": e["centre_name"],
            "case_count": terminal_total + e["unresolved"],
            "values": {
                "non_compliance_rate": non_compliance_rate,
                "repeat_violations": float(e["not_considered"]),
                "outstanding_penalty": e["penalty"],
                "unresolved_cases": float(e["unresolved"]),
            },
        }
    return components


def _normalize(values: dict[str, Optional[float]], lower_is_better: bool) -> dict[str, Optional[float]]:
    present = {k: v for k, v in values.items() if v is not None}
    if not present:
        return {k: None for k in values}
    lo, hi = min(present.values()), max(present.values())
    result: dict[str, Optional[float]] = {}
    for k, v in values.items():
        if v is None:
            result[k] = None
            continue
        if hi == lo:
            result[k] = 1.0  # no variation across the compared set -- not a fabricated distinction
        else:
            normalized = (v - lo) / (hi - lo)
            result[k] = (1 - normalized) if lower_is_better else normalized
    return result


def compute_rankings(db: Session, filters: MetricFilters) -> list[dict]:
    raw = _raw_metrics_by_center(db, filters)
    if not raw:
        return []

    normalized: dict[str, dict[str, Optional[float]]] = {}
    for component in CENTER_SCORE_COMPONENTS:
        values = {centre_code: raw[centre_code]["values"][component] for centre_code in raw}
        normalized[component] = _normalize(values, COMPONENT_LOWER_IS_BETTER[component])

    weights = {w.component_key: w.weight for w in list_weights(db)}

    results = []
    for centre_code, entry in raw.items():
        component_scores = {}
        weighted_sum = 0.0
        weight_sum = 0.0
        for component in CENTER_SCORE_COMPONENTS:
            norm_value = normalized[component][centre_code]
            component_scores[component] = {
                "raw": entry["values"][component],
                "normalized": norm_value,
            }
            if norm_value is not None:
                w = weights.get(component, 0.0)
                weighted_sum += w * norm_value
                weight_sum += w

        composite_score = round((weighted_sum / weight_sum) * 100, 2) if weight_sum > 0 else None

        results.append(
            {
                "centre_code": centre_code,
                "centre_name": entry["centre_name"],
                "case_count": entry["case_count"],
                "components": component_scores,
                "composite_score": composite_score,
            }
        )

    results.sort(key=lambda r: (r["composite_score"] is None, -(r["composite_score"] or 0)))
    for idx, r in enumerate(results, start=1):
        r["rank"] = idx
    return results

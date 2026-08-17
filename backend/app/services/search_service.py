"""Global search across the entities that exist.

Partial, case-insensitive matching via LIKE/ilike -- no full-text index
(fine at this data volume; a real FTS engine would replace this module's
internals only, not its API). Rewritten 2026-08-14 when the Audits/
Findings/PenaltyRule domain this used to search was deleted; Delayed Cash
Billing bills and Weekly Revenue Closure incidents replace them. The whole
/search endpoint is Admin/Auditor-gated (see app/api/search.py) since
Billing data has no per-row visibility model of its own to enforce here.
"""
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.delayed_cash_billing import DelayedCashBill
from app.models.org import OrgNode
from app.models.report import ReportTemplate
from app.models.user import User
from app.models.weekly_revenue_closure import WeeklyRevenueBillIncident

SEARCHABLE_TYPES = ("delayed_cash_bill", "wrc_incident", "org_node", "report_template")


def _pattern(query: str) -> str:
    return f"%{query}%"


def _search_delayed_cash_bills(db: Session, query: str, limit: int) -> list[dict]:
    rows = (
        db.query(DelayedCashBill)
        .filter(
            or_(
                DelayedCashBill.centre_code.ilike(_pattern(query)),
                DelayedCashBill.centre_name.ilike(_pattern(query)),
                DelayedCashBill.sales_bill.ilike(_pattern(query)),
            )
        )
        .order_by(DelayedCashBill.id.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "entity_type": "delayed_cash_bill",
            "id": b.id,
            "title": f"{b.centre_code} — {b.sales_bill}",
            "subtitle": f"{b.centre_name} · {b.considered or 'unreviewed'}",
        }
        for b in rows
    ]


def _search_wrc_incidents(db: Session, query: str, limit: int) -> list[dict]:
    rows = (
        db.query(WeeklyRevenueBillIncident)
        .filter(
            or_(
                WeeklyRevenueBillIncident.centre_code.ilike(_pattern(query)),
                WeeklyRevenueBillIncident.centre_name.ilike(_pattern(query)),
                WeeklyRevenueBillIncident.raw_remark.ilike(_pattern(query)),
            )
        )
        .order_by(WeeklyRevenueBillIncident.id.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "entity_type": "wrc_incident",
            "id": i.id,
            "title": f"{i.centre_code} — {i.mis_final_remark}",
            "subtitle": f"{i.centre_name} · {i.considered or 'unreviewed'}",
        }
        for i in rows
    ]


def _search_org_nodes(db: Session, query: str, limit: int) -> list[dict]:
    rows = (
        db.query(OrgNode)
        .filter(or_(OrgNode.name.ilike(_pattern(query)), OrgNode.external_code.ilike(_pattern(query))))
        .limit(limit)
        .all()
    )
    return [
        {"entity_type": "org_node", "id": n.id, "title": n.name, "subtitle": n.external_code or ""}
        for n in rows
    ]


def _search_report_templates(db: Session, query: str, limit: int) -> list[dict]:
    rows = (
        db.query(ReportTemplate)
        .filter(or_(ReportTemplate.name.ilike(_pattern(query)), ReportTemplate.description.ilike(_pattern(query))))
        .limit(limit)
        .all()
    )
    return [
        {"entity_type": "report_template", "id": t.id, "title": t.name, "subtitle": t.description or ""}
        for t in rows
    ]


SEARCHERS = {
    "delayed_cash_bill": _search_delayed_cash_bills,
    "wrc_incident": _search_wrc_incidents,
    "org_node": _search_org_nodes,
    "report_template": _search_report_templates,
}


def global_search(
    db: Session, user: User, query: str, *, types: list[str] | None = None, limit_per_type: int = 10
) -> dict[str, list[dict]]:
    if not query or not query.strip():
        return {}

    active_types = types or list(SEARCHABLE_TYPES)
    results: dict[str, list[dict]] = {}

    for entity_type in active_types:
        searcher = SEARCHERS.get(entity_type)
        if searcher is not None:
            results[entity_type] = searcher(db, query, limit_per_type)

    return {k: v for k, v in results.items() if v}

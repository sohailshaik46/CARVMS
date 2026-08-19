"""Manual, explicit Weekly Revenue Closure sync between this instance's
own database and REMOTE_DATABASE_URL -- the WRC-specific counterpart to
org_master_remote_sync_service and delayed_cash_remote_sync_service (see
org_master_remote_sync_service's docstring for the full safety contract:
never automatic, preview-first via commit=False, never deletes on either
side; see delayed_cash_remote_sync_service's docstring for why
CaseResponse+evidence and activity logs are deliberately out of scope --
the same two reasons apply here unchanged).

What's synced: WeeklyRevenueClosureRule, WeeklyRevenueClosureBatch,
WeeklyRevenueBillIncident (including its review decision: considered/
reviewed_by/reviewed_at/penalty_remarks/moved_to_no_remark),
WeeklyRevenueNoRemarkIncident, WeeklyRevenueCenterPenalty,
WeeklyRevenueRolePenalty, WeeklyRevenueCenterCase (including its
response_token).

Same two field-handling categories as delayed_cash_remote_sync_service,
via remote_sync_helpers.merge_field:
  - only_fill_if_empty for anything that represents a decision already
    made or a link already emailed: considered, reviewed_by_id,
    reviewed_at, penalty_remarks, response_token,
    response_token_expires_at, escalation_sms_sent_at.
  - rank_order for forward-only lifecycle fields: batch.status
    (WRC_BATCH_STATUSES) and moved_to_no_remark (False -> True only,
    since a Vigilance override should never silently un-apply itself
    because a sync came from a side that hasn't caught up yet).
Everything else is plain "set if different", always visible in the
preview's changed_summary before anything is actually applied.
"""

from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.models.weekly_revenue_closure import (
    WRC_BATCH_STATUSES,
    WeeklyRevenueBillIncident,
    WeeklyRevenueCenterCase,
    WeeklyRevenueCenterPenalty,
    WeeklyRevenueClosureBatch,
    WeeklyRevenueClosureRule,
    WeeklyRevenueNoRemarkIncident,
    WeeklyRevenueRolePenalty,
)
from app.services.remote_sync_helpers import merge_field, resolve_user_id, resolve_user_id_nullable

_MAX_PREVIEW_ITEMS = 50
_MOVED_TO_NO_REMARK_RANK = (False, True)


@dataclass
class WrcRemoteSyncReport:
    rules_created: int = 0
    rules_updated: int = 0
    rules_unchanged: int = 0
    batches_created: int = 0
    batches_updated: int = 0
    batches_unchanged: int = 0
    bill_incidents_created: int = 0
    bill_incidents_updated: int = 0
    bill_incidents_unchanged: int = 0
    no_remark_incidents_created: int = 0
    no_remark_incidents_updated: int = 0
    no_remark_incidents_unchanged: int = 0
    center_penalties_created: int = 0
    center_penalties_updated: int = 0
    center_penalties_unchanged: int = 0
    role_penalties_created: int = 0
    role_penalties_updated: int = 0
    role_penalties_unchanged: int = 0
    center_cases_created: int = 0
    center_cases_updated: int = 0
    center_cases_unchanged: int = 0
    changed_summary: list = field(default_factory=list)
    committed: bool = False


def _add_preview(report: WrcRemoteSyncReport, line: str) -> None:
    if len(report.changed_summary) < _MAX_PREVIEW_ITEMS:
        report.changed_summary.append(line)


def _batch_natural_key(batch: WeeklyRevenueClosureBatch):
    return (batch.period_start, batch.period_end, batch.week_label)


def sync_weekly_revenue(
    source_db: Session, target_db: Session, *, commit: bool, current_admin_target_id: int
) -> WrcRemoteSyncReport:
    report = WrcRemoteSyncReport()

    # ---- rules ----
    target_rules_by_version = {r.rule_version: r for r in target_db.query(WeeklyRevenueClosureRule).all()}
    for source_rule in source_db.query(WeeklyRevenueClosureRule).all():
        target_rule = target_rules_by_version.get(source_rule.rule_version)
        if target_rule is None:
            target_rule = WeeklyRevenueClosureRule(
                rule_version=source_rule.rule_version,
                penalty_rate=source_rule.penalty_rate,
                no_remark_role_penalty_scope=source_rule.no_remark_role_penalty_scope,
                status=source_rule.status,
                effective_from=source_rule.effective_from,
                effective_to=source_rule.effective_to,
                created_by_id=resolve_user_id(source_rule.created_by_id, source_db, target_db, current_admin_target_id),
                approved_by_id=resolve_user_id_nullable(source_rule.approved_by_id, source_db, target_db),
            )
            target_db.add(target_rule)
            target_db.flush()
            target_rules_by_version[source_rule.rule_version] = target_rule
            report.rules_created += 1
            _add_preview(report, f"+ rule: {source_rule.rule_version}")
        else:
            changed = False
            changed |= merge_field(target_rule, "penalty_rate", source_rule.penalty_rate)
            changed |= merge_field(target_rule, "no_remark_role_penalty_scope", source_rule.no_remark_role_penalty_scope)
            changed |= merge_field(target_rule, "status", source_rule.status)
            changed |= merge_field(target_rule, "effective_to", source_rule.effective_to, only_fill_if_empty=True)
            changed |= merge_field(
                target_rule,
                "approved_by_id",
                resolve_user_id_nullable(source_rule.approved_by_id, source_db, target_db),
                only_fill_if_empty=True,
            )
            if changed:
                report.rules_updated += 1
                _add_preview(report, f"~ rule: {source_rule.rule_version}")
            else:
                report.rules_unchanged += 1

    # ---- batches ----
    target_batches_by_key = {_batch_natural_key(b): b for b in target_db.query(WeeklyRevenueClosureBatch).all()}
    source_batches = source_db.query(WeeklyRevenueClosureBatch).all()
    source_id_to_target_batch: dict[int, WeeklyRevenueClosureBatch] = {}

    for source_batch in source_batches:
        key = _batch_natural_key(source_batch)
        target_batch = target_batches_by_key.get(key)
        target_rule = target_rules_by_version[source_batch.rule.rule_version]

        if target_batch is None:
            target_batch = WeeklyRevenueClosureBatch(
                period_start=source_batch.period_start,
                period_end=source_batch.period_end,
                week_label=source_batch.week_label,
                rule_id=target_rule.id,
                status=source_batch.status,
                created_by_id=resolve_user_id(source_batch.created_by_id, source_db, target_db, current_admin_target_id),
            )
            target_db.add(target_batch)
            target_db.flush()
            target_batches_by_key[key] = target_batch
            source_id_to_target_batch[source_batch.id] = target_batch
            report.batches_created += 1
            _add_preview(report, f"+ batch: {source_batch.week_label}")
        else:
            changed = merge_field(target_batch, "status", source_batch.status, rank_order=WRC_BATCH_STATUSES)
            source_id_to_target_batch[source_batch.id] = target_batch
            if changed:
                report.batches_updated += 1
                _add_preview(report, f"~ batch: {source_batch.week_label}")
            else:
                report.batches_unchanged += 1

    # ---- bill incidents (matched within their batch by centre_code + date + type) ----
    for source_batch in source_batches:
        target_batch = source_id_to_target_batch[source_batch.id]
        target_incidents_by_key = {
            (i.centre_code, i.incident_date, i.mis_final_remark): i
            for i in target_db.query(WeeklyRevenueBillIncident)
            .filter(WeeklyRevenueBillIncident.batch_id == target_batch.id)
            .all()
        }
        source_incidents = (
            source_db.query(WeeklyRevenueBillIncident).filter(WeeklyRevenueBillIncident.batch_id == source_batch.id).all()
        )

        for source_incident in source_incidents:
            key = (source_incident.centre_code, source_incident.incident_date, source_incident.mis_final_remark)
            target_incident = target_incidents_by_key.get(key)
            if target_incident is None:
                target_incident = WeeklyRevenueBillIncident(
                    batch_id=target_batch.id,
                    centre_code=source_incident.centre_code,
                    centre_name=source_incident.centre_name,
                    zone=source_incident.zone,
                    cluster=source_incident.cluster,
                    zonal_manager=source_incident.zonal_manager,
                    center_manager=source_incident.center_manager,
                    center_manager_npid=source_incident.center_manager_npid,
                    incident_date=source_incident.incident_date,
                    billed_sessions=source_incident.billed_sessions,
                    daily_report=source_incident.daily_report,
                    variance=source_incident.variance,
                    raw_remark=source_incident.raw_remark,
                    mis_final_remark=source_incident.mis_final_remark,
                    center_remarks=source_incident.center_remarks,
                    penalty_remarks=source_incident.penalty_remarks,
                    considered=source_incident.considered,
                    reviewed_by_id=resolve_user_id_nullable(source_incident.reviewed_by_id, source_db, target_db),
                    reviewed_at=source_incident.reviewed_at,
                    moved_to_no_remark=source_incident.moved_to_no_remark,
                )
                target_db.add(target_incident)
                report.bill_incidents_created += 1
                _add_preview(report, f"+ incident: {source_incident.centre_code} / {source_incident.incident_date}")
            else:
                changed = False
                changed |= merge_field(target_incident, "centre_name", source_incident.centre_name)
                changed |= merge_field(target_incident, "zone", source_incident.zone)
                changed |= merge_field(target_incident, "cluster", source_incident.cluster)
                changed |= merge_field(target_incident, "zonal_manager", source_incident.zonal_manager)
                changed |= merge_field(target_incident, "center_manager", source_incident.center_manager)
                changed |= merge_field(target_incident, "center_manager_npid", source_incident.center_manager_npid)
                changed |= merge_field(target_incident, "billed_sessions", source_incident.billed_sessions)
                changed |= merge_field(target_incident, "daily_report", source_incident.daily_report)
                changed |= merge_field(target_incident, "variance", source_incident.variance)
                changed |= merge_field(target_incident, "raw_remark", source_incident.raw_remark)
                changed |= merge_field(target_incident, "center_remarks", source_incident.center_remarks)
                changed |= merge_field(
                    target_incident, "penalty_remarks", source_incident.penalty_remarks, only_fill_if_empty=True
                )
                changed |= merge_field(target_incident, "considered", source_incident.considered, only_fill_if_empty=True)
                changed |= merge_field(
                    target_incident,
                    "reviewed_by_id",
                    resolve_user_id_nullable(source_incident.reviewed_by_id, source_db, target_db),
                    only_fill_if_empty=True,
                )
                changed |= merge_field(target_incident, "reviewed_at", source_incident.reviewed_at, only_fill_if_empty=True)
                changed |= merge_field(
                    target_incident,
                    "moved_to_no_remark",
                    source_incident.moved_to_no_remark,
                    rank_order=_MOVED_TO_NO_REMARK_RANK,
                )
                if changed:
                    report.bill_incidents_updated += 1
                    _add_preview(report, f"~ incident: {source_incident.centre_code} / {source_incident.incident_date}")
                else:
                    report.bill_incidents_unchanged += 1

    # ---- no-remark incidents (matched within their batch by centre_code + incident_type) ----
    for source_batch in source_batches:
        target_batch = source_id_to_target_batch[source_batch.id]
        target_nri_by_key = {
            (n.centre_code, n.incident_type): n
            for n in target_db.query(WeeklyRevenueNoRemarkIncident)
            .filter(WeeklyRevenueNoRemarkIncident.batch_id == target_batch.id)
            .all()
        }
        source_nris = (
            source_db.query(WeeklyRevenueNoRemarkIncident)
            .filter(WeeklyRevenueNoRemarkIncident.batch_id == source_batch.id)
            .all()
        )

        for source_nri in source_nris:
            key = (source_nri.centre_code, source_nri.incident_type)
            target_nri = target_nri_by_key.get(key)
            if target_nri is None:
                target_nri = WeeklyRevenueNoRemarkIncident(
                    batch_id=target_batch.id,
                    centre_code=source_nri.centre_code,
                    centre_name=source_nri.centre_name,
                    zone=source_nri.zone,
                    cluster=source_nri.cluster,
                    zonal_manager=source_nri.zonal_manager,
                    center_manager=source_nri.center_manager,
                    center_manager_npid=source_nri.center_manager_npid,
                    incident_type=source_nri.incident_type,
                    incident_count=source_nri.incident_count,
                )
                target_db.add(target_nri)
                report.no_remark_incidents_created += 1
                _add_preview(report, f"+ no-remark: {source_nri.centre_code} / {source_nri.incident_type}")
            else:
                changed = False
                changed |= merge_field(target_nri, "centre_name", source_nri.centre_name)
                changed |= merge_field(target_nri, "zone", source_nri.zone)
                changed |= merge_field(target_nri, "cluster", source_nri.cluster)
                changed |= merge_field(target_nri, "zonal_manager", source_nri.zonal_manager)
                changed |= merge_field(target_nri, "center_manager", source_nri.center_manager)
                changed |= merge_field(target_nri, "center_manager_npid", source_nri.center_manager_npid)
                changed |= merge_field(target_nri, "incident_count", source_nri.incident_count)
                if changed:
                    report.no_remark_incidents_updated += 1
                    _add_preview(report, f"~ no-remark: {source_nri.centre_code} / {source_nri.incident_type}")
                else:
                    report.no_remark_incidents_unchanged += 1

    # ---- center penalties (matched within their batch by centre_code) ----
    for source_batch in source_batches:
        target_batch = source_id_to_target_batch[source_batch.id]
        target_cps_by_centre = {
            cp.centre_code: cp
            for cp in target_db.query(WeeklyRevenueCenterPenalty)
            .filter(WeeklyRevenueCenterPenalty.batch_id == target_batch.id)
            .all()
        }
        source_cps = (
            source_db.query(WeeklyRevenueCenterPenalty).filter(WeeklyRevenueCenterPenalty.batch_id == source_batch.id).all()
        )

        for source_cp in source_cps:
            target_cp = target_cps_by_centre.get(source_cp.centre_code)
            if target_cp is None:
                target_cp = WeeklyRevenueCenterPenalty(
                    batch_id=target_batch.id,
                    centre_code=source_cp.centre_code,
                    centre_name=source_cp.centre_name,
                    center_manager=source_cp.center_manager,
                    center_manager_npid=source_cp.center_manager_npid,
                    not_considered_penalty=source_cp.not_considered_penalty,
                    no_remark_penalty=source_cp.no_remark_penalty,
                )
                target_db.add(target_cp)
                report.center_penalties_created += 1
                _add_preview(report, f"+ center penalty: {source_cp.centre_code}")
            else:
                changed = False
                changed |= merge_field(target_cp, "centre_name", source_cp.centre_name)
                changed |= merge_field(target_cp, "center_manager", source_cp.center_manager)
                changed |= merge_field(target_cp, "center_manager_npid", source_cp.center_manager_npid)
                changed |= merge_field(target_cp, "not_considered_penalty", source_cp.not_considered_penalty)
                changed |= merge_field(target_cp, "no_remark_penalty", source_cp.no_remark_penalty)
                if changed:
                    report.center_penalties_updated += 1
                    _add_preview(report, f"~ center penalty: {source_cp.centre_code}")
                else:
                    report.center_penalties_unchanged += 1

    # ---- role penalties (matched within their batch by role + person_npid + section) ----
    for source_batch in source_batches:
        target_batch = source_id_to_target_batch[source_batch.id]
        target_rps_by_key = {
            (r.role, r.person_npid, r.section): r
            for r in target_db.query(WeeklyRevenueRolePenalty).filter(WeeklyRevenueRolePenalty.batch_id == target_batch.id).all()
        }
        source_rps = (
            source_db.query(WeeklyRevenueRolePenalty).filter(WeeklyRevenueRolePenalty.batch_id == source_batch.id).all()
        )

        for source_rp in source_rps:
            key = (source_rp.role, source_rp.person_npid, source_rp.section)
            target_rp = target_rps_by_key.get(key)
            if target_rp is None:
                target_rp = WeeklyRevenueRolePenalty(
                    batch_id=target_batch.id,
                    role=source_rp.role,
                    section=source_rp.section,
                    person_name=source_rp.person_name,
                    person_npid=source_rp.person_npid,
                    distinct_center_count=source_rp.distinct_center_count,
                    penalty_amount=source_rp.penalty_amount,
                )
                target_db.add(target_rp)
                report.role_penalties_created += 1
                _add_preview(report, f"+ role penalty: {source_rp.role} {source_rp.person_name} ({source_rp.section})")
            else:
                changed = False
                changed |= merge_field(target_rp, "person_name", source_rp.person_name)
                changed |= merge_field(target_rp, "distinct_center_count", source_rp.distinct_center_count)
                changed |= merge_field(target_rp, "penalty_amount", source_rp.penalty_amount)
                if changed:
                    report.role_penalties_updated += 1
                    _add_preview(report, f"~ role penalty: {source_rp.role} {source_rp.person_name} ({source_rp.section})")
                else:
                    report.role_penalties_unchanged += 1

    # ---- center cases (matched within their batch by centre_code) ----
    for source_batch in source_batches:
        target_batch = source_id_to_target_batch[source_batch.id]
        target_cases_by_centre = {
            c.centre_code: c
            for c in target_db.query(WeeklyRevenueCenterCase).filter(WeeklyRevenueCenterCase.batch_id == target_batch.id).all()
        }
        source_cases = (
            source_db.query(WeeklyRevenueCenterCase).filter(WeeklyRevenueCenterCase.batch_id == source_batch.id).all()
        )

        for source_case in source_cases:
            target_case = target_cases_by_centre.get(source_case.centre_code)
            if target_case is None:
                target_case = WeeklyRevenueCenterCase(
                    batch_id=target_batch.id,
                    centre_code=source_case.centre_code,
                    centre_name=source_case.centre_name,
                    response_token=source_case.response_token,
                    response_token_expires_at=source_case.response_token_expires_at,
                    escalation_sms_sent_at=source_case.escalation_sms_sent_at,
                )
                target_db.add(target_case)
                report.center_cases_created += 1
                _add_preview(report, f"+ center case: {source_case.centre_code}")
            else:
                changed = False
                changed |= merge_field(target_case, "centre_name", source_case.centre_name)
                changed |= merge_field(target_case, "response_token", source_case.response_token, only_fill_if_empty=True)
                changed |= merge_field(
                    target_case, "response_token_expires_at", source_case.response_token_expires_at, only_fill_if_empty=True
                )
                changed |= merge_field(
                    target_case, "escalation_sms_sent_at", source_case.escalation_sms_sent_at, only_fill_if_empty=True
                )
                if changed:
                    report.center_cases_updated += 1
                    _add_preview(report, f"~ center case: {source_case.centre_code}")
                else:
                    report.center_cases_unchanged += 1

    if commit:
        target_db.commit()
        report.committed = True
    else:
        target_db.rollback()

    return report

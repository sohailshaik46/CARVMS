"""Manual, explicit Delayed Cash Billing sync between this instance's own
database and REMOTE_DATABASE_URL -- the DCB-specific counterpart to
org_master_remote_sync_service (see that module's docstring for the full
safety contract: never automatic, preview-first via commit=False, never
deletes on either side).

What's synced: DelayedCashPenaltyRule, DelayedCashUploadBatch,
DelayedCashBill (including its review decision: considered/reviewed_by/
reviewed_at/penalty_remarks), DelayedCashCenterPenalty (including its
response_token and validated/final penalty decision fields).

What's deliberately NOT synced, and why:
  - DelayedCashCaseResponse (the actual center-manager submission text +
    evidence file). The evidence file itself lives only on whichever
    machine's disk received the upload -- this sync only has a database
    connection to the other side, no file-transfer channel, so copying
    the response ROW without its evidence file would leave a broken
    reference. Ask for this to be built separately if it's needed.
  - DelayedCashCenterActivity (the "who opened/submitted what, when" log).
    Pure activity trail with no natural key worth matching across two
    independent databases; low value relative to the risk of misattributing
    log rows to the wrong event.

Two categories of field get special handling, both via
remote_sync_helpers.merge_field:
  - "Never overwrite once set" (only_fill_if_empty) -- response_token,
    response_token_expires_at, escalation_sms_sent_at, considered,
    reviewed_by_id, reviewed_at, penalty_remarks, validated_penalty,
    monthly_cap_amount, final_penalty. A sync can only FILL these in when
    the target's copy is still empty; it can never replace or blank out
    a real value already there -- protects an already-emailed response
    link and an already-made review decision from either direction.
  - "Forward-only rank" (rank_order) -- DelayedCashUploadBatch.status and
    DelayedCashCenterPenalty.penalty_status move forward along their
    defined lifecycle only, never backward, so a sync from a side that
    simply hasn't caught up yet can't regress an already-closed/decided
    batch back to an earlier stage.

Everything else (centre_name, raw source columns, computed totals) is a
plain "set if different" -- and always visible in the preview's
changed_summary before anything is actually applied.
"""

from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.models.delayed_cash_billing import (
    DCB_BATCH_STATUSES,
    DCB_PENALTY_STATUSES,
    DelayedCashBill,
    DelayedCashCenterPenalty,
    DelayedCashPenaltyRule,
    DelayedCashUploadBatch,
)
from app.services.remote_sync_helpers import merge_field, resolve_user_id, resolve_user_id_nullable

_MAX_PREVIEW_ITEMS = 50


@dataclass
class DcbRemoteSyncReport:
    rules_created: int = 0
    rules_updated: int = 0
    rules_unchanged: int = 0
    batches_created: int = 0
    batches_updated: int = 0
    batches_unchanged: int = 0
    bills_created: int = 0
    bills_updated: int = 0
    bills_unchanged: int = 0
    center_penalties_created: int = 0
    center_penalties_updated: int = 0
    center_penalties_unchanged: int = 0
    changed_summary: list = field(default_factory=list)
    committed: bool = False


def _add_preview(report: DcbRemoteSyncReport, line: str) -> None:
    if len(report.changed_summary) < _MAX_PREVIEW_ITEMS:
        report.changed_summary.append(line)


def _batch_natural_key(batch: DelayedCashUploadBatch):
    return (batch.period_start, batch.period_end, batch.source_filename)


def sync_delayed_cash(
    source_db: Session, target_db: Session, *, commit: bool, current_admin_target_id: int
) -> DcbRemoteSyncReport:
    report = DcbRemoteSyncReport()

    # ---- rules ----
    target_rules_by_version = {r.rule_version: r for r in target_db.query(DelayedCashPenaltyRule).all()}
    for source_rule in source_db.query(DelayedCashPenaltyRule).all():
        target_rule = target_rules_by_version.get(source_rule.rule_version)
        if target_rule is None:
            target_rule = DelayedCashPenaltyRule(
                rule_version=source_rule.rule_version,
                rate_per_day=source_rule.rate_per_day,
                monthly_cap_percentage=source_rule.monthly_cap_percentage,
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
            changed |= merge_field(target_rule, "rate_per_day", source_rule.rate_per_day)
            changed |= merge_field(target_rule, "monthly_cap_percentage", source_rule.monthly_cap_percentage)
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
    target_batches_by_key = {_batch_natural_key(b): b for b in target_db.query(DelayedCashUploadBatch).all()}
    source_batches = source_db.query(DelayedCashUploadBatch).all()
    source_id_to_target_batch: dict[int, DelayedCashUploadBatch] = {}

    for source_batch in source_batches:
        key = _batch_natural_key(source_batch)
        target_batch = target_batches_by_key.get(key)
        target_rule = target_rules_by_version[source_batch.rule.rule_version]

        if target_batch is None:
            target_batch = DelayedCashUploadBatch(
                period_start=source_batch.period_start,
                period_end=source_batch.period_end,
                source_filename=source_batch.source_filename,
                rule_id=target_rule.id,
                status=source_batch.status,
                uploaded_by_id=resolve_user_id(source_batch.uploaded_by_id, source_db, target_db, current_admin_target_id),
            )
            target_db.add(target_batch)
            target_db.flush()
            target_batches_by_key[key] = target_batch
            source_id_to_target_batch[source_batch.id] = target_batch
            report.batches_created += 1
            _add_preview(report, f"+ batch: {source_batch.period_start}..{source_batch.period_end} ({source_batch.source_filename})")
        else:
            changed = merge_field(target_batch, "status", source_batch.status, rank_order=DCB_BATCH_STATUSES)
            source_id_to_target_batch[source_batch.id] = target_batch
            if changed:
                report.batches_updated += 1
                _add_preview(report, f"~ batch: {source_batch.period_start}..{source_batch.period_end} ({source_batch.source_filename})")
            else:
                report.batches_unchanged += 1

    # ---- bills (matched within their batch by sales_bill) ----
    for source_batch in source_batches:
        target_batch = source_id_to_target_batch[source_batch.id]
        target_bills_by_sales_bill = {
            b.sales_bill: b
            for b in target_db.query(DelayedCashBill).filter(DelayedCashBill.batch_id == target_batch.id).all()
        }
        source_bills = source_db.query(DelayedCashBill).filter(DelayedCashBill.batch_id == source_batch.id).all()

        for source_bill in source_bills:
            target_bill = target_bills_by_sales_bill.get(source_bill.sales_bill)
            if target_bill is None:
                target_bill = DelayedCashBill(
                    batch_id=target_batch.id,
                    centre_code=source_bill.centre_code,
                    centre_name=source_bill.centre_name,
                    sales_bill=source_bill.sales_bill,
                    bill_date=source_bill.bill_date,
                    bill_created_time=source_bill.bill_created_time,
                    created_date=source_bill.created_date,
                    source_day_difference=source_bill.source_day_difference,
                    center_remarks=source_bill.center_remarks,
                    penalty_remarks=source_bill.penalty_remarks,
                    calculated_day_difference=source_bill.calculated_day_difference,
                    difference_check=source_bill.difference_check,
                    data_quality_status=source_bill.data_quality_status,
                    calculated_penalty=source_bill.calculated_penalty,
                    considered=source_bill.considered,
                    reviewed_by_id=resolve_user_id_nullable(source_bill.reviewed_by_id, source_db, target_db),
                    reviewed_at=source_bill.reviewed_at,
                )
                target_db.add(target_bill)
                report.bills_created += 1
                _add_preview(report, f"+ bill: {source_bill.centre_code} / {source_bill.sales_bill}")
            else:
                changed = False
                changed |= merge_field(target_bill, "centre_name", source_bill.centre_name)
                changed |= merge_field(target_bill, "calculated_day_difference", source_bill.calculated_day_difference)
                changed |= merge_field(target_bill, "difference_check", source_bill.difference_check)
                changed |= merge_field(target_bill, "data_quality_status", source_bill.data_quality_status)
                changed |= merge_field(target_bill, "calculated_penalty", source_bill.calculated_penalty)
                changed |= merge_field(target_bill, "penalty_remarks", source_bill.penalty_remarks, only_fill_if_empty=True)
                changed |= merge_field(target_bill, "considered", source_bill.considered, only_fill_if_empty=True)
                changed |= merge_field(
                    target_bill,
                    "reviewed_by_id",
                    resolve_user_id_nullable(source_bill.reviewed_by_id, source_db, target_db),
                    only_fill_if_empty=True,
                )
                changed |= merge_field(target_bill, "reviewed_at", source_bill.reviewed_at, only_fill_if_empty=True)
                if changed:
                    report.bills_updated += 1
                    _add_preview(report, f"~ bill: {source_bill.centre_code} / {source_bill.sales_bill}")
                else:
                    report.bills_unchanged += 1

    # ---- center penalties (matched within their batch by centre_code) ----
    for source_batch in source_batches:
        target_batch = source_id_to_target_batch[source_batch.id]
        target_cps_by_centre = {
            cp.centre_code: cp
            for cp in target_db.query(DelayedCashCenterPenalty)
            .filter(DelayedCashCenterPenalty.batch_id == target_batch.id)
            .all()
        }
        source_cps = (
            source_db.query(DelayedCashCenterPenalty)
            .filter(DelayedCashCenterPenalty.batch_id == source_batch.id)
            .all()
        )

        for source_cp in source_cps:
            target_cp = target_cps_by_centre.get(source_cp.centre_code)
            if target_cp is None:
                target_cp = DelayedCashCenterPenalty(
                    batch_id=target_batch.id,
                    centre_code=source_cp.centre_code,
                    centre_name=source_cp.centre_name,
                    total_bills=source_cp.total_bills,
                    calculated_penalty=source_cp.calculated_penalty,
                    validated_penalty=source_cp.validated_penalty,
                    monthly_cap_amount=source_cp.monthly_cap_amount,
                    final_penalty=source_cp.final_penalty,
                    penalty_status=source_cp.penalty_status,
                    response_token=source_cp.response_token,
                    response_token_expires_at=source_cp.response_token_expires_at,
                    escalation_sms_sent_at=source_cp.escalation_sms_sent_at,
                )
                target_db.add(target_cp)
                report.center_penalties_created += 1
                _add_preview(report, f"+ center penalty: {source_cp.centre_code}")
            else:
                changed = False
                changed |= merge_field(target_cp, "centre_name", source_cp.centre_name)
                changed |= merge_field(target_cp, "total_bills", source_cp.total_bills)
                changed |= merge_field(target_cp, "calculated_penalty", source_cp.calculated_penalty)
                changed |= merge_field(target_cp, "validated_penalty", source_cp.validated_penalty, only_fill_if_empty=True)
                changed |= merge_field(target_cp, "monthly_cap_amount", source_cp.monthly_cap_amount, only_fill_if_empty=True)
                changed |= merge_field(target_cp, "final_penalty", source_cp.final_penalty, only_fill_if_empty=True)
                changed |= merge_field(target_cp, "penalty_status", source_cp.penalty_status, rank_order=DCB_PENALTY_STATUSES)
                changed |= merge_field(target_cp, "response_token", source_cp.response_token, only_fill_if_empty=True)
                changed |= merge_field(
                    target_cp, "response_token_expires_at", source_cp.response_token_expires_at, only_fill_if_empty=True
                )
                changed |= merge_field(
                    target_cp, "escalation_sms_sent_at", source_cp.escalation_sms_sent_at, only_fill_if_empty=True
                )
                if changed:
                    report.center_penalties_updated += 1
                    _add_preview(report, f"~ center penalty: {source_cp.centre_code}")
                else:
                    report.center_penalties_unchanged += 1

    if commit:
        target_db.commit()
        report.committed = True
    else:
        target_db.rollback()

    return report

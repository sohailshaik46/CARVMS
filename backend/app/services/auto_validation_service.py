"""Auto-validation: advisory-only classification of a center's submitted
response remark against the AutoValidationRule vocabulary (seeded from the
user's real reference workbook -- see the seed data migration for the exact
49 rows). See app/models/auto_validation.py's module docstring for the full
design reasoning; the two points that matter most for every function here:

1. This NEVER sets DelayedCashBill.considered / WeeklyRevenueBillIncident.
   considered, and NEVER feeds the penalty calculation. It only writes the
   auto_* columns on the case-response row. Vigilance's own review-queue
   click (set_bill_review_decision / set_bill_incident_review) remains the
   only thing that's ever official.
2. A response that matches rules on BOTH sides (considered AND
   not_considered), or matches neither, lands in "manual_check" -- the
   engine never guesses between two signals or invents a verdict from
   nothing.

Matching is case-insensitive and word-boundary-aware (via regex \\b), not a
raw substring test -- so a rule for "Holiday" doesn't fire on an unrelated
remark that happens to contain "holidaying" or similar. It still can't
understand negation or sarcasm ("I did NOT go on holiday") -- that ambiguity
is exactly why this stays advisory rather than authoritative.
"""

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional, Sequence

from sqlalchemy.orm import Session

from app.models.auto_validation import AUTO_VALIDATION_BUCKETS, AutoValidationRule
from app.models.delayed_cash_billing import DelayedCashCaseResponse
from app.models.user import User
from app.models.weekly_revenue_closure import WeeklyRevenueCaseResponse
from app.services import audit_log_service


class InvalidBucketError(Exception):
    pass


# ---------------------------------------------------------------------------
# Rule management
# ---------------------------------------------------------------------------


def list_rules(db: Session, *, active_only: bool = False) -> list[AutoValidationRule]:
    query = db.query(AutoValidationRule)
    if active_only:
        query = query.filter(AutoValidationRule.is_active.is_(True))
    return query.order_by(AutoValidationRule.bucket, AutoValidationRule.category, AutoValidationRule.id).all()


def create_rule(
    db: Session,
    *,
    bucket: str,
    category: str,
    keyword_phrase: str,
    decision_label: str,
    reason: Optional[str] = None,
    notes: Optional[str] = None,
    applies_to: str = "both",
    created_by: Optional[User] = None,
) -> AutoValidationRule:
    if bucket not in ("considered", "not_considered"):
        raise InvalidBucketError(f"'{bucket}' is not a valid rule bucket -- must be 'considered' or 'not_considered'.")
    rule = AutoValidationRule(
        bucket=bucket,
        category=category,
        keyword_phrase=keyword_phrase,
        decision_label=decision_label,
        reason=reason,
        notes=notes,
        applies_to=applies_to,
        created_by_id=created_by.id if created_by else None,
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return rule


def set_rule_active(db: Session, *, rule: AutoValidationRule, is_active: bool) -> AutoValidationRule:
    rule.is_active = is_active
    db.commit()
    db.refresh(rule)
    return rule


# Same 49 rows as the data-seed step in migration 2e32db93c243 (see that
# file for the full provenance comment) -- duplicated here, not imported
# from the migration, so a real DB always gets its rules from the pinned
# historical migration while a throwaway test DB (built via
# Base.metadata.create_all(), which never runs migration data steps -- see
# tests/conftest.py) can seed the same starting rules through this
# idempotent helper instead.
_CONSIDERED_SEED_ROWS = [
    ("IP Bills Pending", "IP bills pending", "Consider", None),
    ("IP Bills Pending", "Insurance pending", "Consider", None),
    ("IP Bills Pending", "Hospital Partner not shared bill details", "Consider", None),
    ("Hospital Partner Delay", "HP not shared bill amount/rate plan", "Consider", None),
    ("Rebilling", "Wrong bill created", "Consider", "if proof"),
    ("Rebilling", "Price modification", "Consider", "if proof"),
    ("Rebilling", "Consultant tagging correction", "Consider", "if proof"),
    ("New Center", "Newly launched center", "Consider", "within 30 days of launch"),
    ("New CM / New Joining", "Newly joined CM/BE under training", "Consider (First Exception)", "3 months; first exception only"),
    ("Center Closure", "Permanently closed", "Consider", None),
    ("Center Closure", "Mutually terminated", "Consider", None),
    ("Approved Exception", "Sukaran approval", "Consider (Always)", None),
    ("Approved Exception", "Mahesh approval", "Consider (Always)", None),
    ("Approved Exception", "CEO approval", "Consider (Always)", None),
    ("DOC Billing Exception", "DOC approval", "Consider (with approval)", None),
    ("DOC Billing Exception", "Sukaran Approval", "Consider (with approval)", None),
]

_NOT_CONSIDERED_SEED_ROWS = [
    ("Staff Negligence", "Forgot to bill", "Internal lapse or Center lapse", None),
    ("Staff Negligence", "Missed billing", "Internal lapse or Center lapse", None),
    ("Staff Negligence", "Billing missed by staff", "Internal lapse or Center lapse", None),
    ("Staff Negligence", "Staff oversight", "Internal lapse or Center lapse", None),
    ("Delay", "Delayed billing", "Internal lapse or Center lapse", None),
    ("Delay", "Late update", "Internal lapse or Center lapse", None),
    ("Delay", "Delay due to busy schedule", "Internal lapse or Center lapse", None),
    ("Delay", "High patient load", "Internal lapse or Center lapse", None),
    ("Leave", "CM on leave", "Leaves & Holidays are not considered as per SOP", None),
    ("Leave", "Staff on leave", "Leaves & Holidays are not considered as per SOP", None),
    ("Leave", "Holiday", "Leaves & Holidays are not considered as per SOP", None),
    ("Leave", "Festival", "Leaves & Holidays are not considered as per SOP", None),
    ("Leave", "Weekly off", "Leaves & Holidays are not considered as per SOP", None),
    ("No Explanation", "Kindly consider", "No valid reason or No justification", None),
    ("No Explanation", "Please waive penalty", "No valid reason or No justification", None),
    ("No Explanation", "Sorry for delay", "No valid reason or No justification", None),
    ("No Explanation", "Will not repeat", "No valid reason or No justification", None),
    ("No Explanation", "Please approve", "No valid reason or No justification", None),
    ("No Proof", "Proof will be shared later", "Evidence or Proof unavailable", None),
    ("No Proof", "Mail will be shared", "Evidence or Proof unavailable", None),
    ("No Proof", "Awaiting confirmation", "Evidence or Proof unavailable", None),
    ("No Proof", "Under discussion", "Evidence or Proof unavailable", None),
    ("Process Failure", "Missed due to system check", "Internal lapse or Center lapse", None),
    ("Process Failure", "Billing pending from our side", "Internal lapse or Center lapse", None),
    ("Process Failure", "Delay in uploading", "Internal lapse or Center lapse", None),
    ("Credit", "Credit given without approval", "Policy violation", None),
    ("Credit", "Pending credit approval", "Approval should be obtained before billing", None),
    ("Generic", "Working on it", "Internal lapse or Center lapse", None),
    ("Generic", "Will update", "Internal lapse or Center lapse", None),
    ("Generic", "Team missed", "Internal lapse or Center lapse", None),
    ("Generic", "Communication gap", "Internal lapse or Center lapse", None),
    ("Generic", "Network issue", "Requires supporting proof", "without proof"),
    ("Generic", "System issue", "Requires supporting proof", "without IT ticket"),
]


def seed_default_rules_if_missing(db: Session) -> None:
    """Idempotent -- mirrors org_service.seed_default_dimensions_if_missing's
    pattern. Does nothing if any rule already exists (real DBs get their
    rules from the pinned migration; this is for a fresh test DB built via
    create_all(), which never runs migration data steps)."""
    if db.query(AutoValidationRule).first() is not None:
        return
    for category, keyword_phrase, decision_label, notes in _CONSIDERED_SEED_ROWS:
        db.add(
            AutoValidationRule(
                bucket="considered", category=category, keyword_phrase=keyword_phrase,
                decision_label=decision_label, reason=None, notes=notes, applies_to="both", is_active=True,
            )
        )
    for category, keyword_phrase, reason, notes in _NOT_CONSIDERED_SEED_ROWS:
        db.add(
            AutoValidationRule(
                bucket="not_considered", category=category, keyword_phrase=keyword_phrase,
                decision_label="Not Considered", reason=reason, notes=notes, applies_to="both", is_active=True,
            )
        )
    db.commit()


# ---------------------------------------------------------------------------
# Matching engine
# ---------------------------------------------------------------------------


@dataclass
class EvaluationResult:
    bucket: str  # one of AUTO_VALIDATION_BUCKETS
    category: Optional[str] = None
    matched_keyword: Optional[str] = None
    decision_label: Optional[str] = None
    reason: Optional[str] = None


def _matches(remark: str, keyword_phrase: str) -> bool:
    """Case-insensitive, word-boundary match: the keyword phrase must appear
    as whole words within the remark, not merely as a raw substring (so a
    "Holiday" rule doesn't fire on "holidaying" or "the holidays are busy"
    matching a partial word). Punctuation inside the phrase (e.g. "will
    not repeat") is treated as literal, spaces as flexible whitespace."""
    pattern = r"\b" + r"\s+".join(re.escape(word) for word in keyword_phrase.split()) + r"\b"
    return re.search(pattern, remark, re.IGNORECASE) is not None


def evaluate_remark(db: Session, *, remark_text: str, engine: str) -> EvaluationResult:
    """`engine` is "dcb" or "wrc" -- only used to also match rules scoped to
    that engine specifically; every seeded rule ships as applies_to="both"
    so this doesn't change behaviour today, it just keeps the door open for
    the two engines' vocabularies to diverge later without a migration."""
    remark = (remark_text or "").strip()
    if not remark:
        return EvaluationResult(bucket="manual_check")

    rules = [
        r
        for r in list_rules(db, active_only=True)
        if r.applies_to == "both" or r.applies_to == engine
    ]

    considered_hit: Optional[AutoValidationRule] = None
    not_considered_hit: Optional[AutoValidationRule] = None
    for rule in rules:
        if not _matches(remark, rule.keyword_phrase):
            continue
        if rule.bucket == "considered" and considered_hit is None:
            considered_hit = rule
        elif rule.bucket == "not_considered" and not_considered_hit is None:
            not_considered_hit = rule

    if considered_hit and not_considered_hit:
        # Contradictory signals -- e.g. remark mentions both "proof will be
        # shared later" AND "wrong bill created". Never picked automatically.
        return EvaluationResult(
            bucket="manual_check",
            reason=(
                f"Remark matched both a considered rule ('{considered_hit.keyword_phrase}') and a "
                f"not-considered rule ('{not_considered_hit.keyword_phrase}') -- needs human judgment."
            ),
        )
    if considered_hit:
        return EvaluationResult(
            bucket="considered",
            category=considered_hit.category,
            matched_keyword=considered_hit.keyword_phrase,
            decision_label=considered_hit.decision_label,
        )
    if not_considered_hit:
        return EvaluationResult(
            bucket="not_considered",
            category=not_considered_hit.category,
            matched_keyword=not_considered_hit.keyword_phrase,
            decision_label=not_considered_hit.decision_label,
            reason=not_considered_hit.reason,
        )
    return EvaluationResult(bucket="manual_check")


# ---------------------------------------------------------------------------
# Evaluate + store, per engine
# ---------------------------------------------------------------------------


def evaluate_dcb_response(db: Session, *, response: DelayedCashCaseResponse) -> DelayedCashCaseResponse:
    result = evaluate_remark(db, remark_text=response.reason, engine="dcb")
    response.auto_bucket = result.bucket
    response.auto_category = result.category
    response.auto_matched_keyword = result.matched_keyword
    response.auto_decision_label = result.decision_label
    response.auto_reason = result.reason
    response.auto_evaluated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(response)
    return response


def evaluate_wrc_response(db: Session, *, response: WeeklyRevenueCaseResponse) -> WeeklyRevenueCaseResponse:
    result = evaluate_remark(db, remark_text=response.reason, engine="wrc")
    response.auto_bucket = result.bucket
    response.auto_category = result.category
    response.auto_matched_keyword = result.matched_keyword
    response.auto_decision_label = result.decision_label
    response.auto_reason = result.reason
    response.auto_evaluated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(response)
    return response


def reevaluate_all_dcb(db: Session) -> list[DelayedCashCaseResponse]:
    """On-demand re-run, e.g. after rules are edited -- re-evaluates every
    response that hasn't been admin-overridden (an override is a human
    decision; re-running rules must never clobber it)."""
    responses = (
        db.query(DelayedCashCaseResponse).filter(DelayedCashCaseResponse.admin_override_bucket.is_(None)).all()
    )
    return [evaluate_dcb_response(db, response=r) for r in responses]


def reevaluate_all_wrc(db: Session) -> list[WeeklyRevenueCaseResponse]:
    responses = (
        db.query(WeeklyRevenueCaseResponse).filter(WeeklyRevenueCaseResponse.admin_override_bucket.is_(None)).all()
    )
    return [evaluate_wrc_response(db, response=r) for r in responses]


# ---------------------------------------------------------------------------
# Effective bucket + admin override
# ---------------------------------------------------------------------------


def effective_bucket(response) -> Optional[str]:
    """The override always wins once set -- but the original auto_bucket is
    kept alongside it (never overwritten), so reporting can always show
    both "what the rules said" and "what Vigilance decided" side by side."""
    return response.admin_override_bucket or response.auto_bucket


def override_dcb_response(
    db: Session, *, response: DelayedCashCaseResponse, admin: User, new_bucket: str, note: Optional[str] = None
) -> DelayedCashCaseResponse:
    if new_bucket not in AUTO_VALIDATION_BUCKETS:
        raise InvalidBucketError(f"'{new_bucket}' is not a valid bucket -- must be one of {AUTO_VALIDATION_BUCKETS}.")
    before = {"bucket": effective_bucket(response)}
    response.admin_override_bucket = new_bucket
    response.admin_override_by_id = admin.id
    response.admin_override_at = datetime.now(timezone.utc)
    response.admin_override_note = note
    audit_log_service.record(
        db,
        actor=admin,
        action="auto_validation.overridden",
        entity_type="DelayedCashCaseResponse",
        entity_id=response.id,
        before=before,
        after={"bucket": new_bucket, "note": note},
    )
    db.commit()
    db.refresh(response)
    return response


def override_wrc_response(
    db: Session, *, response: WeeklyRevenueCaseResponse, admin: User, new_bucket: str, note: Optional[str] = None
) -> WeeklyRevenueCaseResponse:
    if new_bucket not in AUTO_VALIDATION_BUCKETS:
        raise InvalidBucketError(f"'{new_bucket}' is not a valid bucket -- must be one of {AUTO_VALIDATION_BUCKETS}.")
    before = {"bucket": effective_bucket(response)}
    response.admin_override_bucket = new_bucket
    response.admin_override_by_id = admin.id
    response.admin_override_at = datetime.now(timezone.utc)
    response.admin_override_note = note
    audit_log_service.record(
        db,
        actor=admin,
        action="auto_validation.overridden",
        entity_type="WeeklyRevenueCaseResponse",
        entity_id=response.id,
        before=before,
        after={"bucket": new_bucket, "note": note},
    )
    db.commit()
    db.refresh(response)
    return response


# ---------------------------------------------------------------------------
# Listing for the Auto Validation tab
# ---------------------------------------------------------------------------


def list_dcb_responses(db: Session, *, bucket: Optional[str] = None) -> list[DelayedCashCaseResponse]:
    query = db.query(DelayedCashCaseResponse).filter(DelayedCashCaseResponse.auto_evaluated_at.isnot(None))
    responses = query.order_by(DelayedCashCaseResponse.submitted_at.desc()).all()
    if bucket is not None:
        responses = [r for r in responses if effective_bucket(r) == bucket]
    return responses


def list_wrc_responses(db: Session, *, bucket: Optional[str] = None) -> list[WeeklyRevenueCaseResponse]:
    query = db.query(WeeklyRevenueCaseResponse).filter(WeeklyRevenueCaseResponse.auto_evaluated_at.isnot(None))
    responses = query.order_by(WeeklyRevenueCaseResponse.submitted_at.desc()).all()
    if bucket is not None:
        responses = [r for r in responses if effective_bucket(r) == bucket]
    return responses

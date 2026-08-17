"""Auto-validation rules for center response remarks -- shared vocabulary
used by BOTH Delayed Cash Billing and Weekly Revenue Closure, since the
categories the user supplied (Rebilling, Staff Negligence, No Proof, ...)
describe how a center manager explains themselves in general, not anything
specific to either penalty formula. Seeded from a real reference workbook
(Remarks.xlsx: "Consideration" + "No Consideration" sheets, 8 + 10
categories, 49 keyword rows total) -- see the seed data migration for the
exact source rows.

This is advisory-only by design (confirmed with the user): matching a rule
never sets a bill/incident's real `considered` decision or feeds the penalty
calculation. It only populates the auto_* columns on the case-response row
(see DelayedCashCaseResponse / WeeklyRevenueCaseResponse) for Vigilance to
review in the new Auto Validation tab -- Vigilance's own Considered/Not
Considered click in the Review Queue remains the only thing that's ever
official. Admin can override the auto bucket; both the auto result and the
override are kept (see auto_validation_service) so nothing is overwritten
in place.

A response that matches no rule at all, or matches rules on BOTH sides
(considered AND not_considered), lands in "manual_check" rather than the
engine ever guessing -- see auto_validation_service.evaluate_remark."""

from sqlalchemy import Boolean, CheckConstraint, Column, DateTime, ForeignKey, Integer, String, Text, func

from app.database.database import Base

# "manual_check" is never a property of a RULE (there's nothing to configure
# for "no rule matched") -- it's the engine's fallback bucket. Rules only
# ever belong to "considered" or "not_considered".
AUTO_VALIDATION_RULE_BUCKETS = ("considered", "not_considered")
AUTO_VALIDATION_BUCKETS = ("considered", "not_considered", "manual_check")

# Lets a rule be scoped to one engine later if the two ever need to diverge;
# every seeded rule ships as "both" since the source workbook's categories
# aren't engine-specific.
AUTO_VALIDATION_RULE_SCOPES = ("both", "dcb", "wrc")


class AutoValidationRule(Base):
    """One keyword-phrase rule. `keyword_phrase` is matched case-insensitively,
    on word boundaries, as a substring of the center's submitted remark
    (DelayedCashCaseResponse.reason / WeeklyRevenueCaseResponse.reason) --
    never against the historical uploaded bill remark column, which predates
    the center's own explanation. `category`/`decision_label`/`reason`/`notes`
    are all display-only, copied straight from the source workbook so
    Vigilance sees exactly the same vocabulary they authored."""

    __tablename__ = "auto_validation_rules"
    __table_args__ = (
        CheckConstraint(f"bucket IN {AUTO_VALIDATION_RULE_BUCKETS}", name="ck_avr_bucket_valid"),
        CheckConstraint(f"applies_to IN {AUTO_VALIDATION_RULE_SCOPES}", name="ck_avr_applies_to_valid"),
    )

    id = Column(Integer, primary_key=True, index=True)
    bucket = Column(String, nullable=False, index=True)  # "considered" | "not_considered"
    category = Column(String, nullable=False)  # e.g. "Rebilling", "Staff Negligence"
    keyword_phrase = Column(String, nullable=False)  # the literal text matched against the remark
    decision_label = Column(String, nullable=False)  # e.g. "Consider", "Not Considered"
    # Only meaningful for not_considered rules -- what to tell the center.
    # Null for considered rules (there's nothing to explain away).
    reason = Column(Text, nullable=True)
    # Free-text nuance from the source sheet that doesn't fit a column, e.g.
    # "(if proof)" / "(First Exception)" -- shown to Vigilance, never
    # evaluated by the matcher itself.
    notes = Column(Text, nullable=True)
    applies_to = Column(String, nullable=False, default="both")
    # Lets Vigilance disable a rule (e.g. it's causing false positives)
    # without losing its history -- matching skips inactive rules entirely.
    is_active = Column(Boolean, nullable=False, default=True, server_default="1")

    created_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

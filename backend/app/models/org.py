from sqlalchemy import Boolean, CheckConstraint, Column, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import relationship

from app.database.database import Base

ORG_NODE_CONTACT_CHANGE_STATUSES = ("pending", "approved", "rejected")


class OrgDimension(Base):
    """A level in the organizational hierarchy (e.g. "zone", "center").

    Deliberately NOT a fixed set of columns -- the real hierarchy is
    Zone/Zonal Manager/Cluster/Cluster Manager/Center/Center Manager, per
    the user's own confirmed structure (no Region/Regional Manager level --
    removed entirely, including from the seeded template, since the
    organization doesn't have one). Admins can add/reorder dimensions later
    if the real shape changes again.
    """

    __tablename__ = "org_dimensions"

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String, unique=True, nullable=False, index=True)   # e.g. "zone"
    label = Column(String, nullable=False)                           # e.g. "Zone"
    sort_order = Column(Integer, nullable=False, default=0)

    nodes = relationship("OrgNode", back_populates="dimension")


class OrgNode(Base):
    """One node in the hierarchy (e.g. a specific zone, a specific center).

    Self-referencing via parent_id so the tree can be arbitrarily deep and
    doesn't assume the default 7-level template. external_code lets an
    uploaded dataset's own identifiers reconcile against this node later.
    """

    __tablename__ = "org_nodes"
    __table_args__ = (
        UniqueConstraint("dimension_id", "parent_id", "name", name="uq_org_node_sibling_name"),
    )

    id = Column(Integer, primary_key=True, index=True)
    dimension_id = Column(Integer, ForeignKey("org_dimensions.id"), nullable=False, index=True)
    parent_id = Column(Integer, ForeignKey("org_nodes.id"), nullable=True, index=True)
    name = Column(String, nullable=False)
    external_code = Column(String, nullable=True, index=True)
    # Drives the "active centers list" -- an inactive/closed node (e.g. a
    # closed center) is excluded from remark-automation lookups by default
    # rather than needing to be filtered per-upload every time.
    is_active = Column(Boolean, nullable=False, default=True, server_default="1")

    # Denormalized contact info for whoever is responsible at this node
    # (Half Country Head / Zonal Manager / Cluster Manager / Center
    # Incharge, depending on the node's dimension) -- kept on the node
    # itself rather than requiring a real CARVMS User account, since most
    # of these people (e.g. every center's incharge) never log into
    # CARVMS directly; the public response portal is token-based and
    # doesn't need one. A real User + org_node_id assignment (see
    # user_service.assign_org_node) is still the right path for anyone who
    # genuinely needs to log in and see a scoped dashboard -- that's a
    # separate, deliberate step, not an automatic side effect of syncing
    # contact data from the centers master sheet.
    manager_name = Column(String, nullable=True)
    manager_email = Column(String, nullable=True)
    manager_phone = Column(String, nullable=True)
    # Only meaningful for center-level nodes today (Center Incharge NPID),
    # but kept generic in case another level gains an identifier later.
    manager_npid = Column(String, nullable=True)

    dimension = relationship("OrgDimension", back_populates="nodes")
    parent = relationship("OrgNode", remote_side=[id], back_populates="children")
    children = relationship("OrgNode", back_populates="parent")


class OrgNodeContactChangeRequest(Base):
    """A center manager's self-reported name/NPID/email from a public
    response-portal submission is NEVER written straight into OrgNode --
    it becomes a pending request here instead, so an Admin can look at it
    and approve or reject before the Org Master's contact record actually
    changes. This is the one place that mutates OrgNode.manager_* fields as
    a *side effect* of something other than a direct admin edit; every other
    path (org_service.update_node, the sheet sync) is a direct, deliberate
    admin action.

    org_node_id is nullable: if the submitted center code doesn't match any
    known center, the request still gets recorded (so nothing the responder
    typed is silently dropped) but can't be approved until an Admin resolves
    which node it belongs to (or creates one)."""

    __tablename__ = "org_node_contact_change_requests"
    __table_args__ = (
        CheckConstraint(
            f"status IN {ORG_NODE_CONTACT_CHANGE_STATUSES}", name="ck_org_contact_change_status_valid"
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    org_node_id = Column(Integer, ForeignKey("org_nodes.id"), nullable=True, index=True)
    # What the responder typed as their center code -- kept even when it
    # didn't resolve to a real node, and even after approval, as the exact
    # record of what was submitted.
    centre_code_hint = Column(String, nullable=False)

    proposed_manager_name = Column(String, nullable=True)
    proposed_manager_npid = Column(String, nullable=True)
    proposed_manager_email = Column(String, nullable=True)

    # Where this proposal came from -- e.g. "delayed_cash_response" -- and a
    # loose pointer to that source row (e.g. DelayedCashCaseResponse.id) for
    # traceability. Not a real FK: the source table varies by feature and
    # this table shouldn't need a migration every time a new response
    # workflow starts proposing contact changes.
    source = Column(String, nullable=False)
    source_reference_id = Column(Integer, nullable=True)

    status = Column(String, nullable=False, default="pending")
    reviewed_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    org_node = relationship("OrgNode")
    reviewed_by = relationship("User", foreign_keys=[reviewed_by_id])

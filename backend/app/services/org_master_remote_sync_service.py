"""Manual, explicit Org Master sync between this instance's own database
and a REMOTE_DATABASE_URL (in practice: a local dev instance syncing
against Render's live Postgres).

Deliberately NOT automatic and NOT real-time -- there is no background
job, no request-time hook, nothing that touches REMOTE_DATABASE_URL
unless an admin explicitly calls one of the two /org/sync/remote/{push,
pull} endpoints. Every call defaults to a dry run (commit=False): it
computes the exact diff, then rolls back, so an admin can see "what would
change" before anything is actually written. The real bug this exists to
fix: a local admin edit (e.g. updating a center's email) had no way to
reach Render short of a one-off migration script, and vice versa -- see
the org_nodes migration in this session's history for the one-time version
of what this makes routine and reversible.

Safety properties, both directions:
  - NEVER deletes a row on either side. A dimension/node that exists on
    one side but not the other is always CREATED on the side missing it,
    never removed from the side that has it -- so a bad local experiment
    can add noise on the remote side but can't destroy anything there,
    and a stale remote row can't wipe something a local admin is mid-way
    through editing.
  - Rows are matched across the two independent databases by NATURAL
    identity (dimension key + the full root-to-node name path), never by
    raw `id` -- the two databases assign ids completely independently, so
    two nodes with the same id in each database are almost certainly
    unrelated rows.
  - Only Org Master data (org_dimensions, org_nodes) is in scope. DCB/WRC
    batches, bills, incidents, penalties, and review decisions are
    deliberately NOT synced by this module: those are live operational
    data with no safe natural key for merging across two independently
    operated databases, and merging real penalty/decision state wrongly
    is a much worse failure mode than an Org Master contact field being
    briefly out of date.
"""

from dataclasses import dataclass, field
from typing import Optional

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config.settings import settings
from app.models.org import OrgDimension, OrgNode

SYNCED_NODE_FIELDS = ("external_code", "is_active", "manager_name", "manager_email", "manager_phone", "manager_npid")


class RemoteSyncNotConfiguredError(RuntimeError):
    pass


class RemoteSyncMisconfiguredError(RuntimeError):
    pass


@dataclass
class RemoteSyncReport:
    dimensions_created: int = 0
    dimensions_updated: int = 0
    dimensions_unchanged: int = 0
    nodes_created: int = 0
    nodes_updated: int = 0
    nodes_unchanged: int = 0
    # A capped preview of what changed/would change -- not exhaustive for
    # a full 846-node tree, just enough for an admin to sanity-check before
    # confirming a real (commit=True) run.
    changed_node_names: list[str] = field(default_factory=list)
    committed: bool = False


_MAX_PREVIEW_NAMES = 50


def open_remote_session() -> Session:
    """A short-lived session against REMOTE_DATABASE_URL, wholly separate
    from this instance's own request-scoped `db` session. Raises a clear
    error rather than silently doing nothing if it isn't configured (e.g.
    if this ever ran on Render itself, where REMOTE_DATABASE_URL is never
    set) or if it's misconfigured to point at this instance's own
    database (which would make "syncing" a meaningless no-op at best)."""
    if not settings.REMOTE_DATABASE_URL:
        raise RemoteSyncNotConfiguredError(
            "REMOTE_DATABASE_URL is not set -- remote Org Master sync is only available from a "
            "local dev instance configured with the Render database's connection string."
        )
    if settings.REMOTE_DATABASE_URL == settings.DATABASE_URL:
        raise RemoteSyncMisconfiguredError(
            "REMOTE_DATABASE_URL is identical to this instance's own DATABASE_URL -- refusing to "
            "sync a database against itself."
        )
    engine = create_engine(settings.REMOTE_DATABASE_URL)
    RemoteSession = sessionmaker(bind=engine)
    return RemoteSession()


def _dimension_map(db: Session) -> dict[str, OrgDimension]:
    return {d.key: d for d in db.query(OrgDimension).all()}


def _node_natural_path(node: OrgNode) -> tuple:
    """(dimension_key, name) pairs from root to this node -- the stable
    cross-database identity for a node. `id`/`parent_id` mean nothing
    across two independently-run databases; a node's position in the
    hierarchy plus its own name is what an admin actually means by "the
    same center/zone/cluster" on both sides."""
    path: list[tuple[str, str]] = []
    current: Optional[OrgNode] = node
    while current is not None:
        path.append((current.dimension.key, current.name))
        current = current.parent
    return tuple(reversed(path))


def _topological_order(nodes: list[OrgNode]) -> list[OrgNode]:
    """Parents before children. Ascending-id order is NOT safe here --
    this app's own history includes re-parenting that left some nodes
    with parent_id >= id -- so this places nodes as soon as their parent
    is already placed (or has no parent), same approach as the one-off
    846-node migration script this makes routine."""
    by_id = {n.id: n for n in nodes}
    placed: set[int] = set()
    ordered: list[OrgNode] = []
    remaining = list(nodes)
    while remaining:
        progressed = False
        still_remaining = []
        for n in remaining:
            if n.parent_id is None or n.parent_id in placed or n.parent_id not in by_id:
                ordered.append(n)
                placed.add(n.id)
                progressed = True
            else:
                still_remaining.append(n)
        remaining = still_remaining
        if not progressed and remaining:
            # A genuine cycle shouldn't be possible given the FK/UI, but
            # never loop forever -- place whatever's left as-is.
            ordered.extend(remaining)
            break
    return ordered


def sync_org_master(source_db: Session, target_db: Session, *, commit: bool) -> RemoteSyncReport:
    """Copies org_dimensions + org_nodes FROM source_db INTO target_db.
    Additive/upsert only (see module docstring) -- nothing in target_db is
    ever deleted, even if it has no counterpart in source_db.

    commit=False (the default an admin sees first) computes the full diff,
    flushes it so IDs resolve correctly for a preview, then ROLLS BACK --
    target_db is left exactly as it was. Only commit=True actually writes.
    """
    report = RemoteSyncReport()

    # ---- dimensions first (nodes reference them) ----
    source_dims = source_db.query(OrgDimension).order_by(OrgDimension.sort_order).all()
    target_dims_by_key = _dimension_map(target_db)
    for sdim in source_dims:
        tdim = target_dims_by_key.get(sdim.key)
        if tdim is None:
            tdim = OrgDimension(key=sdim.key, label=sdim.label, sort_order=sdim.sort_order)
            target_db.add(tdim)
            report.dimensions_created += 1
            target_dims_by_key[sdim.key] = tdim
        elif tdim.label != sdim.label or tdim.sort_order != sdim.sort_order:
            tdim.label = sdim.label
            tdim.sort_order = sdim.sort_order
            report.dimensions_updated += 1
        else:
            report.dimensions_unchanged += 1

    target_db.flush()  # newly-created dimensions need real ids before nodes reference them
    target_dims_by_key = _dimension_map(target_db)

    # ---- nodes, parents before children ----
    source_nodes = source_db.query(OrgNode).all()
    ordered_source_nodes = _topological_order(source_nodes)

    target_nodes = target_db.query(OrgNode).all()
    target_by_path: dict[tuple, OrgNode] = {_node_natural_path(n): n for n in target_nodes}

    # As target nodes get created during this run, track them by the
    # SOURCE node's id so a child processed right after its parent (both
    # freshly created in this same run) can resolve its target parent
    # immediately, without a second DB round trip.
    source_id_to_target_node: dict[int, OrgNode] = {}

    for snode in ordered_source_nodes:
        natural_path = _node_natural_path(snode)
        existing = target_by_path.get(natural_path)

        target_parent = None
        if snode.parent_id is not None:
            target_parent = source_id_to_target_node.get(snode.parent_id)
            if target_parent is None:
                target_parent = target_by_path.get(natural_path[:-1])

        target_dim = target_dims_by_key[snode.dimension.key]

        if existing is None:
            new_node = OrgNode(
                dimension_id=target_dim.id,
                parent_id=target_parent.id if target_parent else None,
                name=snode.name,
                external_code=snode.external_code,
                is_active=snode.is_active,
                manager_name=snode.manager_name,
                manager_email=snode.manager_email,
                manager_phone=snode.manager_phone,
                manager_npid=snode.manager_npid,
            )
            target_db.add(new_node)
            target_db.flush()  # assigns an id, needed if this node has children
            source_id_to_target_node[snode.id] = new_node
            target_by_path[natural_path] = new_node
            report.nodes_created += 1
            if len(report.changed_node_names) < _MAX_PREVIEW_NAMES:
                report.changed_node_names.append(f"+ {snode.dimension.key}: {snode.name}")
        else:
            changed = False
            for field_name in SYNCED_NODE_FIELDS:
                if getattr(existing, field_name) != getattr(snode, field_name):
                    setattr(existing, field_name, getattr(snode, field_name))
                    changed = True
            source_id_to_target_node[snode.id] = existing
            if changed:
                report.nodes_updated += 1
                if len(report.changed_node_names) < _MAX_PREVIEW_NAMES:
                    report.changed_node_names.append(f"~ {snode.dimension.key}: {snode.name}")
            else:
                report.nodes_unchanged += 1

    if commit:
        target_db.commit()
        report.committed = True
    else:
        target_db.rollback()

    return report

from typing import Optional

from sqlalchemy.orm import Session

from app.models.org import OrgDimension, OrgNode

# Default hierarchy template -- the confirmed real management chain,
# first-in-line to last: Half Country -> Zone -> Cluster -> Center. No
# Region or Regional Manager level (removed entirely -- the organization
# doesn't have one). "zonal_manager" and "employee" remain as historical
# tree levels; the actual Half Country/Zonal/Cluster/Center Manager
# *identity* is a real User anchored via org_node_id to the corresponding
# node (see app/models/user.py), not a distinct dimension row --
# editable/extendable afterward via the admin dimension-create endpoint.
# Not assumed to be the only valid shape.
DEFAULT_DIMENSIONS = [
    ("half_country", "Half Country", 1),
    ("zone", "Zone", 2),
    ("zonal_manager", "Zonal Manager", 3),
    ("cluster", "Cluster", 4),
    ("center", "Center", 5),
    ("employee", "Employee", 6),
]


class DuplicateDimensionKeyError(Exception):
    pass


class DuplicateSiblingNameError(Exception):
    pass


class DimensionNotFoundError(Exception):
    pass


class ParentNodeNotFoundError(Exception):
    pass


def seed_default_dimensions_if_missing(db: Session) -> None:
    """Idempotent: inserts the default hierarchy template only if the
    org_dimensions table is empty. The real migration
    (2361603621ad_add_org_dimensions_and_org_nodes.py) seeds this same list
    for the actual app database via a frozen raw-table insert -- this
    function exists so tests (which build schema via create_all, not
    Alembic) get the same starting state without duplicating migration
    logic at import time."""
    if db.query(OrgDimension).first() is not None:
        return
    for key, label, sort_order in DEFAULT_DIMENSIONS:
        db.add(OrgDimension(key=key, label=label, sort_order=sort_order))
    db.commit()


def list_dimensions(db: Session) -> list[OrgDimension]:
    return db.query(OrgDimension).order_by(OrgDimension.sort_order).all()


def create_dimension(db: Session, *, key: str, label: str, sort_order: int) -> OrgDimension:
    if db.query(OrgDimension).filter(OrgDimension.key == key).first():
        raise DuplicateDimensionKeyError(f"Dimension key '{key}' already exists")

    dim = OrgDimension(key=key, label=label, sort_order=sort_order)
    db.add(dim)
    db.commit()
    db.refresh(dim)
    return dim


def list_nodes(
    db: Session,
    *,
    dimension_id: Optional[int] = None,
    dimension_key: Optional[str] = None,
    parent_id: Optional[int] = None,
    skip: int = 0,
    limit: int = 100,
) -> list[OrgNode]:
    query = db.query(OrgNode)
    if dimension_key is not None:
        query = query.join(OrgDimension).filter(OrgDimension.key == dimension_key)
    if dimension_id is not None:
        query = query.filter(OrgNode.dimension_id == dimension_id)
    if parent_id is not None:
        query = query.filter(OrgNode.parent_id == parent_id)
    limit = max(1, min(limit, 500))
    return query.order_by(OrgNode.name).offset(max(0, skip)).limit(limit).all()


def get_node(db: Session, node_id: int) -> Optional[OrgNode]:
    return db.query(OrgNode).filter(OrgNode.id == node_id).first()


def get_node_by_external_code(db: Session, external_code: str) -> Optional[OrgNode]:
    """The lookup every upload-driven automation (Weekly Revenue Closure,
    Delayed Cash Billing) must use to resolve a raw "Center Code" column
    against the org master -- never re-deriving Zone/Cluster/manager from
    the upload itself."""
    return db.query(OrgNode).filter(OrgNode.external_code == external_code).first()


def find_ancestor_by_dimension_key(db: Session, node: OrgNode, dimension_key: str) -> Optional[OrgNode]:
    """Walks up the parent chain from `node` and returns the first ancestor
    (inclusive of `node` itself) belonging to the given dimension -- e.g.
    find_ancestor_by_dimension_key(db, center_node, "zone") to resolve a
    center's zone regardless of how many levels sit in between."""
    current: Optional[OrgNode] = node
    while current is not None:
        if current.dimension.key == dimension_key:
            return current
        current = current.parent
    return None


def get_or_create_node(
    db: Session,
    *,
    dimension_id: int,
    parent_id: Optional[int],
    name: str,
    external_code: Optional[str] = None,
) -> OrgNode:
    """Idempotent sibling lookup-or-create -- what a reconciling sync (e.g.
    org_sheet_sync_service) needs instead of create_node's raise-on-
    duplicate behavior, since a sync runs against the same names repeatedly."""
    existing = (
        db.query(OrgNode)
        .filter(
            OrgNode.dimension_id == dimension_id,
            OrgNode.parent_id == parent_id,
            OrgNode.name == name,
        )
        .first()
    )
    if existing:
        return existing
    return create_node(db, dimension_id=dimension_id, parent_id=parent_id, name=name, external_code=external_code)


def update_node(
    db: Session,
    *,
    node: OrgNode,
    name: Optional[str] = None,
    external_code: Optional[str] = None,
    is_active: Optional[bool] = None,
    manager_name: Optional[str] = None,
    manager_email: Optional[str] = None,
    manager_phone: Optional[str] = None,
    manager_npid: Optional[str] = None,
) -> OrgNode:
    if name is not None:
        existing = (
            db.query(OrgNode)
            .filter(
                OrgNode.dimension_id == node.dimension_id,
                OrgNode.parent_id == node.parent_id,
                OrgNode.name == name,
                OrgNode.id != node.id,
            )
            .first()
        )
        if existing:
            raise DuplicateSiblingNameError(
                f"A node named '{name}' already exists under this parent for this dimension"
            )
        node.name = name
    if external_code is not None:
        node.external_code = external_code
    if is_active is not None:
        node.is_active = is_active
    if manager_name is not None:
        node.manager_name = manager_name
    if manager_email is not None:
        node.manager_email = manager_email
    if manager_phone is not None:
        node.manager_phone = manager_phone
    if manager_npid is not None:
        node.manager_npid = manager_npid

    db.commit()
    db.refresh(node)
    return node


def get_node_path(db: Session, node: OrgNode) -> list[dict]:
    """Root-to-node breadcrumb, e.g. [Zone: South, Cluster: C1, ..., Center: X]."""
    path: list[dict] = []
    current: Optional[OrgNode] = node
    while current is not None:
        path.append(
            {
                "id": current.id,
                "name": current.name,
                "dimension_key": current.dimension.key,
            }
        )
        current = current.parent
    path.reverse()
    return path


def create_node(
    db: Session,
    *,
    dimension_id: int,
    parent_id: Optional[int],
    name: str,
    external_code: Optional[str],
) -> OrgNode:
    if not db.query(OrgDimension).filter(OrgDimension.id == dimension_id).first():
        raise DimensionNotFoundError(f"Dimension {dimension_id} does not exist")

    if parent_id is not None and not db.query(OrgNode).filter(OrgNode.id == parent_id).first():
        raise ParentNodeNotFoundError(f"Parent node {parent_id} does not exist")

    existing = (
        db.query(OrgNode)
        .filter(
            OrgNode.dimension_id == dimension_id,
            OrgNode.parent_id == parent_id,
            OrgNode.name == name,
        )
        .first()
    )
    if existing:
        raise DuplicateSiblingNameError(
            f"A node named '{name}' already exists under this parent for this dimension"
        )

    node = OrgNode(
        dimension_id=dimension_id,
        parent_id=parent_id,
        name=name,
        external_code=external_code,
    )
    db.add(node)
    db.commit()
    db.refresh(node)
    return node

"""Reconciles CARVMS's Org Master against the real Centers Master sheet.

The sheet identifies each level like this (verified against a real sample,
not assumed):
    Half Country Head (person name)        -- e.g. "Krunal", "Rajan"
    -> Zone (e.g. "South", "Bihar", "Greenfield")
       -> Cluster (identified ONLY by the Cluster Manager's own name --
                    the sheet has no separate cluster label; "Cluster" and
                    "who manages it" are the same string)
          -> Center (Center Code is the one genuinely stable identifier;
                     everything else can drift as people change roles)

This module is intentionally conservative:
  - Never invents a zone/cluster/half-country name that isn't in the row.
  - Never deletes a node that disappears from a sync -- it flags it instead
    (a center genuinely going Closed shows up as Active/Closed in the sheet
    itself and is handled via is_active; a center vanishing from the sheet
    entirely is a data question for a human, not something to silently prune).
  - Contact fields (manager_name/email/phone/npid) live on OrgNode directly
    (see app/models/org.py) rather than auto-creating CARVMS User logins --
    most of the people in this sheet never need to log into CARVMS.
  - A genuine conflict (same zone reported under two different Half Country
    Heads across rows) is reported, never silently resolved by "last write
    wins" without saying so.
"""

import csv
import io
from dataclasses import dataclass, field
from typing import Optional

from sqlalchemy.orm import Session

from app.models.org import OrgDimension, OrgNode
from app.services import org_service

# Column positions verified against a real sample of the sheet -- if the
# sheet's own column order ever changes, this is the one place to fix it.
COL_CENTER_CODE = 1
COL_CENTER_NAME = 2
COL_ACTIVE_CLOSED = 4
COL_ZONE = 5
COL_CLUSTER = 8
COL_ZM_NAME = 9
COL_HALF_COUNTRY_HEAD = 12
COL_CLUSTER_MAIL = 18
COL_CLUSTER_PHONE = 19
COL_ZONAL_MAIL = 20
COL_ZONAL_PHONE = 21
COL_CENTER_INCHARGE_NAME = 23
COL_CENTER_INCHARGE_NPID = 24
COL_CENTER_MAIL = 26
COL_CENTER_MOBILE = 27

MIN_COLUMNS = 22  # up through Center Incharge Name at minimum to be usable

_EXCEL_ERROR_VALUES = {"#n/a", "#ref!", "#value!", "#div/0!"}


def _clean(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    value = value.strip()
    if not value or value.lower() in _EXCEL_ERROR_VALUES:
        return None
    return value


@dataclass
class ParsedRow:
    row_number: int  # 1-based, header excluded, for error reporting
    center_code: str
    center_name: str
    is_active: bool
    active_status_raw: Optional[str]
    zone_name: Optional[str]
    cluster_manager_name: Optional[str]
    cluster_mail: Optional[str]
    cluster_phone: Optional[str]
    zonal_manager_name: Optional[str]
    zonal_mail: Optional[str]
    zonal_phone: Optional[str]
    half_country_head: Optional[str]
    center_incharge_name: Optional[str]
    center_incharge_npid: Optional[str]
    center_mail: Optional[str]
    center_mobile: Optional[str]


@dataclass
class SkippedRow:
    row_number: int
    reason: str
    raw: list


@dataclass
class DataConflict:
    description: str


@dataclass
class SyncReport:
    total_rows: int = 0
    half_countries_created: int = 0
    zones_created: int = 0
    clusters_created: int = 0
    centers_created: int = 0
    centers_updated: int = 0
    skipped: list = field(default_factory=list)
    conflicts: list = field(default_factory=list)


_ACTIVE_STATUS_VALUES = {"active"}
_KNOWN_INACTIVE_STATUS_VALUES = {"closed", "inactive", "dispute", "not operational", "operationally not started"}


def parse_centers_master(text: str, delimiter: str = ",") -> tuple[list[ParsedRow], list[SkippedRow]]:
    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    rows = list(reader)
    if not rows:
        return [], []

    parsed: list[ParsedRow] = []
    skipped: list[SkippedRow] = []

    for i, row in enumerate(rows[1:], start=1):  # skip header
        if len(row) < MIN_COLUMNS:
            if any(_clean(c) for c in row):  # not just a blank line
                skipped.append(SkippedRow(i, f"Row has only {len(row)} columns (expected >= {MIN_COLUMNS})", row))
            continue

        center_code = _clean(row[COL_CENTER_CODE])
        center_name = _clean(row[COL_CENTER_NAME])
        if not center_code:
            skipped.append(SkippedRow(i, "Missing Center Code", row))
            continue
        if not center_name:
            skipped.append(SkippedRow(i, f"Missing Center Name for {center_code}", row))
            continue

        active_raw = _clean(row[COL_ACTIVE_CLOSED])
        status_key = (active_raw or "").lower()
        is_active = status_key in _ACTIVE_STATUS_VALUES
        if active_raw and status_key not in _ACTIVE_STATUS_VALUES and status_key not in _KNOWN_INACTIVE_STATUS_VALUES:
            skipped.append(
                SkippedRow(i, f"Unrecognized Active/Closed value '{active_raw}' for {center_code} -- treated as inactive", row)
            )

        parsed.append(
            ParsedRow(
                row_number=i,
                center_code=center_code,
                center_name=center_name,
                is_active=is_active,
                active_status_raw=active_raw,
                zone_name=_clean(row[COL_ZONE]),
                cluster_manager_name=_clean(row[COL_CLUSTER]),
                cluster_mail=_clean(row[COL_CLUSTER_MAIL]),
                cluster_phone=_clean(row[COL_CLUSTER_PHONE]),
                zonal_manager_name=_clean(row[COL_ZM_NAME]),
                zonal_mail=_clean(row[COL_ZONAL_MAIL]),
                zonal_phone=_clean(row[COL_ZONAL_PHONE]),
                half_country_head=_clean(row[COL_HALF_COUNTRY_HEAD]),
                center_incharge_name=_clean(row[COL_CENTER_INCHARGE_NAME]),
                center_incharge_npid=_clean(row[COL_CENTER_INCHARGE_NPID]) if len(row) > COL_CENTER_INCHARGE_NPID else None,
                center_mail=_clean(row[COL_CENTER_MAIL]) if len(row) > COL_CENTER_MAIL else None,
                center_mobile=_clean(row[COL_CENTER_MOBILE]) if len(row) > COL_CENTER_MOBILE else None,
            )
        )

    return parsed, skipped


# ---------------------------------------------------------------------------
# "All Centers" directory (a different, simpler sheet -- CENTER ID / CENTER
# NAME / PHONE / CM NAME / CM EMAIL / CENTER STATUS / ADDRESS, no Zone/
# Cluster/Half Country columns). Used to keep the Center Code/Name dropdown
# on the public response portal populated and correct, independent of
# whether the bigger Centers Master hierarchy sync has run. A center
# already placed in the hierarchy by that sync keeps its parent; a center
# seen here for the first time is created top-level (parent_id=None) and
# can be re-parented later once/if the hierarchy sync places it properly.
# ---------------------------------------------------------------------------

DIRECTORY_COL_CENTER_ID = 0
DIRECTORY_COL_CENTER_NAME = 1
DIRECTORY_COL_PHONE = 2
DIRECTORY_COL_CM_NAME = 3
DIRECTORY_COL_CM_EMAIL = 4
DIRECTORY_COL_STATUS = 5

DIRECTORY_MIN_COLUMNS = 6


@dataclass
class DirectoryReport:
    total_rows: int = 0
    centers_created: int = 0
    centers_updated: int = 0
    skipped: list = field(default_factory=list)


def sync_center_directory(db: Session, rows: list) -> DirectoryReport:
    """`rows` is a list of already-parsed row tuples/lists (the caller
    handles CSV vs. XLSX extraction) -- the first row is the header."""
    report = DirectoryReport()
    center_dim = db.query(OrgDimension).filter(OrgDimension.key == "center").first()
    if center_dim is None:
        raise org_service.DimensionNotFoundError("Dimension 'center' does not exist")

    for i, row in enumerate(rows[1:], start=1):
        if len(row) < DIRECTORY_MIN_COLUMNS or not any(_clean(str(c)) if c is not None else None for c in row):
            continue
        code = _clean(str(row[DIRECTORY_COL_CENTER_ID])) if row[DIRECTORY_COL_CENTER_ID] is not None else None
        name = _clean(str(row[DIRECTORY_COL_CENTER_NAME])) if row[DIRECTORY_COL_CENTER_NAME] is not None else None
        if not code or not name:
            report.skipped.append(SkippedRow(i, "Missing Center ID or Center Name", []))
            continue

        phone = _clean(str(row[DIRECTORY_COL_PHONE])) if row[DIRECTORY_COL_PHONE] is not None else None
        cm_name = _clean(str(row[DIRECTORY_COL_CM_NAME])) if row[DIRECTORY_COL_CM_NAME] is not None else None
        cm_email = _clean(str(row[DIRECTORY_COL_CM_EMAIL])) if row[DIRECTORY_COL_CM_EMAIL] is not None else None
        status_raw = _clean(str(row[DIRECTORY_COL_STATUS])) if row[DIRECTORY_COL_STATUS] is not None else None
        is_active = (status_raw or "").lower() == "active"

        report.total_rows += 1
        existing = org_service.get_node_by_external_code(db, code)
        if existing is not None:
            org_service.update_node(
                db, node=existing, name=name, is_active=is_active,
                manager_name=cm_name, manager_email=cm_email, manager_phone=phone,
            )
            report.centers_updated += 1
        else:
            try:
                node = org_service.create_node(
                    db, dimension_id=center_dim.id, parent_id=None, name=name, external_code=code
                )
            except org_service.DuplicateSiblingNameError as exc:
                report.skipped.append(SkippedRow(i, f"{code}: {exc}", []))
                continue
            org_service.update_node(
                db, node=node, is_active=is_active,
                manager_name=cm_name, manager_email=cm_email, manager_phone=phone,
            )
            report.centers_created += 1

    return report


def list_active_center_directory(db: Session) -> list[dict]:
    """(code, name) pairs for every active center node -- what the public
    response portal's Center Code/Name dropdowns are populated from."""
    center_dim = db.query(OrgDimension).filter(OrgDimension.key == "center").first()
    if center_dim is None:
        return []
    nodes = (
        db.query(OrgNode)
        .filter(OrgNode.dimension_id == center_dim.id, OrgNode.is_active.is_(True), OrgNode.external_code.isnot(None))
        .order_by(OrgNode.name)
        .all()
    )
    return [{"code": n.external_code, "name": n.name} for n in nodes]


def sync_centers_master(db: Session, text: str, *, delimiter: str = ",") -> SyncReport:
    parsed_rows, skipped = parse_centers_master(text, delimiter=delimiter)
    report = SyncReport(total_rows=len(parsed_rows), skipped=list(skipped))

    dims = {d.key: d for d in db.query(OrgDimension).all()}
    for required in ("half_country", "zone", "cluster", "center"):
        if required not in dims:
            raise org_service.DimensionNotFoundError(
                f"Dimension '{required}' does not exist -- run seed_default_dimensions_if_missing first"
            )

    # Track what this sync has decided per zone, so a contradictory row
    # later in the same file is a reported conflict, not a silent overwrite.
    zone_head_seen: dict[str, str] = {}
    half_country_nodes: dict[str, OrgNode] = {}
    zone_nodes: dict[tuple[str, str], OrgNode] = {}  # (half_country_key, zone_name) -> node
    cluster_nodes: dict[tuple[int, str], OrgNode] = {}  # (zone_node_id, cluster_manager_name) -> node

    for row in parsed_rows:
        try:
            _sync_one_row(
                db, row, dims, report,
                zone_head_seen=zone_head_seen,
                half_country_nodes=half_country_nodes,
                zone_nodes=zone_nodes,
                cluster_nodes=cluster_nodes,
            )
        except org_service.DuplicateSiblingNameError as exc:
            db.rollback()
            report.skipped.append(
                SkippedRow(row.row_number, f"{row.center_code}: {exc} -- left the existing node untouched", [])
            )

    return report


def _sync_one_row(
    db: Session,
    row: "ParsedRow",
    dims: dict,
    report: SyncReport,
    *,
    zone_head_seen: dict,
    half_country_nodes: dict,
    zone_nodes: dict,
    cluster_nodes: dict,
) -> None:
    if not row.zone_name:
        report.skipped.append(SkippedRow(row.row_number, f"{row.center_code}: no Zone -- cannot place in hierarchy", []))
        return

    head_key = row.half_country_head or ""
    prior_head = zone_head_seen.get(row.zone_name)
    if prior_head is not None and head_key and prior_head != head_key:
        report.conflicts.append(
            DataConflict(
                f"Zone '{row.zone_name}' appears under Half Country Head '{prior_head}' in one row and "
                f"'{head_key}' in another (row {row.row_number}, {row.center_code}) -- kept the first, flagging for review."
            )
        )
    elif head_key and prior_head is None:
        zone_head_seen[row.zone_name] = head_key

    effective_head = zone_head_seen.get(row.zone_name) or None

    half_country_node = None
    if effective_head:
        half_country_node = half_country_nodes.get(effective_head)
        if half_country_node is None:
            before = db.query(OrgNode).filter(
                OrgNode.dimension_id == dims["half_country"].id, OrgNode.name == effective_head
            ).count()
            half_country_node = org_service.get_or_create_node(
                db, dimension_id=dims["half_country"].id, parent_id=None, name=effective_head
            )
            half_country_node.manager_name = effective_head
            db.commit()
            half_country_nodes[effective_head] = half_country_node
            if before == 0:
                report.half_countries_created += 1

    zone_key = (effective_head or "", row.zone_name)
    zone_node = zone_nodes.get(zone_key)
    if zone_node is None:
        parent_id = half_country_node.id if half_country_node else None
        before = db.query(OrgNode).filter(
            OrgNode.dimension_id == dims["zone"].id, OrgNode.parent_id == parent_id, OrgNode.name == row.zone_name
        ).count()
        zone_node = org_service.get_or_create_node(
            db, dimension_id=dims["zone"].id, parent_id=parent_id, name=row.zone_name
        )
        zone_nodes[zone_key] = zone_node
        if before == 0:
            report.zones_created += 1
    if row.zonal_manager_name:
        zone_node.manager_name = row.zonal_manager_name
    if row.zonal_mail:
        zone_node.manager_email = row.zonal_mail
    if row.zonal_phone:
        zone_node.manager_phone = row.zonal_phone
    db.commit()

    cluster_node = zone_node
    if row.cluster_manager_name:
        cluster_key = (zone_node.id, row.cluster_manager_name)
        cluster_node = cluster_nodes.get(cluster_key)
        if cluster_node is None:
            before = db.query(OrgNode).filter(
                OrgNode.dimension_id == dims["cluster"].id,
                OrgNode.parent_id == zone_node.id,
                OrgNode.name == row.cluster_manager_name,
            ).count()
            cluster_node = org_service.get_or_create_node(
                db, dimension_id=dims["cluster"].id, parent_id=zone_node.id, name=row.cluster_manager_name
            )
            cluster_nodes[cluster_key] = cluster_node
            if before == 0:
                report.clusters_created += 1
        cluster_node.manager_name = row.cluster_manager_name
        if row.cluster_mail:
            cluster_node.manager_email = row.cluster_mail
        if row.cluster_phone:
            cluster_node.manager_phone = row.cluster_phone
        db.commit()

    existing_center = org_service.get_node_by_external_code(db, row.center_code)
    if existing_center is not None:
        org_service.update_node(
            db,
            node=existing_center,
            name=row.center_name,
            is_active=row.is_active,
            manager_name=row.center_incharge_name,
            manager_email=row.center_mail,
            manager_phone=row.center_mobile,
            manager_npid=row.center_incharge_npid,
        )
        if existing_center.parent_id != cluster_node.id:
            existing_center.parent_id = cluster_node.id
            db.commit()
        report.centers_updated += 1
    else:
        center_node = org_service.create_node(
            db,
            dimension_id=dims["center"].id,
            parent_id=cluster_node.id,
            name=row.center_name,
            external_code=row.center_code,
        )
        org_service.update_node(
            db,
            node=center_node,
            is_active=row.is_active,
            manager_name=row.center_incharge_name,
            manager_email=row.center_mail,
            manager_phone=row.center_mobile,
            manager_npid=row.center_incharge_npid,
        )
        report.centers_created += 1

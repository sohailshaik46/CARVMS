"""Tests for org_master_remote_sync_service -- the manual, admin-triggered
push/pull between this instance's database and REMOTE_DATABASE_URL.

Exercises the service function directly against two independent in-memory
SQLite databases standing in for "local" and "remote" (never the real
Render Postgres) -- this proves the diff/match/never-delete logic without
any live network dependency. A couple of API-level tests separately prove
the RBAC guard and the "not configured" 400 when REMOTE_DATABASE_URL is
unset, which is the real state of the test environment.
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.database import Base
from app.models.org import OrgDimension, OrgNode
from app.models.user import User
from app.services import org_master_remote_sync_service as sync_service
from tests.conftest import TestingSessionLocal


def _new_sqlite_db():
    """A throwaway in-memory database with the full schema, standing in
    for one side of a sync (either "local" or "remote")."""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    return Session()


def _seed_basic_tree(db):
    """zone South -> cluster C1 -> center 900-X-C, with one manager field
    set on the center so "update changed fields" has something to prove."""
    zone_dim = OrgDimension(key="zone", label="Zone", sort_order=1)
    cluster_dim = OrgDimension(key="cluster", label="Cluster", sort_order=2)
    center_dim = OrgDimension(key="center", label="Center", sort_order=3)
    db.add_all([zone_dim, cluster_dim, center_dim])
    db.flush()

    zone = OrgNode(dimension_id=zone_dim.id, parent_id=None, name="South", external_code=None, is_active=True)
    db.add(zone)
    db.flush()
    cluster = OrgNode(dimension_id=cluster_dim.id, parent_id=zone.id, name="C1", external_code=None, is_active=True)
    db.add(cluster)
    db.flush()
    center = OrgNode(
        dimension_id=center_dim.id,
        parent_id=cluster.id,
        name="Test Center",
        external_code="900-X-C",
        is_active=True,
        manager_email="old@example.com",
    )
    db.add(center)
    db.commit()
    return zone, cluster, center


def _register(client, username, email, password="password123"):
    return client.post("/auth/register", json={"username": username, "email": email, "password": password})


def _login(client, username, password="password123"):
    return client.post("/auth/login", json={"username": username, "password": password}).json()["access_token"]


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _admin(client, username, email):
    _register(client, username, email)
    db = TestingSessionLocal()
    try:
        db.query(User).filter(User.username == username).first().role = "Admin"
        db.commit()
    finally:
        db.close()
    return _login(client, username)


# ---------------------------------------------------------------------------
# Service-level: dry run never writes
# ---------------------------------------------------------------------------


def test_dry_run_reports_correct_counts_and_writes_nothing():
    source = _new_sqlite_db()
    target = _new_sqlite_db()
    _seed_basic_tree(source)

    report = sync_service.sync_org_master(source, target, commit=False)

    assert report.committed is False
    assert report.dimensions_created == 3
    assert report.nodes_created == 3
    # And genuinely nothing was written -- target is still empty.
    assert target.query(OrgDimension).count() == 0
    assert target.query(OrgNode).count() == 0


# ---------------------------------------------------------------------------
# Real (commit=True) run: creates missing rows
# ---------------------------------------------------------------------------


def test_commit_creates_missing_dimensions_and_nodes_with_correct_hierarchy():
    source = _new_sqlite_db()
    target = _new_sqlite_db()
    _seed_basic_tree(source)

    report = sync_service.sync_org_master(source, target, commit=True)

    assert report.committed is True
    assert report.dimensions_created == 3
    assert report.nodes_created == 3
    assert report.nodes_updated == 0

    target_center = target.query(OrgNode).filter(OrgNode.external_code == "900-X-C").first()
    assert target_center is not None
    assert target_center.manager_email == "old@example.com"
    # Hierarchy preserved even though target's own ids are unrelated to source's.
    assert target_center.parent.name == "C1"
    assert target_center.parent.parent.name == "South"


# ---------------------------------------------------------------------------
# Existing rows: matched by natural path (not id), fields updated in place
# ---------------------------------------------------------------------------


def test_existing_matching_node_is_updated_not_duplicated_even_with_different_ids():
    source = _new_sqlite_db()
    target = _new_sqlite_db()
    _seed_basic_tree(source)
    # Same real-world tree already exists in target too, but built in a
    # different order so its ids don't line up with source's at all.
    _seed_basic_tree(target)

    # Change the center's email on the source side only.
    source_center = source.query(OrgNode).filter(OrgNode.external_code == "900-X-C").first()
    source_center.manager_email = "new@example.com"
    source.commit()

    report = sync_service.sync_org_master(source, target, commit=True)

    assert report.nodes_created == 0  # nothing new -- same tree, matched by natural path
    assert report.nodes_updated == 1  # only the email actually differs
    assert report.nodes_unchanged == 2  # zone + cluster, untouched

    assert target.query(OrgNode).filter(OrgNode.external_code == "900-X-C").count() == 1  # never duplicated
    target_center = target.query(OrgNode).filter(OrgNode.external_code == "900-X-C").first()
    assert target_center.manager_email == "new@example.com"


# ---------------------------------------------------------------------------
# Never deletes
# ---------------------------------------------------------------------------


def test_a_row_only_present_in_target_is_never_deleted():
    source = _new_sqlite_db()
    target = _new_sqlite_db()
    _seed_basic_tree(source)
    _seed_basic_tree(target)

    # target has one extra center the source doesn't know about at all.
    zone_dim = target.query(OrgDimension).filter(OrgDimension.key == "zone").first()
    center_dim = target.query(OrgDimension).filter(OrgDimension.key == "center").first()
    cluster = target.query(OrgNode).filter(OrgNode.name == "C1").first()
    extra = OrgNode(dimension_id=center_dim.id, parent_id=cluster.id, name="Extra Center", external_code="999-EXTRA-C")
    target.add(extra)
    target.commit()

    sync_service.sync_org_master(source, target, commit=True)

    # Still there -- pushing FROM source never removes something target-only.
    assert target.query(OrgNode).filter(OrgNode.external_code == "999-EXTRA-C").count() == 1


# ---------------------------------------------------------------------------
# Symmetry: the exact same function pulls when args are swapped
# ---------------------------------------------------------------------------


def test_swapping_source_and_target_performs_a_pull_instead_of_a_push():
    local = _new_sqlite_db()
    remote = _new_sqlite_db()
    _seed_basic_tree(remote)  # data exists remotely, not locally yet

    report = sync_service.sync_org_master(remote, local, commit=True)  # "pull"

    assert report.nodes_created == 3
    assert local.query(OrgNode).filter(OrgNode.external_code == "900-X-C").count() == 1


# ---------------------------------------------------------------------------
# API layer: RBAC + "not configured" guard
# ---------------------------------------------------------------------------


def test_remote_sync_endpoints_require_admin(client):
    _register(client, "orsync_plain", "orsync_plain@example.com")
    token = _login(client, "orsync_plain")
    resp = client.post("/org/sync/remote/push", headers=_auth(token))
    assert resp.status_code == 403


def test_remote_sync_returns_clear_400_when_not_configured(client, monkeypatch):
    """Deterministic regardless of whether this dev machine's own .env
    happens to have REMOTE_DATABASE_URL set (it may, for the real manual
    push/pull feature) -- forces the actual "unset" state via monkeypatch
    so this test never depends on, or reaches out to, a real database.
    This is the exact guard an admin would hit from an instance (e.g.
    Render itself) that was never configured for this feature."""
    monkeypatch.setattr("app.services.org_master_remote_sync_service.settings.REMOTE_DATABASE_URL", None)
    admin_token = _admin(client, "orsync_admin_noconfig", "orsync_admin_noconfig@example.com")
    resp = client.post("/org/sync/remote/push", headers=_auth(admin_token))
    assert resp.status_code == 400
    assert "not set" in resp.json()["detail"].lower()

    resp = client.post("/org/sync/remote/pull", headers=_auth(admin_token))
    assert resp.status_code == 400


def test_remote_sync_returns_clear_400_when_pointed_at_its_own_database(client, monkeypatch):
    """A misconfiguration guard: REMOTE_DATABASE_URL must never equal this
    instance's own DATABASE_URL, since "syncing" a database against
    itself is a meaningless no-op at best."""
    from app.services.org_master_remote_sync_service import settings as sync_settings

    monkeypatch.setattr(sync_settings, "REMOTE_DATABASE_URL", sync_settings.DATABASE_URL)
    admin_token = _admin(client, "orsync_admin_selfconfig", "orsync_admin_selfconfig@example.com")
    resp = client.post("/org/sync/remote/push", headers=_auth(admin_token))
    assert resp.status_code == 400
    assert "identical" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Status endpoint -- lets each Data Sync card decide whether to show
# itself at all
# ---------------------------------------------------------------------------


def test_remote_sync_status_reports_false_when_not_configured(client, monkeypatch):
    monkeypatch.setattr("app.services.org_master_remote_sync_service.settings.REMOTE_DATABASE_URL", None)
    _register(client, "orsync_status_unconfigured", "orsync_status_unconfigured@example.com")
    token = _login(client, "orsync_status_unconfigured")
    resp = client.get("/org/sync/remote/status", headers=_auth(token))
    assert resp.status_code == 200
    assert resp.json() == {"configured": False}


def test_remote_sync_status_reports_true_when_configured(client, monkeypatch):
    from app.services.org_master_remote_sync_service import settings as sync_settings

    monkeypatch.setattr(sync_settings, "REMOTE_DATABASE_URL", "postgresql://fake:fake@fake-host/fake")
    _register(client, "orsync_status_configured", "orsync_status_configured@example.com")
    token = _login(client, "orsync_status_configured")
    resp = client.get("/org/sync/remote/status", headers=_auth(token))
    assert resp.status_code == 200
    assert resp.json() == {"configured": True}


def test_remote_sync_status_requires_auth(client):
    resp = client.get("/org/sync/remote/status")
    assert resp.status_code == 401

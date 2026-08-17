import os

from app.models.org import OrgNode
from app.services import org_service, org_sheet_sync_service as sync_svc
from tests.conftest import TestingSessionLocal

FIXTURE_PATH = os.path.join(os.path.dirname(__file__), "fixtures", "centers_master_sample.tsv")


def _load_fixture() -> str:
    with open(FIXTURE_PATH, "r", encoding="utf-8") as f:
        return f.read()


def _register(client, username, email, password="password123"):
    return client.post("/auth/register", json={"username": username, "email": email, "password": password})


def _login(client, username, password="password123"):
    return client.post("/auth/login", json={"username": username, "password": password}).json()["access_token"]


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _admin(client, username="sync_admin", email="sync_admin@example.com"):
    _register(client, username, email)
    from app.models.user import User

    db = TestingSessionLocal()
    try:
        db.query(User).filter(User.username == username).first().role = "Admin"
        db.commit()
    finally:
        db.close()
    return _login(client, username)


# ---------- pure parser ----------

def test_parse_finds_all_data_rows():
    parsed, skipped = sync_svc.parse_centers_master(_load_fixture(), delimiter="\t")
    assert len(parsed) == 88
    assert not skipped


def test_parse_khemnichak_row_fields():
    parsed, _ = sync_svc.parse_centers_master(_load_fixture(), delimiter="\t")
    khm = next(r for r in parsed if r.center_code == "106-BH-PTN-KHM-C")
    assert khm.center_name == "Khemnichak, Patna"
    assert khm.zone_name == "Bihar"
    assert khm.cluster_manager_name == "Santosh Kumar"
    assert khm.zonal_manager_name == "Nishant Kumar Singh"
    assert khm.zonal_mail == "nishant_s@nephroplus.com"
    assert khm.cluster_mail == "santosh.roy@nephroplus.com"
    assert khm.half_country_head is None  # genuinely blank in the source for Bihar
    assert khm.is_active is True
    assert khm.center_incharge_name == "Shrikant Ranjan"
    assert khm.center_incharge_npid == "NP38172"
    assert khm.center_mail == "bh.ptn.khm.cm@nephroplus.com"


def test_parse_south_zone_row_has_half_country_head():
    parsed, _ = sync_svc.parse_centers_master(_load_fixture(), delimiter="\t")
    bjh = next(r for r in parsed if r.center_code == "1-TS-HYD-BJH-S")
    assert bjh.zone_name == "South"
    assert bjh.half_country_head == "Krunal"


# ---------- reconciliation against the real DB ----------

def test_sync_builds_expected_hierarchy():
    db = TestingSessionLocal()
    try:
        report = sync_svc.sync_centers_master(db, _load_fixture(), delimiter="\t")
        assert report.total_rows == 88
        assert report.centers_created == 88
        assert report.centers_updated == 0
        assert not report.conflicts

        # South zone sits under half-country "Krunal"; Bihar zone has no
        # half-country head in this sample and stays top-level.
        krunal = db.query(OrgNode).filter(OrgNode.name == "Krunal").first()
        assert krunal is not None
        south = db.query(OrgNode).filter(OrgNode.name == "South", OrgNode.parent_id == krunal.id).first()
        assert south is not None

        bihar = db.query(OrgNode).filter(OrgNode.name == "Bihar", OrgNode.parent_id.is_(None)).first()
        assert bihar is not None

        khm = org_service.get_node_by_external_code(db, "106-BH-PTN-KHM-C")
        assert khm is not None
        assert khm.name == "Khemnichak, Patna"
        assert khm.is_active is True
        assert khm.manager_name == "Shrikant Ranjan"
        assert khm.manager_npid == "NP38172"
        assert khm.manager_email == "bh.ptn.khm.cm@nephroplus.com"

        cluster = db.query(OrgNode).filter(OrgNode.id == khm.parent_id).first()
        assert cluster.name == "Santosh Kumar"
        assert cluster.manager_email == "santosh.roy@nephroplus.com"
        assert cluster.parent_id == bihar.id
    finally:
        db.close()


def test_sync_is_idempotent_second_run_updates_not_creates():
    db = TestingSessionLocal()
    try:
        sync_svc.sync_centers_master(db, _load_fixture(), delimiter="\t")
        second = sync_svc.sync_centers_master(db, _load_fixture(), delimiter="\t")
        assert second.centers_created == 0
        assert second.centers_updated == 88
        assert second.half_countries_created == 0
        assert second.zones_created == 0
        assert second.clusters_created == 0
    finally:
        db.close()


def test_sync_reuses_same_cluster_across_multiple_centers():
    """Multiple centers under the same zone with the same Cluster Manager
    name must land under ONE cluster node, not one per row."""
    db = TestingSessionLocal()
    try:
        sync_svc.sync_centers_master(db, _load_fixture(), delimiter="\t")
        naveed_clusters = db.query(OrgNode).filter(OrgNode.name == "Naveed").all()
        # "Naveed" manages several South-zone centers in the fixture (T Nagar,
        # Kilpauk3/4, TNHB Road, Redhills, Anna Salai, Vadalur) -- all must
        # share a single cluster node.
        assert len(naveed_clusters) == 1
    finally:
        db.close()


def test_sync_flags_missing_zone_without_crashing():
    db = TestingSessionLocal()
    try:
        text = (
            "S. No.\tCenter Code\tCenter Name\tHospital\tActive / Closed\tZone\tStart\tStatus\tCluster\tZM\t"
            "State\tCity\tHalf Country Head\tNABH\tQM\tZQM\tBME\tBMEMob\tClusterMail\tClusterPh\tZonalMail\tZonalPh\t"
            "Category\tIncharge\tNPID\tBabylonID\tCenterMail\tMobile\tClosedDate\n"
            "1\tX-1\tNo Zone Center\tHosp\tActive\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\n"
        )
        report = sync_svc.sync_centers_master(db, text, delimiter="\t")
        assert report.centers_created == 0
        assert any("no Zone" in s.reason for s in report.skipped)
    finally:
        db.close()


def test_sync_flags_duplicate_center_name_under_same_cluster_without_aborting():
    """Two different Center Codes that happen to share the exact same
    name under the exact same cluster must not abort the whole sync --
    the second is skipped and reported, the first (and everything else)
    still gets processed."""
    db = TestingSessionLocal()
    try:
        header = (
            "S. No.\tCenter Code\tCenter Name\tHospital\tActive / Closed\tZone\tStart\tStatus\tCluster\tZM\t"
            "State\tCity\tHalf Country Head\tNABH\tQM\tZQM\tBME\tBMEMob\tClusterMail\tClusterPh\tZonalMail\tZonalPh\t"
            "Category\tIncharge\tNPID\tBabylonID\tCenterMail\tMobile\tClosedDate\n"
        )
        row1 = "1\tDUP-1\tSame Name\tHosp\tActive\tTestZone\t\t\tMgrA\tZM1\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\n"
        row2 = "2\tDUP-2\tSame Name\tHosp\tActive\tTestZone\t\t\tMgrA\tZM1\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\n"
        report = sync_svc.sync_centers_master(db, header + row1 + row2, delimiter="\t")
        assert report.centers_created == 1
        assert len(report.skipped) == 1
        assert "DUP-2" in report.skipped[0].reason
        assert org_service.get_node_by_external_code(db, "DUP-1") is not None
        assert org_service.get_node_by_external_code(db, "DUP-2") is None
    finally:
        db.close()


def test_sync_keeps_one_zone_when_half_country_head_differs_across_rows():
    """A Half Country Head sometimes personally covers as the acting Zonal
    Manager for a subset of a zone's centers -- so the same zone showing a
    different Half Country Head on different rows is expected, not a
    conflict. Both rows must land under ONE zone node (the first head seen
    stays its nominal parent), and nothing gets flagged."""
    db = TestingSessionLocal()
    try:
        header = (
            "S. No.\tCenter Code\tCenter Name\tHospital\tActive / Closed\tZone\tStart\tStatus\tCluster\tZM\t"
            "State\tCity\tHalf Country Head\tNABH\tQM\tZQM\tBME\tBMEMob\tClusterMail\tClusterPh\tZonalMail\tZonalPh\t"
            "Category\tIncharge\tNPID\tBabylonID\tCenterMail\tMobile\tClosedDate\n"
        )
        row1 = "1\tCF-1\tCenter One\tHosp\tActive\tSharedZone\t\t\tMgrA\tZM1\t\t\tHeadA\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\n"
        row2 = "2\tCF-2\tCenter Two\tHosp\tActive\tSharedZone\t\t\tMgrA\tZM1\t\t\tHeadB\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\n"
        report = sync_svc.sync_centers_master(db, header + row1 + row2, delimiter="\t")
        assert report.conflicts == []
        zones = db.query(OrgNode).filter(OrgNode.name == "SharedZone").all()
        assert len(zones) == 1
        head_a = db.query(OrgNode).filter(OrgNode.name == "HeadA").first()
        assert zones[0].parent_id == head_a.id
        c1 = org_service.get_node_by_external_code(db, "CF-1")
        c2 = org_service.get_node_by_external_code(db, "CF-2")
        assert c1.parent_id == c2.parent_id  # same cluster, therefore same zone
    finally:
        db.close()


def test_sync_clubs_numbered_zone_splits_into_one_zone():
    """'North-1' and 'North-2' are numbered splits of the same zone for
    CARVMS's own reporting -- they must collapse into a single 'North'
    zone node, not two separate ones."""
    db = TestingSessionLocal()
    try:
        header = (
            "S. No.\tCenter Code\tCenter Name\tHospital\tActive / Closed\tZone\tStart\tStatus\tCluster\tZM\t"
            "State\tCity\tHalf Country Head\tNABH\tQM\tZQM\tBME\tBMEMob\tClusterMail\tClusterPh\tZonalMail\tZonalPh\t"
            "Category\tIncharge\tNPID\tBabylonID\tCenterMail\tMobile\tClosedDate\n"
        )
        row1 = "1\tNZ-1\tCenter One\tHosp\tActive\tNorth-1\t\t\tMgrA\tAshu\t\t\tRajan\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\n"
        row2 = "2\tNZ-2\tCenter Two\tHosp\tActive\tNorth-2\t\t\tMgrB\tPraveen\t\t\tRajan\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\n"
        report = sync_svc.sync_centers_master(db, header + row1 + row2, delimiter="\t")
        assert report.zones_created == 1
        norths = db.query(OrgNode).filter(OrgNode.name.like("North%")).all()
        assert [n.name for n in norths] == ["North"]
        c1 = org_service.get_node_by_external_code(db, "NZ-1")
        c2 = org_service.get_node_by_external_code(db, "NZ-2")
        zone1 = db.query(OrgNode).filter(OrgNode.id == db.query(OrgNode).filter(OrgNode.id == c1.parent_id).first().parent_id).first()
        zone2 = db.query(OrgNode).filter(OrgNode.id == db.query(OrgNode).filter(OrgNode.id == c2.parent_id).first().parent_id).first()
        assert zone1.id == zone2.id == norths[0].id
    finally:
        db.close()


def test_sync_clubs_city_suffixed_zone_splits_into_one_zone():
    """'KA PPP - Bng' and 'KA PPP - Mysuru' are the same base zone with a
    city tag appended -- they must collapse into a single 'KA PPP' zone,
    same rule as the numbered North-1/North-2 case, not a special case."""
    db = TestingSessionLocal()
    try:
        header = (
            "S. No.\tCenter Code\tCenter Name\tHospital\tActive / Closed\tZone\tStart\tStatus\tCluster\tZM\t"
            "State\tCity\tHalf Country Head\tNABH\tQM\tZQM\tBME\tBMEMob\tClusterMail\tClusterPh\tZonalMail\tZonalPh\t"
            "Category\tIncharge\tNPID\tBabylonID\tCenterMail\tMobile\tClosedDate\n"
        )
        row1 = "1\tKP-1\tCenter One\tHosp\tActive\tKA PPP - Bng\t\t\tMgrA\tSudhakar\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\n"
        row2 = "2\tKP-2\tCenter Two\tHosp\tActive\tKA PPP - Mysuru\t\t\tMgrB\tSudhakar\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\n"
        report = sync_svc.sync_centers_master(db, header + row1 + row2, delimiter="\t")
        assert report.zones_created == 1
        zones = db.query(OrgNode).filter(OrgNode.name.like("KA PPP%")).all()
        assert [z.name for z in zones] == ["KA PPP"]
    finally:
        db.close()


def test_sync_falls_back_to_half_country_head_as_zonal_manager():
    """When a row has no Zonal Manager of its own, the zone's manager_name
    falls back to the Half Country Head -- some centers are genuinely
    covered this way rather than by a dedicated Zonal Manager."""
    db = TestingSessionLocal()
    try:
        header = (
            "S. No.\tCenter Code\tCenter Name\tHospital\tActive / Closed\tZone\tStart\tStatus\tCluster\tZM\t"
            "State\tCity\tHalf Country Head\tNABH\tQM\tZQM\tBME\tBMEMob\tClusterMail\tClusterPh\tZonalMail\tZonalPh\t"
            "Category\tIncharge\tNPID\tBabylonID\tCenterMail\tMobile\tClosedDate\n"
        )
        row = "1\tHF-1\tCenter One\tHosp\tActive\tWestLike\t\t\tMgrA\t\t\t\tKrunal\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\n"
        sync_svc.sync_centers_master(db, header + row, delimiter="\t")
        zone = db.query(OrgNode).filter(OrgNode.name == "WestLike").first()
        assert zone.manager_name == "Krunal"
    finally:
        db.close()


def test_sync_treats_excel_error_values_as_blank():
    db = TestingSessionLocal()
    try:
        header = (
            "S. No.\tCenter Code\tCenter Name\tHospital\tActive / Closed\tZone\tStart\tStatus\tCluster\tZM\t"
            "State\tCity\tHalf Country Head\tNABH\tQM\tZQM\tBME\tBMEMob\tClusterMail\tClusterPh\tZonalMail\tZonalPh\t"
            "Category\tIncharge\tNPID\tBabylonID\tCenterMail\tMobile\tClosedDate\n"
        )
        row = "1\tERR-1\tError Center\tHosp\t#N/A\tErrZone\t\t#N/A\t#REF!\t#N/A\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\n"
        report = sync_svc.sync_centers_master(db, header + row, delimiter="\t")
        assert report.centers_created == 1
        node = org_service.get_node_by_external_code(db, "ERR-1")
        assert node.is_active is False  # "#N/A" active-status is not "active"
        # cluster manager name was "#REF!" -> treated as blank -> center
        # placed directly under the zone, no cluster node created.
        assert report.clusters_created == 0
    finally:
        db.close()


# ---------- API surface ----------

def test_only_admin_can_trigger_upload_sync(client):
    _register(client, "sync_plain", "sync_plain@example.com")
    token = _login(client, "sync_plain")
    resp = client.post(
        "/org/sync/centers-master",
        files={"file": ("centers.tsv", _load_fixture(), "text/tab-separated-values")},
        headers=_auth(token),
    )
    assert resp.status_code == 403


def test_admin_can_upload_csv_and_get_report(client):
    token = _admin(client)
    resp = client.post(
        "/org/sync/centers-master",
        files={"file": ("centers.tsv", _load_fixture(), "text/tab-separated-values")},
        headers=_auth(token),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_rows"] == 88
    assert body["centers_created"] == 88
    assert body["conflicts"] == []


def test_from_sheet_endpoint_reports_not_configured_when_url_missing(client, monkeypatch):
    from app.config.settings import settings as app_settings

    monkeypatch.setattr(app_settings, "CENTERS_MASTER_SHEET_CSV_URL", None)
    token = _admin(client, "sync_admin2", "sync_admin2@example.com")
    resp = client.post("/org/sync/centers-master/from-sheet", headers=_auth(token))
    assert resp.status_code == 400
    assert "not configured" in resp.json()["detail"].lower()


def test_from_sheet_endpoint_surfaces_401_as_clear_error(client, monkeypatch):
    from app.config.settings import settings as app_settings

    monkeypatch.setattr(app_settings, "CENTERS_MASTER_SHEET_CSV_URL", "https://example.com/fake-sheet.csv")

    class _FakeResponse:
        status_code = 401
        url = "https://example.com/fake-sheet.csv"
        text = ""

    def _fake_get(*args, **kwargs):
        return _FakeResponse()

    monkeypatch.setattr("app.api.org.httpx.get", _fake_get)
    token = _admin(client, "sync_admin3", "sync_admin3@example.com")
    resp = client.post("/org/sync/centers-master/from-sheet", headers=_auth(token))
    assert resp.status_code == 502
    assert "shared" in resp.json()["detail"].lower() or "401" in resp.json()["detail"]

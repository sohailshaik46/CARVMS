from tests.conftest import TestingSessionLocal
from app.models.user import User


def _register(client, username, email, password="password123"):
    return client.post(
        "/auth/register",
        json={"username": username, "email": email, "password": password},
    )


def _login(client, username, password="password123"):
    resp = client.post("/auth/login", json={"username": username, "password": password})
    return resp.json()["access_token"]


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _make_admin_and_login(client, username="org_admin", email="org_admin@example.com"):
    _register(client, username, email)
    db = TestingSessionLocal()
    try:
        user = db.query(User).filter(User.username == username).first()
        user.role = "Admin"
        db.commit()
    finally:
        db.close()
    return _login(client, username)


# ---------- dimensions ----------

def test_dimensions_seeded_by_default(client):
    _register(client, "reader", "reader@example.com")
    token = _login(client, "reader")

    resp = client.get("/org/dimensions", headers=_auth(token))
    assert resp.status_code == 200
    keys = [d["key"] for d in resp.json()]
    assert keys == ["half_country", "zone", "zonal_manager", "cluster", "center", "employee"]


def test_anonymous_cannot_read_dimensions(client):
    resp = client.get("/org/dimensions")
    assert resp.status_code == 401


def test_non_admin_cannot_create_dimension(client):
    _register(client, "reader2", "reader2@example.com")
    token = _login(client, "reader2")
    resp = client.post(
        "/org/dimensions",
        json={"key": "custom_level", "label": "Custom Level", "sort_order": 8},
        headers=_auth(token),
    )
    assert resp.status_code == 403


def test_admin_can_create_custom_dimension(client):
    token = _make_admin_and_login(client)
    resp = client.post(
        "/org/dimensions",
        json={"key": "custom_level", "label": "Custom Level", "sort_order": 8},
        headers=_auth(token),
    )
    assert resp.status_code == 201
    assert resp.json()["key"] == "custom_level"


def test_duplicate_dimension_key_rejected(client):
    token = _make_admin_and_login(client)
    resp = client.post(
        "/org/dimensions",
        json={"key": "zone", "label": "Zone Again", "sort_order": 99},
        headers=_auth(token),
    )
    assert resp.status_code == 400


# ---------- nodes ----------

def _get_dimension_id(client, token, key):
    dims = client.get("/org/dimensions", headers=_auth(token)).json()
    return next(d["id"] for d in dims if d["key"] == key)


def test_admin_can_build_a_tree_and_read_it_back(client):
    token = _make_admin_and_login(client)
    zone_id = _get_dimension_id(client, token, "zone")
    center_id = _get_dimension_id(client, token, "center")

    zone_resp = client.post(
        "/org/nodes",
        json={"dimension_id": zone_id, "parent_id": None, "name": "South Zone"},
        headers=_auth(token),
    )
    assert zone_resp.status_code == 201
    zone_node_id = zone_resp.json()["id"]

    center_resp = client.post(
        "/org/nodes",
        json={
            "dimension_id": center_id,
            "parent_id": zone_node_id,
            "name": "Hyderabad Center",
            "external_code": "HYD-01",
        },
        headers=_auth(token),
    )
    assert center_resp.status_code == 201
    center_node_id = center_resp.json()["id"]

    detail = client.get(f"/org/nodes/{center_node_id}", headers=_auth(token)).json()
    assert detail["name"] == "Hyderabad Center"
    assert detail["external_code"] == "HYD-01"
    assert [p["name"] for p in detail["path"]] == ["South Zone", "Hyderabad Center"]

    children = client.get(
        f"/org/nodes?parent_id={zone_node_id}", headers=_auth(token)
    ).json()
    assert [c["name"] for c in children] == ["Hyderabad Center"]


def test_duplicate_sibling_name_rejected(client):
    token = _make_admin_and_login(client)
    zone_id = _get_dimension_id(client, token, "zone")

    client.post(
        "/org/nodes",
        json={"dimension_id": zone_id, "parent_id": None, "name": "North Zone"},
        headers=_auth(token),
    )
    resp = client.post(
        "/org/nodes",
        json={"dimension_id": zone_id, "parent_id": None, "name": "North Zone"},
        headers=_auth(token),
    )
    assert resp.status_code == 400


def test_create_node_with_unknown_dimension_rejected(client):
    token = _make_admin_and_login(client)
    resp = client.post(
        "/org/nodes",
        json={"dimension_id": 999999, "parent_id": None, "name": "Ghost"},
        headers=_auth(token),
    )
    assert resp.status_code == 404


def test_non_admin_cannot_create_node(client):
    admin_token = _make_admin_and_login(client)
    zone_id = _get_dimension_id(client, admin_token, "zone")

    _register(client, "plain_org_user", "plain_org_user@example.com")
    token = _login(client, "plain_org_user")

    resp = client.post(
        "/org/nodes",
        json={"dimension_id": zone_id, "parent_id": None, "name": "East Zone"},
        headers=_auth(token),
    )
    assert resp.status_code == 403


# ---------- node is_active / update (org master, ongoing maintenance) ----------

def test_new_node_defaults_active(client):
    token = _make_admin_and_login(client, "org_admin2", "org_admin2@example.com")
    zone_id = _get_dimension_id(client, token, "zone")
    resp = client.post(
        "/org/nodes", json={"dimension_id": zone_id, "parent_id": None, "name": "Active Zone"},
        headers=_auth(token),
    )
    assert resp.json()["is_active"] is True


def test_admin_can_deactivate_and_reactivate_node(client):
    token = _make_admin_and_login(client, "org_admin3", "org_admin3@example.com")
    zone_id = _get_dimension_id(client, token, "zone")
    node = client.post(
        "/org/nodes", json={"dimension_id": zone_id, "parent_id": None, "name": "Closing Zone"},
        headers=_auth(token),
    ).json()

    resp = client.patch(f"/org/nodes/{node['id']}", json={"is_active": False}, headers=_auth(token))
    assert resp.status_code == 200
    assert resp.json()["is_active"] is False

    resp = client.patch(f"/org/nodes/{node['id']}", json={"is_active": True}, headers=_auth(token))
    assert resp.json()["is_active"] is True


def test_admin_can_update_external_code(client):
    token = _make_admin_and_login(client, "org_admin4", "org_admin4@example.com")
    center_id = _get_dimension_id(client, token, "center")
    node = client.post(
        "/org/nodes", json={"dimension_id": center_id, "parent_id": None, "name": "Recode Center"},
        headers=_auth(token),
    ).json()
    assert node["external_code"] is None

    resp = client.patch(
        f"/org/nodes/{node['id']}", json={"external_code": "RCC-01"}, headers=_auth(token)
    )
    assert resp.json()["external_code"] == "RCC-01"


def test_update_node_rejects_duplicate_sibling_name(client):
    token = _make_admin_and_login(client, "org_admin5", "org_admin5@example.com")
    zone_id = _get_dimension_id(client, token, "zone")
    client.post(
        "/org/nodes", json={"dimension_id": zone_id, "parent_id": None, "name": "Existing Zone"},
        headers=_auth(token),
    )
    node = client.post(
        "/org/nodes", json={"dimension_id": zone_id, "parent_id": None, "name": "Renamable Zone"},
        headers=_auth(token),
    ).json()

    resp = client.patch(
        f"/org/nodes/{node['id']}", json={"name": "Existing Zone"}, headers=_auth(token)
    )
    assert resp.status_code == 400


def test_update_node_404_for_unknown_node(client):
    token = _make_admin_and_login(client, "org_admin6", "org_admin6@example.com")
    resp = client.patch("/org/nodes/999999", json={"is_active": False}, headers=_auth(token))
    assert resp.status_code == 404


def test_non_admin_cannot_update_node(client):
    admin_token = _make_admin_and_login(client, "org_admin7", "org_admin7@example.com")
    zone_id = _get_dimension_id(client, admin_token, "zone")
    node = client.post(
        "/org/nodes", json={"dimension_id": zone_id, "parent_id": None, "name": "Guarded Zone"},
        headers=_auth(admin_token),
    ).json()

    _register(client, "plain_org_user2", "plain_org_user2@example.com")
    token = _login(client, "plain_org_user2")
    resp = client.patch(f"/org/nodes/{node['id']}", json={"is_active": False}, headers=_auth(token))
    assert resp.status_code == 403


# ---------- assigning a manager (User) to an org node ----------

def test_admin_can_assign_and_unassign_user_to_org_node(client):
    token = _make_admin_and_login(client, "org_admin8", "org_admin8@example.com")
    zone_id = _get_dimension_id(client, token, "zone")
    node = client.post(
        "/org/nodes", json={"dimension_id": zone_id, "parent_id": None, "name": "Manager Zone"},
        headers=_auth(token),
    ).json()

    _register(client, "future_zonal_mgr", "future_zonal_mgr@example.com")
    db = TestingSessionLocal()
    try:
        target = db.query(User).filter(User.username == "future_zonal_mgr").first()
        target_id = target.id
        target.role = "Zonal Manager"
        db.commit()
    finally:
        db.close()

    resp = client.patch(
        f"/users/{target_id}/org-node", json={"org_node_id": node["id"]}, headers=_auth(token)
    )
    assert resp.status_code == 200
    assert resp.json()["org_node_id"] == node["id"]

    # Unassign (manager left) -- None is a legitimate, explicit state.
    resp = client.patch(f"/users/{target_id}/org-node", json={"org_node_id": None}, headers=_auth(token))
    assert resp.status_code == 200
    assert resp.json()["org_node_id"] is None


def test_assign_org_node_404_for_unknown_node(client):
    token = _make_admin_and_login(client, "org_admin9", "org_admin9@example.com")
    _register(client, "future_zonal_mgr2", "future_zonal_mgr2@example.com")
    db = TestingSessionLocal()
    try:
        target_id = db.query(User).filter(User.username == "future_zonal_mgr2").first().id
    finally:
        db.close()

    resp = client.patch(
        f"/users/{target_id}/org-node", json={"org_node_id": 999999}, headers=_auth(token)
    )
    assert resp.status_code == 404


def test_non_admin_cannot_assign_org_node(client):
    admin_token = _make_admin_and_login(client, "org_admin10", "org_admin10@example.com")
    _register(client, "future_zonal_mgr3", "future_zonal_mgr3@example.com")
    db = TestingSessionLocal()
    try:
        target_id = db.query(User).filter(User.username == "future_zonal_mgr3").first().id
    finally:
        db.close()

    _register(client, "plain_org_user3", "plain_org_user3@example.com")
    token = _login(client, "plain_org_user3")
    resp = client.patch(f"/users/{target_id}/org-node", json={"org_node_id": None}, headers=_auth(token))
    assert resp.status_code == 403


# ---------- lookup helpers used by upload-driven automation ----------

def test_get_node_by_external_code_and_find_ancestor():
    from app.services import org_service

    db = TestingSessionLocal()
    try:
        org_service.seed_default_dimensions_if_missing(db)
        zone_dim = db.query(org_service.OrgDimension).filter_by(key="zone").first()
        center_dim = db.query(org_service.OrgDimension).filter_by(key="center").first()

        zone = org_service.create_node(db, dimension_id=zone_dim.id, parent_id=None, name="Lookup Zone", external_code=None)
        center = org_service.create_node(
            db, dimension_id=center_dim.id, parent_id=zone.id, name="Lookup Center", external_code="LKP-01"
        )

        found = org_service.get_node_by_external_code(db, "LKP-01")
        assert found is not None
        assert found.id == center.id

        assert org_service.get_node_by_external_code(db, "DOES-NOT-EXIST") is None

        ancestor_zone = org_service.find_ancestor_by_dimension_key(db, center, "zone")
        assert ancestor_zone is not None
        assert ancestor_zone.id == zone.id

        # A node IS its own ancestor for its own dimension.
        assert org_service.find_ancestor_by_dimension_key(db, center, "center").id == center.id

        # No such ancestor dimension above this node.
        assert org_service.find_ancestor_by_dimension_key(db, zone, "center") is None
    finally:
        db.close()

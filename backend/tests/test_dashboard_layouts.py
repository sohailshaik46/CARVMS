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


def _basic_config(**overrides):
    config = {
        "visible_kpis": ["total_audits", "total_financial_exposure"],
        "show_status_chart": True,
        "show_severity_chart": False,
        "default_filters": {"status": "Draft"},
    }
    config.update(overrides)
    return config


def test_create_and_get_private_layout(client):
    _register(client, "dl_user", "dl_user@example.com")
    token = _login(client, "dl_user")

    resp = client.post(
        "/dashboard-layouts",
        json={"name": "My Dashboard", "config": _basic_config(), "is_shared": False},
        headers=_auth(token),
    )
    assert resp.status_code == 201
    layout = resp.json()
    assert layout["is_shared"] is False
    assert layout["config"]["visible_kpis"] == ["total_audits", "total_financial_exposure"]

    fetched = client.get(f"/dashboard-layouts/{layout['id']}", headers=_auth(token)).json()
    assert fetched["id"] == layout["id"]


def test_rejects_unknown_kpi_key(client):
    _register(client, "dl_user2", "dl_user2@example.com")
    token = _login(client, "dl_user2")

    resp = client.post(
        "/dashboard-layouts",
        json={"name": "Bad", "config": _basic_config(visible_kpis=["not_a_real_kpi"])},
        headers=_auth(token),
    )
    assert resp.status_code == 422


def test_private_layout_not_visible_to_other_users(client):
    _register(client, "dl_owner", "dl_owner@example.com")
    owner_token = _login(client, "dl_owner")
    layout = client.post(
        "/dashboard-layouts",
        json={"name": "Private", "config": _basic_config(), "is_shared": False},
        headers=_auth(owner_token),
    ).json()

    _register(client, "dl_stranger", "dl_stranger@example.com")
    stranger_token = _login(client, "dl_stranger")

    resp = client.get(f"/dashboard-layouts/{layout['id']}", headers=_auth(stranger_token))
    assert resp.status_code == 404

    listing = client.get("/dashboard-layouts", headers=_auth(stranger_token)).json()
    assert layout["id"] not in [l["id"] for l in listing]


def test_shared_layout_visible_to_everyone(client):
    _register(client, "dl_owner2", "dl_owner2@example.com")
    owner_token = _login(client, "dl_owner2")
    layout = client.post(
        "/dashboard-layouts",
        json={"name": "South Zone Dashboard", "config": _basic_config(), "is_shared": True},
        headers=_auth(owner_token),
    ).json()

    _register(client, "dl_viewer", "dl_viewer@example.com")
    viewer_token = _login(client, "dl_viewer")

    resp = client.get(f"/dashboard-layouts/{layout['id']}", headers=_auth(viewer_token))
    assert resp.status_code == 200

    listing = client.get("/dashboard-layouts", headers=_auth(viewer_token)).json()
    assert layout["id"] in [l["id"] for l in listing]


def test_only_owner_or_admin_can_edit_or_delete(client):
    _register(client, "dl_owner3", "dl_owner3@example.com")
    owner_token = _login(client, "dl_owner3")
    layout = client.post(
        "/dashboard-layouts",
        json={"name": "Shared Layout", "config": _basic_config(), "is_shared": True},
        headers=_auth(owner_token),
    ).json()

    _register(client, "dl_stranger2", "dl_stranger2@example.com")
    stranger_token = _login(client, "dl_stranger2")

    edit_resp = client.patch(
        f"/dashboard-layouts/{layout['id']}", json={"name": "Hijacked"}, headers=_auth(stranger_token)
    )
    assert edit_resp.status_code == 403

    delete_resp = client.delete(f"/dashboard-layouts/{layout['id']}", headers=_auth(stranger_token))
    assert delete_resp.status_code == 403

    ok_edit = client.patch(
        f"/dashboard-layouts/{layout['id']}", json={"name": "Renamed"}, headers=_auth(owner_token)
    )
    assert ok_edit.status_code == 200
    assert ok_edit.json()["name"] == "Renamed"


def test_admin_can_edit_or_delete_others_layout(client):
    _register(client, "dl_owner4", "dl_owner4@example.com")
    owner_token = _login(client, "dl_owner4")
    layout = client.post(
        "/dashboard-layouts",
        json={"name": "Needs admin cleanup", "config": _basic_config(), "is_shared": True},
        headers=_auth(owner_token),
    ).json()

    _register(client, "dl_admin2", "dl_admin2@example.com")
    db2 = TestingSessionLocal()
    try:
        u = db2.query(User).filter(User.username == "dl_admin2").first()
        u.role = "Admin"
        db2.commit()
    finally:
        db2.close()
    admin_token = _login(client, "dl_admin2")

    resp = client.delete(f"/dashboard-layouts/{layout['id']}", headers=_auth(admin_token))
    assert resp.status_code == 204


def test_anonymous_cannot_access_layouts(client):
    assert client.get("/dashboard-layouts").status_code == 401
    assert client.post("/dashboard-layouts", json={"name": "x", "config": _basic_config()}).status_code == 401

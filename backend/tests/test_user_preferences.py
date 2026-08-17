from app.models.user_preference import DEFAULT_DASHBOARD_CONFIG


def _register(client, username, email, password="password123"):
    return client.post("/auth/register", json={"username": username, "email": email, "password": password})


def _login(client, username, password="password123"):
    return client.post("/auth/login", json={"username": username, "password": password}).json()["access_token"]


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def test_get_preferences_defaults_without_prior_row(client):
    _register(client, "pref_user1", "pref_user1@example.com")
    token = _login(client, "pref_user1")
    resp = client.get("/me/preferences", headers=_auth(token))
    assert resp.status_code == 200
    body = resp.json()
    assert body["theme"] == "dark"
    assert body["dashboard_config"] == DEFAULT_DASHBOARD_CONFIG
    assert body["notification_prefs"]["email_on_new_case"] is True
    assert body["security_settings"]["session_timeout_minutes"] == 60


def test_update_theme_only_leaves_other_fields_untouched(client):
    _register(client, "pref_user2", "pref_user2@example.com")
    token = _login(client, "pref_user2")
    client.get("/me/preferences", headers=_auth(token))  # lazily creates the row

    resp = client.put("/me/preferences", json={"theme": "light"}, headers=_auth(token))
    assert resp.status_code == 200
    body = resp.json()
    assert body["theme"] == "light"
    assert body["dashboard_config"] == DEFAULT_DASHBOARD_CONFIG  # untouched


def test_update_dashboard_config_persists_visible_kpis_and_order(client):
    _register(client, "pref_user3", "pref_user3@example.com")
    token = _login(client, "pref_user3")
    new_config = {"visible_kpis": ["wrc_penalty", "dcb_validated_penalty"]}
    resp = client.put("/me/preferences", json={"dashboard_config": new_config}, headers=_auth(token))
    assert resp.status_code == 200
    assert resp.json()["dashboard_config"] == new_config

    # persists across a fresh GET
    resp2 = client.get("/me/preferences", headers=_auth(token))
    assert resp2.json()["dashboard_config"] == new_config


def test_invalid_theme_rejected(client):
    _register(client, "pref_user4", "pref_user4@example.com")
    token = _login(client, "pref_user4")
    resp = client.put("/me/preferences", json={"theme": "neon"}, headers=_auth(token))
    assert resp.status_code == 422


def test_preferences_are_per_user_not_shared(client):
    _register(client, "pref_user5", "pref_user5@example.com")
    _register(client, "pref_user6", "pref_user6@example.com")
    token5 = _login(client, "pref_user5")
    token6 = _login(client, "pref_user6")

    client.put("/me/preferences", json={"theme": "light"}, headers=_auth(token5))
    resp6 = client.get("/me/preferences", headers=_auth(token6))
    assert resp6.json()["theme"] == "dark"  # user6 untouched by user5's change


def test_requires_authentication(client):
    resp = client.get("/me/preferences")
    assert resp.status_code == 401

import io

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


def _set_role(username, role):
    db = TestingSessionLocal()
    try:
        user = db.query(User).filter(User.username == username).first()
        user.role = role
        db.commit()
    finally:
        db.close()


def _admin(client, username="a_admin", email="a_admin@example.com"):
    _register(client, username, email)
    _set_role(username, "Admin")
    return _login(client, username)


def _upload_csv(client, token, name, content):
    return client.post(
        "/datasets",
        data={"name": name},
        files={"file": (f"{name}.csv", io.BytesIO(content), "text/csv")},
        headers=_auth(token),
    ).json()


# claim_id C1 duplicated exactly; amount 500 repeated 4x (>=3 threshold);
# amount 100000 is a wild outlier vs everything else.
ANOMALY_CSV = (
    b"claim_id,amount\n"
    b"C1,100\n"
    b"C1,100\n"
    b"C2,500\n"
    b"C3,500\n"
    b"C4,500\n"
    b"C5,500\n"
    b"C6,110\n"
    b"C7,95\n"
    b"C8,100000\n"
)


def test_duplicate_row_rule_detects_exact_duplicate(client):
    token = _admin(client)
    ds = _upload_csv(client, token, "Anomaly DS", ANOMALY_CSV)

    resp = client.post(
        f"/datasets/{ds['id']}/anomaly-scan",
        json={"rules": ["duplicate_row"]},
        headers=_auth(token),
    )
    assert resp.status_code == 201
    anomalies = resp.json()
    assert len(anomalies) == 1
    assert anomalies[0]["rule_code"] == "duplicate_row"
    assert anomalies[0]["status"] == "Open"


def test_repeated_value_rule_detects_over_threshold_repeats(client):
    token = _admin(client, "a_admin2", "a_admin2@example.com")
    ds = _upload_csv(client, token, "Anomaly DS2", ANOMALY_CSV)

    resp = client.post(
        f"/datasets/{ds['id']}/anomaly-scan",
        json={"rules": ["repeated_value"], "repeated_value_column": "amount", "repeated_value_threshold": 3},
        headers=_auth(token),
    )
    assert resp.status_code == 201
    anomalies = resp.json()
    assert len(anomalies) == 1
    assert anomalies[0]["observed_value"]["value"] == 500
    assert anomalies[0]["observed_value"]["occurrence_count"] == 4


def test_repeated_value_rule_requires_column(client):
    token = _admin(client, "a_admin3", "a_admin3@example.com")
    ds = _upload_csv(client, token, "Anomaly DS3", ANOMALY_CSV)

    resp = client.post(
        f"/datasets/{ds['id']}/anomaly-scan",
        json={"rules": ["repeated_value"]},
        headers=_auth(token),
    )
    assert resp.status_code == 400


def test_outlier_iqr_rule_detects_the_wild_value(client):
    token = _admin(client, "a_admin4", "a_admin4@example.com")
    ds = _upload_csv(client, token, "Anomaly DS4", ANOMALY_CSV)

    resp = client.post(
        f"/datasets/{ds['id']}/anomaly-scan",
        json={"rules": ["outlier_iqr"], "outlier_column": "amount"},
        headers=_auth(token),
    )
    assert resp.status_code == 201
    anomalies = resp.json()
    assert len(anomalies) == 1
    assert anomalies[0]["observed_value"]["value"] == 100000


def test_unknown_rule_rejected(client):
    token = _admin(client, "a_admin5", "a_admin5@example.com")
    ds = _upload_csv(client, token, "Anomaly DS5", ANOMALY_CSV)

    resp = client.post(
        f"/datasets/{ds['id']}/anomaly-scan",
        json={"rules": ["made_up_rule"]},
        headers=_auth(token),
    )
    assert resp.status_code == 422


# ---------- lifecycle: list / dismiss ----------

def test_dismiss_anomaly(client):
    token = _admin(client, "a_admin6", "a_admin6@example.com")
    ds = _upload_csv(client, token, "Anomaly DS6", ANOMALY_CSV)
    anomaly = client.post(
        f"/datasets/{ds['id']}/anomaly-scan",
        json={"rules": ["duplicate_row"]},
        headers=_auth(token),
    ).json()[0]

    resp = client.post(
        f"/anomalies/{anomaly['id']}/dismiss",
        json={"reason": "Confirmed legitimate resubmission by center"},
        headers=_auth(token),
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "Dismissed"
    assert resp.json()["dismissed_reason"] == "Confirmed legitimate resubmission by center"


def test_list_and_get_anomalies(client):
    token = _admin(client, "a_admin10", "a_admin10@example.com")
    ds = _upload_csv(client, token, "Anomaly DS10", ANOMALY_CSV)
    created = client.post(
        f"/datasets/{ds['id']}/anomaly-scan",
        json={"rules": ["duplicate_row", "repeated_value"], "repeated_value_column": "amount"},
        headers=_auth(token),
    ).json()
    assert len(created) == 2

    listing = client.get(f"/datasets/{ds['id']}/anomalies", headers=_auth(token)).json()
    assert len(listing) == 2

    fetched = client.get(f"/anomalies/{created[0]['id']}", headers=_auth(token)).json()
    assert fetched["id"] == created[0]["id"]


def test_anonymous_cannot_scan(client):
    resp = client.post("/datasets/1/anomaly-scan", json={"rules": ["duplicate_row"]})
    assert resp.status_code == 401

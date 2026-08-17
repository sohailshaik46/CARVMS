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


def _admin(client, username="r_admin", email="r_admin@example.com"):
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


CSV_A = (
    b"claim_id,amount,center\n"
    b"C1,1000,Hyderabad\n"
    b"C2,2000,Delhi\n"
    b"C3,3000,Chennai\n"
)

# C1 matches, C2 has a different amount (mismatch), C3 missing from B,
# C4 only exists in B (extra).
CSV_B = (
    b"claim_id,amount,center\n"
    b"C1,1000,Hyderabad\n"
    b"C2,2500,Delhi\n"
    b"C4,400,Mumbai\n"
)


def test_reconciliation_finds_matched_mismatched_missing_extra(client):
    token = _admin(client)
    ds_a = _upload_csv(client, token, "System A Claims", CSV_A)
    ds_b = _upload_csv(client, token, "System B Claims", CSV_B)

    resp = client.post(
        "/reconciliations",
        json={
            "dataset_a_id": ds_a["id"],
            "dataset_b_id": ds_b["id"],
            "key_column_a": "claim_id",
            "key_column_b": "claim_id",
        },
        headers=_auth(token),
    )
    assert resp.status_code == 201
    body = resp.json()

    assert body["status"] == "completed"
    assert body["matched_count"] == 1  # C1
    assert body["mismatched_count"] == 1  # C2 (amount differs)
    assert body["missing_in_b_count"] == 1  # C3
    assert body["extra_in_b_count"] == 1  # C4

    details = body["details_json"]
    assert details["mismatched_examples"][0]["key"] == "C2"
    assert details["mismatched_examples"][0]["diffs"]["amount"] == {"a": 2000, "b": 2500}
    assert details["missing_in_b_examples"] == ["C3"]
    assert details["extra_in_b_examples"] == ["C4"]
    assert details["mismatched_examples_truncated"] is False


def test_reconciliation_respects_explicit_compare_columns(client):
    token = _admin(client, "r_admin2", "r_admin2@example.com")
    ds_a = _upload_csv(client, token, "A2", CSV_A)
    ds_b = _upload_csv(client, token, "B2", CSV_B)

    # Only compare 'center' -- C2's amount differs but center doesn't, so
    # C2 should now count as matched, not mismatched.
    resp = client.post(
        "/reconciliations",
        json={
            "dataset_a_id": ds_a["id"],
            "dataset_b_id": ds_b["id"],
            "key_column_a": "claim_id",
            "key_column_b": "claim_id",
            "compare_columns": ["center"],
        },
        headers=_auth(token),
    )
    body = resp.json()
    assert body["matched_count"] == 2  # C1 and C2 now both match on center
    assert body["mismatched_count"] == 0


def test_reconciliation_rejects_unknown_key_column(client):
    token = _admin(client, "r_admin3", "r_admin3@example.com")
    ds_a = _upload_csv(client, token, "A3", CSV_A)
    ds_b = _upload_csv(client, token, "B3", CSV_B)

    resp = client.post(
        "/reconciliations",
        json={
            "dataset_a_id": ds_a["id"],
            "dataset_b_id": ds_b["id"],
            "key_column_a": "not_a_real_column",
            "key_column_b": "claim_id",
        },
        headers=_auth(token),
    )
    assert resp.status_code == 400


def test_reconciliation_rejects_non_tabular_dataset(client):
    token = _admin(client, "r_admin4", "r_admin4@example.com")
    ds_a = _upload_csv(client, token, "A4", CSV_A)
    ds_pdf = client.post(
        "/datasets",
        data={"name": "Some PDF"},
        files={"file": ("r.pdf", io.BytesIO(b"%PDF-1.4"), "application/pdf")},
        headers=_auth(token),
    ).json()

    resp = client.post(
        "/reconciliations",
        json={
            "dataset_a_id": ds_a["id"],
            "dataset_b_id": ds_pdf["id"],
            "key_column_a": "claim_id",
            "key_column_b": "claim_id",
        },
        headers=_auth(token),
    )
    assert resp.status_code == 400


def test_reconciliation_is_listed_and_retrievable(client):
    token = _admin(client, "r_admin5", "r_admin5@example.com")
    ds_a = _upload_csv(client, token, "A5", CSV_A)
    ds_b = _upload_csv(client, token, "B5", CSV_B)

    created = client.post(
        "/reconciliations",
        json={
            "dataset_a_id": ds_a["id"],
            "dataset_b_id": ds_b["id"],
            "key_column_a": "claim_id",
            "key_column_b": "claim_id",
        },
        headers=_auth(token),
    ).json()

    listing = client.get(f"/reconciliations?dataset_id={ds_a['id']}", headers=_auth(token)).json()
    assert any(r["id"] == created["id"] for r in listing)

    fetched = client.get(f"/reconciliations/{created['id']}", headers=_auth(token)).json()
    assert fetched["id"] == created["id"]
    assert fetched["matched_count"] == 1


def test_anonymous_cannot_run_reconciliation(client):
    resp = client.post(
        "/reconciliations",
        json={"dataset_a_id": 1, "dataset_b_id": 2, "key_column_a": "x", "key_column_b": "x"},
    )
    assert resp.status_code == 401

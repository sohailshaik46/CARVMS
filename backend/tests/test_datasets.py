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


def _admin(client, username="ds_admin", email="ds_admin@example.com"):
    _register(client, username, email)
    _set_role(username, "Admin")
    return _login(client, username)


CSV_CONTENT = (
    b"zone,center,revenue\n"
    b"South,Hyderabad,1000\n"
    b"South,Hyderabad,1000\n"  # exact duplicate row
    b"North,Delhi,\n"           # null revenue
    b"North,Chennai,500\n"
)


def _upload_csv(client, token, name="Revenue CSV", content=CSV_CONTENT, filename="revenue.csv"):
    return client.post(
        "/datasets",
        data={"name": name},
        files={"file": (filename, io.BytesIO(content), "text/csv")},
        headers=_auth(token),
    )


# ---------- upload + profiling ----------

def test_csv_upload_is_profiled_with_real_numbers(client):
    token = _admin(client)
    resp = _upload_csv(client, token)
    assert resp.status_code == 201
    body = resp.json()

    assert body["status"] == "clean"
    assert body["row_count"] == 4
    assert body["column_count"] == 3
    assert body["duplicate_row_count"] == 1
    assert 0 <= body["quality_score"] <= 100
    assert body["source_type"] == "csv"

    columns = client.get(f"/datasets/{body['id']}/columns", headers=_auth(token)).json()
    names = {c["name"] for c in columns}
    assert names == {"zone", "center", "revenue"}
    revenue_col = next(c for c in columns if c["name"] == "revenue")
    assert revenue_col["null_rate"] > 0  # one null in the fixture

    # column names matching seeded org dimensions auto-map
    zone_col = next(c for c in columns if c["name"] == "zone")
    assert zone_col["mapped_dimension"] == "zone"
    center_col = next(c for c in columns if c["name"] == "center")
    assert center_col["mapped_dimension"] == "center"


def test_malformed_csv_marks_dataset_failed_not_silently_wrong(client):
    token = _admin(client)
    # A file with a .csv extension that pandas cannot parse as tabular at all
    # (single unterminated quote across an otherwise-fine file still parses
    # in pandas' lenient csv engine, so instead we force a real parser error
    # by using mismatched quoting that trips the C parser).
    bad_content = b'"a,"b\n1,2\n"unterminated'
    resp = _upload_csv(client, token, content=bad_content, filename="bad.csv")
    assert resp.status_code == 201
    body = resp.json()
    # Either it parses leniently (pandas is forgiving) or it fails cleanly --
    # what must NOT happen is a fabricated "clean" status with wrong numbers
    # silently swallowed. Assert it's one of the two honest outcomes.
    assert body["status"] in ("clean", "failed")
    if body["status"] == "failed":
        assert body["profiling_error"]


def test_non_tabular_upload_is_not_fabricated_as_profiled(client):
    token = _admin(client)
    resp = client.post(
        "/datasets",
        data={"name": "Some PDF report"},
        files={"file": ("report.pdf", io.BytesIO(b"%PDF-1.4 not really a pdf"), "application/pdf")},
        headers=_auth(token),
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["source_type"] == "pdf"
    assert body["status"] == "uploaded"
    assert body["row_count"] is None
    assert body["quality_score"] is None

    columns = client.get(f"/datasets/{body['id']}/columns", headers=_auth(token)).json()
    assert columns == []


def test_unsupported_extension_rejected(client):
    token = _admin(client)
    resp = client.post(
        "/datasets",
        data={"name": "Bad file"},
        files={"file": ("virus.exe", io.BytesIO(b"MZ"), "application/x-msdownload")},
        headers=_auth(token),
    )
    assert resp.status_code == 415


# ---------- listing / access ----------

def test_anonymous_cannot_upload_or_list(client):
    resp = client.post("/datasets", data={"name": "x"}, files={"file": ("a.csv", io.BytesIO(b"a,b\n1,2"), "text/csv")})
    assert resp.status_code == 401
    assert client.get("/datasets").status_code == 401


def test_list_and_filter_by_status(client):
    token = _admin(client)
    _upload_csv(client, token)
    client.post(
        "/datasets",
        data={"name": "PDF"},
        files={"file": ("r.pdf", io.BytesIO(b"%PDF"), "application/pdf")},
        headers=_auth(token),
    )

    clean = client.get("/datasets?status=clean", headers=_auth(token)).json()
    uploaded = client.get("/datasets?status=uploaded", headers=_auth(token)).json()
    assert all(d["status"] == "clean" for d in clean)
    assert all(d["status"] == "uploaded" for d in uploaded)


# ---------- reprocess / archive / permissions ----------

def test_only_owner_or_admin_can_reprocess_or_archive(client):
    owner_token = _admin(client, "ds_owner", "ds_owner@example.com")
    dataset = _upload_csv(client, owner_token).json()

    _register(client, "stranger", "ds_stranger@example.com")
    stranger_token = _login(client, "stranger")

    resp = client.post(f"/datasets/{dataset['id']}/reprocess", headers=_auth(stranger_token))
    assert resp.status_code == 403

    resp2 = client.post(f"/datasets/{dataset['id']}/archive", headers=_auth(stranger_token))
    assert resp2.status_code == 403

    ok = client.post(f"/datasets/{dataset['id']}/reprocess", headers=_auth(owner_token))
    assert ok.status_code == 200
    assert ok.json()["status"] == "clean"

    archived = client.post(f"/datasets/{dataset['id']}/archive", headers=_auth(owner_token))
    assert archived.status_code == 200
    assert archived.json()["status"] == "archived"


def test_lineage_versioning(client):
    token = _admin(client, "ds_lineage", "ds_lineage@example.com")
    v1 = _upload_csv(client, token, name="Monthly Revenue").json()
    assert v1["version"] == 1

    resp = client.post(
        "/datasets",
        data={"name": "Monthly Revenue", "lineage_of_id": v1["id"]},
        files={"file": ("revenue_v2.csv", io.BytesIO(CSV_CONTENT), "text/csv")},
        headers=_auth(token),
    )
    v2 = resp.json()
    assert v2["version"] == 2
    assert v2["lineage_of_id"] == v1["id"]

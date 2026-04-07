from fastapi.testclient import TestClient

from pyemberstore.http_app import create_app


def _client(tmp_path):
    app = create_app(tmp_path)
    return TestClient(app)


def test_create_get_and_persist_firestore_typed_document(tmp_path):
    client = _client(tmp_path)

    payload = {
        "fields": {
            "name": {"stringValue": "Alice"},
            "age": {"integerValue": "30"},
            "active": {"booleanValue": True},
        }
    }

    create = client.post(
        "/v1/projects/local/databases/(default)/documents/users",
        params={"documentId": "alice"},
        json=payload,
    )
    assert create.status_code == 200

    get = client.get("/v1/projects/local/databases/(default)/documents/users/alice")
    assert get.status_code == 200
    body = get.json()
    assert body["name"].endswith("/documents/users/alice")
    assert body["fields"]["name"] == {"stringValue": "Alice"}
    assert body["fields"]["age"] == {"integerValue": "30"}
    assert body["fields"]["active"] == {"booleanValue": True}


def test_patch_merges_fields(tmp_path):
    client = _client(tmp_path)

    client.post(
        "/v1/projects/local/databases/(default)/documents/users",
        params={"documentId": "bob"},
        json={"fields": {"name": {"stringValue": "Bob"}, "city": {"stringValue": "Aarhus"}}},
    )

    patch = client.patch(
        "/v1/projects/local/databases/(default)/documents/users/bob",
        json={"fields": {"city": {"stringValue": "Copenhagen"}}},
    )
    assert patch.status_code == 200

    get = client.get("/v1/projects/local/databases/(default)/documents/users/bob")
    fields = get.json()["fields"]
    assert fields["name"] == {"stringValue": "Bob"}
    assert fields["city"] == {"stringValue": "Copenhagen"}


def test_list_documents(tmp_path):
    client = _client(tmp_path)

    client.post(
        "/v1/projects/local/databases/(default)/documents/users",
        params={"documentId": "u1"},
        json={"fields": {"name": {"stringValue": "A"}}},
    )
    client.post(
        "/v1/projects/local/databases/(default)/documents/users",
        params={"documentId": "u2"},
        json={"fields": {"name": {"stringValue": "B"}}},
    )

    res = client.get("/v1/projects/local/databases/(default)/documents/users")
    assert res.status_code == 200
    docs = res.json()["documents"]
    ids = sorted(doc["name"].split("/")[-1] for doc in docs)
    assert ids == ["u1", "u2"]


def test_run_query_equal_filter(tmp_path):
    client = _client(tmp_path)

    client.post(
        "/v1/projects/local/databases/(default)/documents/users",
        params={"documentId": "u1"},
        json={"fields": {"role": {"stringValue": "admin"}}},
    )
    client.post(
        "/v1/projects/local/databases/(default)/documents/users",
        params={"documentId": "u2"},
        json={"fields": {"role": {"stringValue": "user"}}},
    )

    query = {
        "structuredQuery": {
            "from": [{"collectionId": "users"}],
            "where": {
                "fieldFilter": {
                    "field": {"fieldPath": "role"},
                    "op": "EQUAL",
                    "value": {"stringValue": "admin"},
                }
            },
        }
    }

    res = client.post(
        "/v1/projects/local/databases/(default)/documents:runQuery",
        json=query,
    )
    assert res.status_code == 200
    rows = res.json()
    assert len(rows) == 1
    assert rows[0]["document"]["name"].endswith("/documents/users/u1")


def test_delete_document(tmp_path):
    client = _client(tmp_path)

    client.post(
        "/v1/projects/local/databases/(default)/documents/users",
        params={"documentId": "gone"},
        json={"fields": {"x": {"integerValue": "1"}}},
    )

    delete = client.delete("/v1/projects/local/databases/(default)/documents/users/gone")
    assert delete.status_code == 200

    get = client.get("/v1/projects/local/databases/(default)/documents/users/gone")
    assert get.status_code == 404

import json

import pytest

from pyemberstore import Client, DocumentNotFoundError


def test_set_and_get_document(tmp_path):
    client = Client(tmp_path)
    doc = client.collection("users").document("alice")

    doc.set({"name": "Alice", "age": 30})

    snapshot = doc.get()
    assert snapshot.exists is True
    assert snapshot.id == "alice"
    assert snapshot.to_dict() == {"name": "Alice", "age": 30}


def test_get_missing_document_returns_non_existing_snapshot(tmp_path):
    client = Client(tmp_path)

    snapshot = client.collection("users").document("missing").get()

    assert snapshot.exists is False
    assert snapshot.id == "missing"
    assert snapshot.to_dict() is None


def test_update_missing_document_raises(tmp_path):
    client = Client(tmp_path)

    with pytest.raises(DocumentNotFoundError):
        client.collection("users").document("missing").update({"name": "Nope"})


def test_set_merge_true_merges_shallow_fields(tmp_path):
    client = Client(tmp_path)
    doc = client.collection("users").document("bob")

    doc.set({"name": "Bob", "age": 25, "city": "Aarhus"})
    doc.set({"age": 26}, merge=True)

    assert doc.get().to_dict() == {"name": "Bob", "age": 26, "city": "Aarhus"}


def test_delete_document(tmp_path):
    client = Client(tmp_path)
    doc = client.collection("users").document("carol")

    doc.set({"name": "Carol"})
    doc.delete()

    assert doc.get().exists is False


def test_where_query_filters_documents(tmp_path):
    client = Client(tmp_path)
    users = client.collection("users")

    users.document("u1").set({"name": "A", "role": "admin", "meta": {"country": "DK"}})
    users.document("u2").set({"name": "B", "role": "user", "meta": {"country": "US"}})
    users.document("u3").set({"name": "C", "role": "admin", "meta": {"country": "US"}})

    docs = users.where("role", "==", "admin").where("meta.country", "==", "US").stream()

    assert [d.id for d in docs] == ["u3"]


def test_persists_to_json_file(tmp_path):
    client = Client(tmp_path)
    users = client.collection("users")

    users.document("a").set({"name": "A"})
    users.document("b").set({"name": "B"})

    file_path = tmp_path / "users.json"
    assert file_path.exists()

    content = json.loads(file_path.read_text())
    assert content == {
        "a": {"name": "A"},
        "b": {"name": "B"},
    }


def test_second_client_reads_existing_files(tmp_path):
    first = Client(tmp_path)
    first.collection("users").document("z").set({"name": "Zed"})

    second = Client(tmp_path)
    snapshot = second.collection("users").document("z").get()

    assert snapshot.exists is True
    assert snapshot.to_dict() == {"name": "Zed"}

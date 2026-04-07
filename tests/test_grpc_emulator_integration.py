import json
from datetime import datetime

from google.cloud import firestore
from google.cloud import firestore_v1

from pyemberstore.grpc_emulator import start_grpc_emulator


def test_firestore_client_works_via_firestore_emulator_host(tmp_path, monkeypatch):
    running = start_grpc_emulator(tmp_path, host="127.0.0.1", port=0)

    try:
        monkeypatch.setenv("FIRESTORE_EMULATOR_HOST", f"{running.host}:{running.port}")

        client = firestore.Client(project="demo-project")

        alice = client.collection("users").document("alice")
        alice.set({"name": "Alice", "age": 30, "role": "admin"})

        snap = alice.get()
        assert snap.exists is True
        assert snap.to_dict() == {"name": "Alice", "age": 30, "role": "admin"}

        alice.update({"age": 31})
        assert alice.get().to_dict()["age"] == 31

        docs = list(
            client.collection("users")
            .where(filter=firestore_v1.FieldFilter("role", "==", "admin"))
            .stream()
        )
        assert [d.id for d in docs] == ["alice"]

        alice.delete()
        assert alice.get().exists is False

        persisted = json.loads((tmp_path / "demo-project" / "(default)" / "users.json").read_text())
        assert persisted == {}
    finally:
        running.stop()


def test_server_timestamp_transform_roundtrip(tmp_path, monkeypatch):
    running = start_grpc_emulator(tmp_path, host="127.0.0.1", port=0)

    try:
        monkeypatch.setenv("FIRESTORE_EMULATOR_HOST", f"{running.host}:{running.port}")
        client = firestore.Client(project="demo-project")

        ref = client.collection("events").document("e1")
        ref.set({"name": "created", "ts": firestore.SERVER_TIMESTAMP})

        snap = ref.get()
        payload = snap.to_dict()
        assert payload["name"] == "created"
        assert isinstance(payload["ts"], datetime)

        persisted = json.loads(
            (tmp_path / "demo-project" / "(default)" / "events.json").read_text()
        )
        assert persisted["e1"]["ts"]["__pyember_type__"] == "timestamp"
        assert isinstance(persisted["e1"]["ts"]["value"], str)
    finally:
        running.stop()

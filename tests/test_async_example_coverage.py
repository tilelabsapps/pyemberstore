import asyncio

from google.cloud.firestore_v1 import (
    AsyncClient,
    ArrayRemove,
    ArrayUnion,
    DELETE_FIELD,
    SERVER_TIMESTAMP,
)
from google.cloud.firestore_v1.base_vector_query import DistanceMeasure
from google.cloud.firestore_v1.vector import Vector

from pyemberstore.grpc_emulator import start_grpc_emulator


def test_async_query_order_limit_and_create_update_patterns(tmp_path, monkeypatch):
    running = start_grpc_emulator(tmp_path, host="127.0.0.1", port=0)

    async def scenario():
        client = AsyncClient(project="demo-project")
        users = client.collection("users")

        await users.document("u1").create({"ownerSub": "a", "score": 1, "createdAt": SERVER_TIMESTAMP})
        await users.document("u2").set({"ownerSub": "a", "score": 2, "createdAt": SERVER_TIMESTAMP})
        await users.document("u3").set({"ownerSub": "b", "score": 3, "createdAt": SERVER_TIMESTAMP})

        rows = (
            await users.where("ownerSub", "==", "a")
            .order_by("score", direction="DESCENDING")
            .limit(1)
            .get()
        )
        assert len(rows) == 1
        assert rows[0].id == "u2"

        await users.document("u2").update({"profile.name": "Alice", "profile.temp": "x"})
        await users.document("u2").update({"profile.temp": DELETE_FIELD})
        got = (await users.document("u2").get()).to_dict()
        assert got["profile"] == {"name": "Alice"}

    try:
        monkeypatch.setenv("FIRESTORE_EMULATOR_HOST", f"{running.host}:{running.port}")
        asyncio.run(scenario())
    finally:
        running.stop()


def test_async_array_union_and_remove(tmp_path, monkeypatch):
    running = start_grpc_emulator(tmp_path, host="127.0.0.1", port=0)

    async def scenario():
        client = AsyncClient(project="demo-project")
        ref = client.collection("workspaces").document("w1")

        await ref.set({"sites": [{"uri": "https://a.test"}]})
        await ref.update({"sites": ArrayUnion([{"uri": "https://b.test"}, {"uri": "https://a.test"}])})
        payload = (await ref.get()).to_dict()
        assert payload["sites"] == [{"uri": "https://a.test"}, {"uri": "https://b.test"}]

        await ref.update({"sites": ArrayRemove([{"uri": "https://a.test"}])})
        payload = (await ref.get()).to_dict()
        assert payload["sites"] == [{"uri": "https://b.test"}]

    try:
        monkeypatch.setenv("FIRESTORE_EMULATOR_HOST", f"{running.host}:{running.port}")
        asyncio.run(scenario())
    finally:
        running.stop()


def test_async_vector_find_nearest(tmp_path, monkeypatch):
    running = start_grpc_emulator(tmp_path, host="127.0.0.1", port=0)

    async def scenario():
        client = AsyncClient(project="demo-project")
        col = client.collection("user_documents")

        await col.document("d1").set({"path": "one", "vector": Vector([0.0, 0.0])})
        await col.document("d2").set({"path": "two", "vector": Vector([1.0, 1.0])})
        await col.document("d3").set({"path": "three", "vector": Vector([9.0, 9.0])})

        vq = col.find_nearest(
            vector_field="vector",
            query_vector=Vector([0.9, 0.8]),
            distance_measure=DistanceMeasure.EUCLIDEAN,
            limit=2,
        )
        docs = await vq.get()
        assert [d.id for d in docs] == ["d2", "d1"]

    try:
        monkeypatch.setenv("FIRESTORE_EMULATOR_HOST", f"{running.host}:{running.port}")
        asyncio.run(scenario())
    finally:
        running.stop()

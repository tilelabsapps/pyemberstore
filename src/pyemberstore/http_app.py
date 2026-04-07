from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Query

from .client import Client


def create_app(storage_root: str | Path) -> FastAPI:
    app = FastAPI(title="Pyember Store", version="0.1.0")
    root = Path(storage_root)

    def _client_for(project: str, database: str) -> Client:
        db_root = root / project / database
        return Client(db_root)

    @app.post("/v1/projects/{project}/databases/{database}/documents/{collection_id}")
    def create_document(
        project: str,
        database: str,
        collection_id: str,
        body: dict[str, Any],
        document_id: str | None = Query(default=None, alias="documentId"),
    ) -> dict[str, Any]:
        doc_id = document_id or uuid4().hex
        ref = _client_for(project, database).collection(collection_id).document(doc_id)
        ref.set(_decode_document_body(body), merge=False)
        return _encode_document(project, database, collection_id, doc_id, ref.get().to_dict() or {})

    @app.get("/v1/projects/{project}/databases/{database}/documents/{collection_id}/{document_id}")
    def get_document(project: str, database: str, collection_id: str, document_id: str) -> dict[str, Any]:
        ref = _client_for(project, database).collection(collection_id).document(document_id)
        snap = ref.get()
        if not snap.exists:
            raise HTTPException(status_code=404, detail="Document not found")
        return _encode_document(project, database, collection_id, document_id, snap.to_dict() or {})

    @app.patch("/v1/projects/{project}/databases/{database}/documents/{collection_id}/{document_id}")
    def patch_document(
        project: str,
        database: str,
        collection_id: str,
        document_id: str,
        body: dict[str, Any],
    ) -> dict[str, Any]:
        ref = _client_for(project, database).collection(collection_id).document(document_id)
        data = _decode_document_body(body)
        if ref.get().exists:
            ref.set(data, merge=True)
        else:
            ref.set(data)
        return _encode_document(project, database, collection_id, document_id, ref.get().to_dict() or {})

    @app.delete("/v1/projects/{project}/databases/{database}/documents/{collection_id}/{document_id}")
    def delete_document(project: str, database: str, collection_id: str, document_id: str) -> dict[str, Any]:
        ref = _client_for(project, database).collection(collection_id).document(document_id)
        ref.delete()
        return {}

    @app.get("/v1/projects/{project}/databases/{database}/documents/{collection_id}")
    def list_documents(project: str, database: str, collection_id: str) -> dict[str, Any]:
        collection = _client_for(project, database).collection(collection_id)
        docs = [
            _encode_document(project, database, collection_id, snap.id, snap.to_dict() or {})
            for snap in collection.stream()
        ]
        return {"documents": docs}

    @app.post("/v1/projects/{project}/databases/{database}/documents:runQuery")
    def run_query(project: str, database: str, body: dict[str, Any]) -> list[dict[str, Any]]:
        structured = body.get("structuredQuery") or {}
        from_items = structured.get("from") or []
        if not from_items:
            raise HTTPException(status_code=400, detail="structuredQuery.from is required")

        collection_id = from_items[0].get("collectionId")
        if not collection_id:
            raise HTTPException(status_code=400, detail="collectionId is required")

        query = _client_for(project, database).collection(collection_id)
        where = structured.get("where")
        if where:
            field_filter = where.get("fieldFilter") or {}
            field = ((field_filter.get("field") or {}).get("fieldPath"))
            op = field_filter.get("op")
            value = _decode_value(field_filter.get("value"))

            if op != "EQUAL":
                raise HTTPException(status_code=400, detail=f"Unsupported fieldFilter op: {op}")
            query = query.where(field, "==", value)

        snapshots = query.stream()
        return [
            {
                "document": _encode_document(project, database, collection_id, snap.id, snap.to_dict() or {}),
            }
            for snap in snapshots
        ]

    return app


def _decode_document_body(body: dict[str, Any]) -> dict[str, Any]:
    fields = body.get("fields")
    if fields is None:
        # Accept plain JSON objects for convenience.
        return body

    return {key: _decode_value(value) for key, value in fields.items()}


def _encode_document(
    project: str,
    database: str,
    collection_id: str,
    document_id: str,
    data: dict[str, Any],
) -> dict[str, Any]:
    return {
        "name": (
            f"projects/{project}/databases/{database}/documents/{collection_id}/{document_id}"
        ),
        "fields": {key: _encode_value(value) for key, value in data.items()},
    }


def _decode_value(value: Any) -> Any:
    if not isinstance(value, dict):
        return value

    if "nullValue" in value:
        return None
    if "stringValue" in value:
        return value["stringValue"]
    if "booleanValue" in value:
        return value["booleanValue"]
    if "integerValue" in value:
        return int(value["integerValue"])
    if "doubleValue" in value:
        return float(value["doubleValue"])
    if "mapValue" in value:
        fields = value["mapValue"].get("fields", {})
        return {k: _decode_value(v) for k, v in fields.items()}
    if "arrayValue" in value:
        values = value["arrayValue"].get("values", [])
        return [_decode_value(v) for v in values]

    return value


def _encode_value(value: Any) -> dict[str, Any]:
    if value is None:
        return {"nullValue": None}
    if isinstance(value, bool):
        return {"booleanValue": value}
    if isinstance(value, int) and not isinstance(value, bool):
        return {"integerValue": str(value)}
    if isinstance(value, float):
        return {"doubleValue": value}
    if isinstance(value, str):
        return {"stringValue": value}
    if isinstance(value, list):
        return {"arrayValue": {"values": [_encode_value(v) for v in value]}}
    if isinstance(value, dict):
        return {"mapValue": {"fields": {k: _encode_value(v) for k, v in value.items()}}}

    raise TypeError(f"Unsupported value type: {type(value)!r}")

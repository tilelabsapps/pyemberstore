from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from google.cloud.firestore_v1.vector import Vector


class JSONStorage:
    """Simple JSON-file storage backend.

    One collection is persisted as one JSON file. The file content is:
    `{doc_id: document_data}`.
    """

    def __init__(self, root_path: str | Path) -> None:
        self._root = Path(root_path)
        self._root.mkdir(parents=True, exist_ok=True)

    def read_collection(self, name: str) -> dict[str, dict[str, Any]]:
        path = self._collection_path(name)
        if not path.exists():
            return {}

        with path.open("r", encoding="utf-8") as f:
            payload = json.load(f)

        if not isinstance(payload, dict):
            raise ValueError(f"Collection file {path} must contain a JSON object")

        return _decode_special_values(payload)

    def write_collection(self, name: str, documents: dict[str, dict[str, Any]]) -> None:
        path = self._collection_path(name)
        path.parent.mkdir(parents=True, exist_ok=True)

        with path.open("w", encoding="utf-8") as f:
            json.dump(_encode_special_values(documents), f, indent=2, sort_keys=True)
            f.write("\n")

    def _collection_path(self, name: str) -> Path:
        return self._root / f"{name}.json"


_TYPE_KEY = "__pyember_type__"
_VALUE_KEY = "value"
_TIMESTAMP_TYPE = "timestamp"
_VECTOR_TYPE = "vector"


def _encode_special_values(value: Any) -> Any:
    if isinstance(value, datetime):
        return {_TYPE_KEY: _TIMESTAMP_TYPE, _VALUE_KEY: value.isoformat()}
    if isinstance(value, Vector):
        return {_TYPE_KEY: _VECTOR_TYPE, _VALUE_KEY: [float(v) for v in value]}

    if isinstance(value, dict):
        return {k: _encode_special_values(v) for k, v in value.items()}

    if isinstance(value, list):
        return [_encode_special_values(v) for v in value]

    return value


def _decode_special_values(value: Any) -> Any:
    if isinstance(value, dict):
        if value.get(_TYPE_KEY) == _TIMESTAMP_TYPE and _VALUE_KEY in value:
            return datetime.fromisoformat(value[_VALUE_KEY])
        if value.get(_TYPE_KEY) == _VECTOR_TYPE and _VALUE_KEY in value:
            return Vector(value[_VALUE_KEY])
        return {k: _decode_special_values(v) for k, v in value.items()}

    if isinstance(value, list):
        return [_decode_special_values(v) for v in value]

    return value

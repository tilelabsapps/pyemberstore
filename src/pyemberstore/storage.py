from __future__ import annotations

import json
import os
import threading
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import portalocker
from google.cloud.firestore_v1.vector import Vector


class JSONStorage:
    """Simple JSON-file storage backend.

    One collection is persisted as one JSON file. The file content is:
    `{doc_id: document_data}`.
    """

    def __init__(self, root_path: str | Path) -> None:
        self._root = Path(root_path)
        self._root.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()

    def _get_active_locks(self) -> dict[str, bool]:
        """Returns a dict mapping collection name to is_exclusive boolean."""
        if not hasattr(self._local, "active_locks"):
            self._local.active_locks = {}
        return self._local.active_locks

    def lock(self, name: str, exclusive: bool = True):
        """Return a context manager for locking the collection.
        
        Note: We always use exclusive locks to avoid deadlocks and complex 
        lock upgrade scenarios in this local JSON emulator.
        """
        storage = self
        class LockContext:
            def __enter__(self):
                active = storage._get_active_locks()
                if name in active:
                    self.nested = True
                    return
                
                self.nested = False
                lock_path = storage._collection_path(name).with_suffix(".lock")
                # Always use LOCK_EX for simplicity and safety against deadlocks
                self.lock_obj = portalocker.Lock(lock_path, flags=portalocker.LOCK_EX, mode="w", timeout=60)
                self.lock_obj.__enter__()
                active[name] = True

            def __exit__(self, exc_type, exc_val, exc_tb):
                if not self.nested:
                    self.lock_obj.__exit__(exc_type, exc_val, exc_tb)
                    del storage._get_active_locks()[name]
        
        return LockContext()

    def read_collection(self, name: str) -> dict[str, dict[str, Any]]:
        path = self._collection_path(name)
        if not path.exists():
            return {}

        with self.lock(name, exclusive=False):
            with path.open("r", encoding="utf-8") as f:
                payload = json.load(f)

        if not isinstance(payload, dict):
            raise ValueError(f"Collection file {path} must contain a JSON object")

        return _decode_special_values(payload)

    def write_collection(self, name: str, documents: dict[str, dict[str, Any]]) -> None:
        path = self._collection_path(name)
        path.parent.mkdir(parents=True, exist_ok=True)

        with self.lock(name, exclusive=True):
            # Write to a temporary file first to ensure atomicity
            tmp_path = path.with_suffix(f".{uuid4().hex}.tmp")
            try:
                with tmp_path.open("w", encoding="utf-8") as f:
                    json.dump(_encode_special_values(documents), f, indent=2, sort_keys=True)
                    f.write("\n")
                    f.flush()
                    os.fsync(f.fileno())

                # Atomic rename to target path
                os.replace(tmp_path, path)
            finally:
                if tmp_path.exists():
                    tmp_path.unlink()

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

from __future__ import annotations

import copy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .errors import DocumentNotFoundError
from .storage import JSONStorage


@dataclass(frozen=True)
class DocumentSnapshot:
    id: str
    _data: dict[str, Any] | None

    @property
    def exists(self) -> bool:
        return self._data is not None

    def to_dict(self) -> dict[str, Any] | None:
        if self._data is None:
            return None
        return copy.deepcopy(self._data)


class Client:
    def __init__(self, root_path: str | Path) -> None:
        self._storage = JSONStorage(root_path)

    def collection(self, name: str) -> CollectionReference:
        return CollectionReference(self._storage, name)


class CollectionReference:
    def __init__(self, storage: JSONStorage, name: str) -> None:
        self._storage = storage
        self._name = name

    def document(self, doc_id: str) -> DocumentReference:
        return DocumentReference(self._storage, self._name, doc_id)

    def stream(self) -> list[DocumentSnapshot]:
        docs = self._storage.read_collection(self._name)
        return [DocumentSnapshot(id=doc_id, _data=copy.deepcopy(data)) for doc_id, data in docs.items()]

    def where(self, field_path: str, op_string: str, value: Any) -> Query:
        return Query(self._storage, self._name, [(field_path, op_string, value)])


class Query:
    def __init__(
        self,
        storage: JSONStorage,
        collection_name: str,
        filters: list[tuple[str, str, Any]],
    ) -> None:
        self._storage = storage
        self._collection_name = collection_name
        self._filters = filters

    def where(self, field_path: str, op_string: str, value: Any) -> Query:
        return Query(
            self._storage,
            self._collection_name,
            [*self._filters, (field_path, op_string, value)],
        )

    def stream(self) -> list[DocumentSnapshot]:
        docs = self._storage.read_collection(self._collection_name)
        matched: list[DocumentSnapshot] = []

        for doc_id, doc_data in docs.items():
            if self._matches_all_filters(doc_data):
                matched.append(DocumentSnapshot(id=doc_id, _data=copy.deepcopy(doc_data)))

        return matched

    def _matches_all_filters(self, document: dict[str, Any]) -> bool:
        for field_path, op_string, expected in self._filters:
            if op_string != "==":
                raise NotImplementedError(f"Unsupported operator: {op_string}")

            actual = _resolve_field_path(document, field_path)
            if actual != expected:
                return False

        return True


class DocumentReference:
    def __init__(self, storage: JSONStorage, collection_name: str, doc_id: str) -> None:
        self._storage = storage
        self._collection_name = collection_name
        self._doc_id = doc_id

    @property
    def id(self) -> str:
        return self._doc_id

    def get(self) -> DocumentSnapshot:
        docs = self._storage.read_collection(self._collection_name)
        if self._doc_id not in docs:
            return DocumentSnapshot(id=self._doc_id, _data=None)
        return DocumentSnapshot(id=self._doc_id, _data=copy.deepcopy(docs[self._doc_id]))

    def set(self, data: dict[str, Any], merge: bool = False) -> None:
        with self._storage.lock(self._collection_name, exclusive=True):
            docs = self._storage.read_collection(self._collection_name)

            if merge and self._doc_id in docs:
                current = docs[self._doc_id]
                docs[self._doc_id] = {**current, **copy.deepcopy(data)}
            else:
                docs[self._doc_id] = copy.deepcopy(data)

            self._storage.write_collection(self._collection_name, docs)

    def update(self, data: dict[str, Any]) -> None:
        with self._storage.lock(self._collection_name, exclusive=True):
            docs = self._storage.read_collection(self._collection_name)
            if self._doc_id not in docs:
                raise DocumentNotFoundError(
                    f"Document '{self._doc_id}' does not exist in '{self._collection_name}'"
                )

            current = docs[self._doc_id]
            docs[self._doc_id] = {**current, **copy.deepcopy(data)}
            self._storage.write_collection(self._collection_name, docs)

    def delete(self) -> None:
        with self._storage.lock(self._collection_name, exclusive=True):
            docs = self._storage.read_collection(self._collection_name)
            if self._doc_id in docs:
                del docs[self._doc_id]
                self._storage.write_collection(self._collection_name, docs)


def _resolve_field_path(document: dict[str, Any], field_path: str) -> Any:
    current: Any = document
    for part in field_path.split("."):
        if not isinstance(current, dict):
            return None
        if part not in current:
            return None
        current = current[part]
    return current

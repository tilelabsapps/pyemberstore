from __future__ import annotations

from concurrent import futures
from dataclasses import dataclass
from datetime import UTC, datetime
from math import sqrt
from pathlib import Path
import re
from typing import Any, Iterable
from uuid import uuid4

import grpc
from google.cloud.firestore_v1 import _helpers
from google.cloud.firestore_v1.types import document as document_pb
from google.cloud.firestore_v1.types import firestore as firestore_pb
from google.cloud.firestore_v1.types import query as query_pb
from google.cloud.firestore_v1.types import write as write_pb
from google.cloud.firestore_v1.vector import Vector
from google.protobuf import empty_pb2
from google.protobuf.timestamp_pb2 import Timestamp

from .client import Client

_DOCUMENT_NAME_RE = re.compile(
    r"^projects/(?P<project>[^/]+)/databases/(?P<database>[^/]+)/documents/(?P<doc_path>.+)$"
)
_DATABASE_RE = re.compile(r"^projects/(?P<project>[^/]+)/databases/(?P<database>[^/]+)$")
_PARENT_RE = re.compile(
    r"^projects/(?P<project>[^/]+)/databases/(?P<database>[^/]+)/documents(?:/(?P<parent_doc>.+))?$"
)


@dataclass
class RunningGrpcEmulator:
    server: grpc.Server
    host: str
    port: int

    def stop(self, grace: float = 0) -> None:
        self.server.stop(grace)


class FirestoreEmulatorService:
    def __init__(self, storage_root: str | Path) -> None:
        self._storage_root = Path(storage_root)
        self._storage_root.mkdir(parents=True, exist_ok=True)

    def GetDocument(
        self, request: firestore_pb.GetDocumentRequest, context: grpc.ServicerContext
    ) -> document_pb.Document:
        project, database, collection_path, doc_id = _parse_document_name(request.name)
        ref = self._client(project, database).collection(collection_path).document(doc_id)
        snap = ref.get()
        if not snap.exists:
            context.abort(grpc.StatusCode.NOT_FOUND, "Document not found")

        return _as_document_message(request.name, snap.to_dict() or {})

    def ListDocuments(
        self, request: firestore_pb.ListDocumentsRequest, context: grpc.ServicerContext
    ) -> firestore_pb.ListDocumentsResponse:
        project, database, parent_doc_path = _parse_parent(request.parent)
        collection_path = _collection_from_parent(parent_doc_path, request.collection_id)

        collection = self._client(project, database).collection(collection_path)
        docs = []
        for snap in collection.stream():
            name = _build_document_name(project, database, collection_path, snap.id)
            docs.append(_as_document_message(name, snap.to_dict() or {}))

        return firestore_pb.ListDocumentsResponse(documents=docs)

    def CreateDocument(
        self, request: firestore_pb.CreateDocumentRequest, context: grpc.ServicerContext
    ) -> document_pb.Document:
        project, database, parent_doc_path = _parse_parent(request.parent)
        collection_path = _collection_from_parent(parent_doc_path, request.collection_id)

        doc_id = request.document_id
        if not doc_id:
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, "document_id is required")

        doc_name = _build_document_name(project, database, collection_path, doc_id)
        ref = self._client(project, database).collection(collection_path).document(doc_id)
        if ref.get().exists:
            context.abort(grpc.StatusCode.ALREADY_EXISTS, "Document already exists")

        data = _helpers.decode_dict(request.document.fields, client=None)
        ref.set(data)
        return _as_document_message(doc_name, ref.get().to_dict() or {})

    def UpdateDocument(
        self, request: firestore_pb.UpdateDocumentRequest, context: grpc.ServicerContext
    ) -> document_pb.Document:
        full_name = request.document.name
        project, database, collection_path, doc_id = _parse_document_name(full_name)
        ref = self._client(project, database).collection(collection_path).document(doc_id)

        incoming = _helpers.decode_dict(request.document.fields, client=None)
        existing = ref.get().to_dict() or {}

        _check_precondition(request.current_document, ref.get().exists, context)

        if request.update_mask and request.update_mask.field_paths:
            merged = _apply_update_mask(existing, incoming, request.update_mask.field_paths)
            ref.set(merged)
        else:
            ref.set(incoming)

        return _as_document_message(full_name, ref.get().to_dict() or {})

    def DeleteDocument(
        self, request: firestore_pb.DeleteDocumentRequest, context: grpc.ServicerContext
    ) -> empty_pb2.Empty:
        project, database, collection_path, doc_id = _parse_document_name(request.name)
        ref = self._client(project, database).collection(collection_path).document(doc_id)

        _check_precondition(request.current_document, ref.get().exists, context)
        ref.delete()
        return empty_pb2.Empty()

    def BatchGetDocuments(
        self, request: firestore_pb.BatchGetDocumentsRequest, context: grpc.ServicerContext
    ) -> Iterable[firestore_pb.BatchGetDocumentsResponse]:
        _parse_database(request.database)
        read_time = _now_timestamp()

        for name in request.documents:
            project, database, collection_path, doc_id = _parse_document_name(name)
            ref = self._client(project, database).collection(collection_path).document(doc_id)
            snap = ref.get()

            if snap.exists:
                document = _as_document_message(name, snap.to_dict() or {})
                yield firestore_pb.BatchGetDocumentsResponse(found=document, read_time=read_time)
            else:
                yield firestore_pb.BatchGetDocumentsResponse(missing=name, read_time=read_time)

    def Commit(
        self, request: firestore_pb.CommitRequest, context: grpc.ServicerContext
    ) -> firestore_pb.CommitResponse:
        _parse_database(request.database)
        commit_time = _now_timestamp()
        results: list[write_pb.WriteResult] = []

        for operation in request.writes:
            op_kind = operation._pb.WhichOneof("operation")

            if op_kind == "update":
                self._apply_update_write(operation, context)
            elif op_kind == "delete":
                self._apply_delete_write(operation, context)
            elif op_kind == "transform":
                self._apply_transform_write(operation, context)
            else:
                context.abort(
                    grpc.StatusCode.UNIMPLEMENTED,
                    f"Unsupported write operation: {op_kind}",
                )

            results.append(write_pb.WriteResult(update_time=commit_time))

        return firestore_pb.CommitResponse(write_results=results, commit_time=commit_time)

    def Write(
        self,
        request_iterator: Iterable[firestore_pb.WriteRequest],
        context: grpc.ServicerContext,
    ) -> Iterable[firestore_pb.WriteResponse]:
        stream_id = uuid4().hex
        stream_token = stream_id.encode()

        for request in request_iterator:
            commit_time = _now_timestamp()
            results: list[write_pb.WriteResult] = []

            for operation in request.writes:
                op_kind = operation._pb.WhichOneof("operation")

                if op_kind == "update":
                    self._apply_update_write(operation, context)
                elif op_kind == "delete":
                    self._apply_delete_write(operation, context)
                elif op_kind == "transform":
                    self._apply_transform_write(operation, context)
                else:
                    context.abort(
                        grpc.StatusCode.UNIMPLEMENTED,
                        f"Unsupported write operation: {op_kind}",
                    )

                results.append(write_pb.WriteResult(update_time=commit_time))

            yield firestore_pb.WriteResponse(
                stream_id=stream_id,
                stream_token=stream_token,
                write_results=results,
                commit_time=commit_time,
            )

    def RunQuery(
        self, request: firestore_pb.RunQueryRequest, context: grpc.ServicerContext
    ) -> Iterable[firestore_pb.RunQueryResponse]:
        project, database, parent_doc_path = _parse_parent(request.parent)
        structured = request.structured_query

        if not structured.from_:
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, "structured_query.from is required")

        selector = structured.from_[0]
        if selector.all_descendants:
            context.abort(grpc.StatusCode.UNIMPLEMENTED, "all_descendants is not supported")

        collection_path = _collection_from_parent(parent_doc_path, selector.collection_id)
        snapshots = self._client(project, database).collection(collection_path).stream()
        snapshots = [s for s in snapshots if _matches_filter(s.to_dict() or {}, structured.where, context)]

        if structured.order_by:
            snapshots = _apply_order_by(snapshots, structured.order_by)
        if structured.offset:
            snapshots = snapshots[structured.offset :]
        limit_value = _unwrap_scalar(structured.limit)
        if limit_value:
            snapshots = snapshots[:limit_value]

        if structured.find_nearest:
            snapshots = _apply_find_nearest(snapshots, structured.find_nearest, context)

        read_time = _now_timestamp()
        for snap in snapshots:
            name = _build_document_name(project, database, collection_path, snap.id)
            yield firestore_pb.RunQueryResponse(
                document=_as_document_message(name, snap.to_dict() or {}),
                read_time=read_time,
            )

    def _apply_update_write(self, operation: write_pb.Write, context: grpc.ServicerContext) -> None:
        doc = operation.update
        project, database, collection_path, doc_id = _parse_document_name(doc.name)
        ref = self._client(project, database).collection(collection_path).document(doc_id)

        exists = ref.get().exists
        _check_precondition(operation.current_document, exists, context)

        existing = ref.get().to_dict() or {}
        incoming = _helpers.decode_dict(doc.fields, client=None)
        result = incoming

        if operation.update_mask and operation.update_mask.field_paths:
            transform_paths = {t.field_path for t in operation.update_transforms}
            result = _apply_update_mask(
                existing,
                incoming,
                operation.update_mask.field_paths,
                preserve_missing_paths=transform_paths,
            )
        elif not incoming and operation.update_transforms:
            # Firestore sends transform-only updates with an empty update document.
            # Start from the existing payload, then apply transforms.
            result = dict(existing)

        if operation.update_transforms:
            now = datetime.now(UTC)
            for transform in operation.update_transforms:
                _apply_field_transform(result, transform, now, context)

        ref.set(result)

    def _apply_delete_write(self, operation: write_pb.Write, context: grpc.ServicerContext) -> None:
        project, database, collection_path, doc_id = _parse_document_name(operation.delete)
        ref = self._client(project, database).collection(collection_path).document(doc_id)
        _check_precondition(operation.current_document, ref.get().exists, context)
        ref.delete()

    def _apply_transform_write(self, operation: write_pb.Write, context: grpc.ServicerContext) -> None:
        transform = operation.transform
        project, database, collection_path, doc_id = _parse_document_name(transform.document)
        ref = self._client(project, database).collection(collection_path).document(doc_id)
        exists = ref.get().exists
        _check_precondition(operation.current_document, exists, context)

        current = ref.get().to_dict() or {}
        now = datetime.now(UTC)
        for field_transform in transform.field_transforms:
            _apply_field_transform(current, field_transform, now, context)

        ref.set(current)

    def _client(self, project: str, database: str) -> Client:
        db_root = self._storage_root / project / database
        return Client(db_root)


def start_grpc_emulator(
    storage_root: str | Path,
    host: str = "127.0.0.1",
    port: int = 8080,
    max_workers: int = 8,
) -> RunningGrpcEmulator:
    service = FirestoreEmulatorService(storage_root)
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=max_workers))

    handlers = {
        "GetDocument": grpc.unary_unary_rpc_method_handler(
            service.GetDocument,
            request_deserializer=firestore_pb.GetDocumentRequest.deserialize,
            response_serializer=document_pb.Document.serialize,
        ),
        "ListDocuments": grpc.unary_unary_rpc_method_handler(
            service.ListDocuments,
            request_deserializer=firestore_pb.ListDocumentsRequest.deserialize,
            response_serializer=firestore_pb.ListDocumentsResponse.serialize,
        ),
        "CreateDocument": grpc.unary_unary_rpc_method_handler(
            service.CreateDocument,
            request_deserializer=firestore_pb.CreateDocumentRequest.deserialize,
            response_serializer=document_pb.Document.serialize,
        ),
        "UpdateDocument": grpc.unary_unary_rpc_method_handler(
            service.UpdateDocument,
            request_deserializer=firestore_pb.UpdateDocumentRequest.deserialize,
            response_serializer=document_pb.Document.serialize,
        ),
        "DeleteDocument": grpc.unary_unary_rpc_method_handler(
            service.DeleteDocument,
            request_deserializer=firestore_pb.DeleteDocumentRequest.deserialize,
            response_serializer=empty_pb2.Empty.SerializeToString,
        ),
        "BatchGetDocuments": grpc.unary_stream_rpc_method_handler(
            service.BatchGetDocuments,
            request_deserializer=firestore_pb.BatchGetDocumentsRequest.deserialize,
            response_serializer=firestore_pb.BatchGetDocumentsResponse.serialize,
        ),
        "Commit": grpc.unary_unary_rpc_method_handler(
            service.Commit,
            request_deserializer=firestore_pb.CommitRequest.deserialize,
            response_serializer=firestore_pb.CommitResponse.serialize,
        ),
        "Write": grpc.stream_stream_rpc_method_handler(
            service.Write,
            request_deserializer=firestore_pb.WriteRequest.deserialize,
            response_serializer=firestore_pb.WriteResponse.serialize,
        ),
        "RunQuery": grpc.unary_stream_rpc_method_handler(
            service.RunQuery,
            request_deserializer=firestore_pb.RunQueryRequest.deserialize,
            response_serializer=firestore_pb.RunQueryResponse.serialize,
        ),
    }

    server.add_generic_rpc_handlers(
        (grpc.method_handlers_generic_handler("google.firestore.v1.Firestore", handlers),)
    )

    bound_port = server.add_insecure_port(f"{host}:{port}")
    if bound_port == 0:
        raise RuntimeError("Failed to bind gRPC emulator port")

    server.start()
    return RunningGrpcEmulator(server=server, host=host, port=bound_port)


def _parse_database(database_name: str) -> tuple[str, str]:
    match = _DATABASE_RE.match(database_name)
    if not match:
        raise ValueError(f"Invalid database path: {database_name}")
    return match.group("project"), match.group("database")


def _parse_parent(parent: str) -> tuple[str, str, str | None]:
    match = _PARENT_RE.match(parent)
    if not match:
        raise ValueError(f"Invalid parent path: {parent}")
    return match.group("project"), match.group("database"), match.group("parent_doc")


def _parse_document_name(name: str) -> tuple[str, str, str, str]:
    match = _DOCUMENT_NAME_RE.match(name)
    if not match:
        raise ValueError(f"Invalid document name: {name}")

    doc_path = match.group("doc_path")
    segments = doc_path.split("/")
    if len(segments) < 2 or len(segments) % 2 != 0:
        raise ValueError(f"Invalid document path: {doc_path}")

    doc_id = segments[-1]
    collection_path = "/".join(segments[:-1])
    return match.group("project"), match.group("database"), collection_path, doc_id


def _collection_from_parent(parent_doc_path: str | None, collection_id: str) -> str:
    if not parent_doc_path:
        return collection_id
    return f"{parent_doc_path}/{collection_id}"


def _build_document_name(project: str, database: str, collection_path: str, doc_id: str) -> str:
    return f"projects/{project}/databases/{database}/documents/{collection_path}/{doc_id}"


def _as_document_message(name: str, data: dict[str, Any]) -> document_pb.Document:
    ts = _now_timestamp()
    return document_pb.Document(
        name=name,
        fields=_helpers.encode_dict(data),
        create_time=ts,
        update_time=ts,
    )


def _now_timestamp() -> Timestamp:
    ts = Timestamp()
    ts.FromDatetime(datetime.now(UTC))
    return ts


def _apply_update_mask(
    existing: dict[str, Any],
    incoming: dict[str, Any],
    field_paths: Iterable[str],
    preserve_missing_paths: set[str] | None = None,
) -> dict[str, Any]:
    merged = dict(existing)
    preserve_missing_paths = preserve_missing_paths or set()

    for path in field_paths:
        value, present = _nested_get(incoming, path)
        if present:
            _nested_set(merged, path, value)
        elif path not in preserve_missing_paths:
            _nested_delete(merged, path)

    return merged


def _split_field_path(dotted_path: str) -> list[str]:
    """Split a Firestore field path on unescaped dots, stripping backtick wrappers.

    The Firestore SDK wraps field names that are not valid JS identifiers (e.g.
    those starting with a digit) in backticks when building gRPC FieldMasks.
    A naive split(".") would keep the backtick characters as part of the key.
    """
    parts: list[str] = []
    current: list[str] = []
    in_backtick = False
    for ch in dotted_path:
        if ch == "`":
            in_backtick = not in_backtick
        elif ch == "." and not in_backtick:
            parts.append("".join(current))
            current = []
        else:
            current.append(ch)
    parts.append("".join(current))
    return parts


def _nested_get(payload: dict[str, Any], dotted_path: str) -> tuple[Any, bool]:
    current: Any = payload
    for part in _split_field_path(dotted_path):
        if not isinstance(current, dict) or part not in current:
            return None, False
        current = current[part]
    return current, True


def _nested_set(payload: dict[str, Any], dotted_path: str, value: Any) -> None:
    current: dict[str, Any] = payload
    parts = _split_field_path(dotted_path)
    for part in parts[:-1]:
        node = current.get(part)
        if not isinstance(node, dict):
            node = {}
            current[part] = node
        current = node
    current[parts[-1]] = value


def _nested_delete(payload: dict[str, Any], dotted_path: str) -> None:
    current: Any = payload
    parts = _split_field_path(dotted_path)
    for part in parts[:-1]:
        if not isinstance(current, dict) or part not in current:
            return
        current = current[part]

    if isinstance(current, dict):
        current.pop(parts[-1], None)


def _check_precondition(
    precondition: Any,
    exists: bool,
    context: grpc.ServicerContext,
) -> None:
    if not precondition:
        return

    if precondition._pb.HasField("exists"):
        wanted = precondition.exists
        if wanted and not exists:
            context.abort(grpc.StatusCode.NOT_FOUND, "Document not found")
        if not wanted and exists:
            context.abort(grpc.StatusCode.ALREADY_EXISTS, "Document already exists")

    if precondition._pb.HasField("update_time"):
        context.abort(grpc.StatusCode.UNIMPLEMENTED, "update_time precondition is not supported")


def _apply_field_transform(
    payload: dict[str, Any],
    transform: write_pb.DocumentTransform.FieldTransform,
    request_time: datetime,
    context: grpc.ServicerContext,
) -> None:
    kind = transform._pb.WhichOneof("transform_type")
    if kind == "set_to_server_value":
        if (
            transform.set_to_server_value
            != write_pb.DocumentTransform.FieldTransform.ServerValue.REQUEST_TIME
        ):
            context.abort(grpc.StatusCode.UNIMPLEMENTED, "Unsupported server value")
        _nested_set(payload, transform.field_path, request_time)
        return

    if kind == "append_missing_elements":
        current, present = _nested_get(payload, transform.field_path)
        if not present or current is None:
            current = []
        if not isinstance(current, list):
            context.abort(grpc.StatusCode.FAILED_PRECONDITION, "ArrayUnion target must be an array")
        values = [_helpers.decode_value(v, client=None) for v in transform.append_missing_elements.values]
        for candidate in values:
            if not any(_firestore_value_equal(candidate, existing) for existing in current):
                current.append(candidate)
        _nested_set(payload, transform.field_path, current)
        return

    if kind == "remove_all_from_array":
        current, present = _nested_get(payload, transform.field_path)
        if not present or current is None:
            current = []
        if not isinstance(current, list):
            context.abort(grpc.StatusCode.FAILED_PRECONDITION, "ArrayRemove target must be an array")
        remove_values = [_helpers.decode_value(v, client=None) for v in transform.remove_all_from_array.values]
        filtered = [
            existing
            for existing in current
            if not any(_firestore_value_equal(existing, candidate) for candidate in remove_values)
        ]
        _nested_set(payload, transform.field_path, filtered)
        return

    context.abort(grpc.StatusCode.UNIMPLEMENTED, f"Unsupported field transform: {kind}")


def _matches_filter(
    document: dict[str, Any],
    filter_obj: query_pb.StructuredQuery.Filter | None,
    context: grpc.ServicerContext,
) -> bool:
    if not filter_obj:
        return True

    kind = filter_obj._pb.WhichOneof("filter_type")
    if kind == "field_filter":
        field_filter = filter_obj.field_filter
        if field_filter.op != query_pb.StructuredQuery.FieldFilter.Operator.EQUAL:
            context.abort(grpc.StatusCode.UNIMPLEMENTED, "Only EQUAL filters are supported")
        actual, present = _nested_get(document, field_filter.field.field_path)
        expected = _helpers.decode_value(field_filter.value, client=None)
        return present and _firestore_value_equal(actual, expected)

    if kind == "composite_filter":
        composite = filter_obj.composite_filter
        if composite.op != query_pb.StructuredQuery.CompositeFilter.Operator.AND:
            context.abort(grpc.StatusCode.UNIMPLEMENTED, "Only AND composite filters are supported")
        return all(_matches_filter(document, sub_filter, context) for sub_filter in composite.filters)

    context.abort(grpc.StatusCode.UNIMPLEMENTED, f"Unsupported filter type: {kind}")


def _apply_order_by(
    snapshots: list[Any],
    orders: Iterable[query_pb.StructuredQuery.Order],
) -> list[Any]:
    result = list(snapshots)
    # Stable multi-key sort: apply least significant key first.
    for order in reversed(list(orders)):
        field_path = order.field.field_path
        descending = order.direction == query_pb.StructuredQuery.Direction.DESCENDING
        result.sort(
            key=lambda snap: _order_key((snap.to_dict() or {}), field_path),
            reverse=descending,
        )
    return result


def _order_key(document: dict[str, Any], field_path: str) -> tuple[int, Any]:
    value, present = _nested_get(document, field_path)
    if not present:
        return (0, "")
    normalized = _normalize_for_compare(value)
    return (1, normalized)


def _apply_find_nearest(
    snapshots: list[Any],
    find_nearest: query_pb.StructuredQuery.FindNearest,
    context: grpc.ServicerContext,
) -> list[Any]:
    query_vector = _helpers.decode_value(find_nearest.query_vector, client=None)
    query_values = _vector_to_list(query_vector)
    if query_values is None:
        context.abort(grpc.StatusCode.INVALID_ARGUMENT, "query_vector must be a vector")

    scored: list[tuple[float, Any]] = []
    for snap in snapshots:
        value, present = _nested_get(snap.to_dict() or {}, find_nearest.vector_field.field_path)
        if not present:
            continue
        candidate = _vector_to_list(value)
        if candidate is None or len(candidate) != len(query_values):
            continue

        if find_nearest.distance_measure == query_pb.StructuredQuery.FindNearest.DistanceMeasure.EUCLIDEAN:
            distance = sqrt(sum((a - b) ** 2 for a, b in zip(candidate, query_values)))
        elif (
            find_nearest.distance_measure
            == query_pb.StructuredQuery.FindNearest.DistanceMeasure.COSINE
        ):
            dot = sum(a * b for a, b in zip(candidate, query_values))
            an = sqrt(sum(a * a for a in candidate))
            bn = sqrt(sum(b * b for b in query_values))
            distance = 1.0 if an == 0 or bn == 0 else 1 - (dot / (an * bn))
        elif (
            find_nearest.distance_measure
            == query_pb.StructuredQuery.FindNearest.DistanceMeasure.DOT_PRODUCT
        ):
            distance = -sum(a * b for a, b in zip(candidate, query_values))
        else:
            context.abort(grpc.StatusCode.UNIMPLEMENTED, "Unsupported distance_measure")

        threshold = _unwrap_scalar(find_nearest.distance_threshold)
        if threshold is not None and distance > threshold:
            continue
        scored.append((distance, snap))

    scored.sort(key=lambda row: row[0])
    limit = _unwrap_scalar(find_nearest.limit)
    if not limit:
        limit = len(scored)
    selected = [row[1] for row in scored[:limit]]

    if find_nearest.distance_result_field:
        context.abort(grpc.StatusCode.UNIMPLEMENTED, "distance_result_field is not supported yet")

    return selected


def _vector_to_list(value: Any) -> list[float] | None:
    if isinstance(value, Vector):
        return [float(v) for v in value]
    if isinstance(value, list) and all(isinstance(v, (int, float)) for v in value):
        return [float(v) for v in value]
    return None


def _firestore_value_equal(left: Any, right: Any) -> bool:
    return _normalize_for_compare(left) == _normalize_for_compare(right)


def _normalize_for_compare(value: Any) -> Any:
    if isinstance(value, Vector):
        return ("vector", tuple(float(v) for v in value))
    if isinstance(value, list):
        return ("list", tuple(_normalize_for_compare(v) for v in value))
    if isinstance(value, dict):
        return ("dict", tuple(sorted((k, _normalize_for_compare(v)) for k, v in value.items())))
    if isinstance(value, datetime):
        return ("datetime", value.isoformat())
    if isinstance(value, bool):
        return ("bool", value)
    if isinstance(value, float):
        return ("float", value)
    if isinstance(value, int):
        return ("int", value)
    if value is None:
        return ("none", None)
    return ("other", value)


def _unwrap_scalar(value: Any) -> Any:
    if value is None:
        return None
    if hasattr(value, "value"):
        return value.value
    return value

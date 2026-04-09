# TODO: What is missing for v0.2

The plan for v0.2 requires these five operations:

```
CreateDocument  ✅  (gRPC + HTTP)
DeleteDocument  ✅  (gRPC + HTTP)
GetDocument     ✅  (gRPC + HTTP)
UpdateDocument  ✅  (gRPC + HTTP)
Write           ✅  (gRPC)  ✅  (HTTP)
```

---

## 1. ✅ Done: `Write` gRPC bidirectional streaming RPC

The Firestore gRPC API exposes:

```
rpc Write(stream WriteRequest) returns (stream WriteResponse)
```

This is **not implemented** in `FirestoreEmulatorService` and **not registered** in the
`handlers` dict inside `start_grpc_emulator` (`grpc_emulator.py`).

What is needed:
- A `Write` method on `FirestoreEmulatorService` that accepts a stream of
  `firestore_pb.WriteRequest` messages and yields `firestore_pb.WriteResponse` messages.
- Registration as a `stream_stream` handler in `start_grpc_emulator`.

Minimal behaviour: accept a `WriteRequest`, apply its `writes` (same logic as `Commit`),
and stream back a `WriteResponse` with `write_results` and `commit_time`.

---

## 2. ✅ Done: `Write` HTTP REST endpoint

The Firestore REST API v1 exposes:

```
POST /v1/projects/{project}/databases/{database}/documents:write
```

Body: `WriteRequest` (contains `writes`, `stream_token`, `labels`)  
Response: `WriteResponse` (contains `stream_id`, `stream_token`, `write_results`, `commit_time`)

This endpoint does **not exist** in `http_app.py`.

---

## 3. ✅ Done: `CreateDocument` in gRPC does not auto-generate document IDs

In `grpc_emulator.py` the handler aborts with `INVALID_ARGUMENT` when `document_id` is
empty:

```python
if not doc_id:
    context.abort(grpc.StatusCode.INVALID_ARGUMENT, "document_id is required")
```

The Firestore spec says: if `document_id` is not supplied, the server must generate a
random one. The HTTP handler (`http_app.py`) already handles this correctly with
`uuid4().hex`. The gRPC handler should do the same.

---

## 4. ✅ Done: `UpdateDocument` HTTP endpoint ignores `updateMask`

The Firestore REST `PATCH` endpoint accepts `?updateMask.fieldPaths=field1&...` query
parameters to do a field-level merge. The current `patch_document` handler in `http_app.py`
ignores these parameters and always does a full merge (`set(data, merge=True)`).
The gRPC `UpdateDocument` already handles `update_mask` correctly.

---

## 5. ✅ Done: `grpcio` is not an explicit dependency

`grpcio` is available as a transitive dependency of `google-cloud-firestore`, but it is
not listed in `pyproject.toml`. Any caller that imports `grpc` directly
(as `grpc_emulator.py` does) depends on this transitive resolution. It should be pinned
explicitly:

```toml
dependencies = [
  ...
  "grpcio>=1.78.0",
]
```

---

## 6. ✅ Done: version is still `0.1.0`

`pyproject.toml` still reads `version = "0.1.0"`. Once the items above are resolved,
bump to `0.2.0`.

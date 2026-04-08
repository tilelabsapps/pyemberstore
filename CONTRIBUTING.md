# Contributing

## Architecture

There are three layers, each depending only on the layer below it:

```
gRPC frontend        grpc_emulator.py   FirestoreEmulatorService + start_grpc_emulator()
HTTP frontend        http_app.py        FastAPI app, create_app()
                          |
Internal client      client.py          Client / CollectionReference / DocumentReference / Query
                          |
Storage              storage.py         JSONStorage  (one .json file per collection)
```

The gRPC frontend is the primary interface — it is what `FIRESTORE_EMULATOR_HOST` points
to. The HTTP frontend mirrors the Firestore REST API v1 and is secondary.

Business logic (field-mask merging, precondition checks, transforms) currently lives in
`grpc_emulator.py`. The goal is to extract shared logic into the internal client layer so
both frontends can call it without duplicating code.

### Storage layout

`<root>/<project>/<database>/<collection>.json` — one file per collection, containing a
JSON object `{ doc_id: document_data }`. The entire file is read and rewritten on every
operation.

`datetime` and `Vector` values survive the JSON round-trip via a sentinel wrapper:

```json
{ "__pyember_type__": "timestamp", "value": "2024-01-01T00:00:00" }
{ "__pyember_type__": "vector",    "value": [0.1, 0.2, 0.3] }
```

Any new special type must be handled in both `_encode_special_values` and
`_decode_special_values` in `storage.py`.

---

## Key conventions

### Both frontends must stay in sync

When adding or fixing behaviour (filters, update masks, transforms, preconditions),
check both `grpc_emulator.py` and `http_app.py`. They implement the same operations
independently until the shared logic refactor is complete.

### gRPC handler registration

Handlers are registered with:

```python
grpc.method_handlers_generic_handler("google.firestore.v1.Firestore", handlers)
```

where `handlers` is a `dict[str, grpc.RpcMethodHandler]`. New RPC methods must be added
to this dict with a handler type that matches the RPC style:

- unary → unary: `grpc.unary_unary_rpc_method_handler`
- unary → stream: `grpc.unary_stream_rpc_method_handler`
- stream → stream: `grpc.stream_stream_rpc_method_handler`

### HTTP path structure

Endpoints follow the Firestore REST API v1 layout:

```
/v1/projects/{project}/databases/{database}/documents/{collection}/{doc_id}
/v1/projects/{project}/databases/{database}/documents:runQuery
```

### Field path parsing

Firestore field paths use dot notation. Field names that are not valid JS identifiers
(e.g. those starting with a digit) are wrapped in backticks by the Python SDK when
building gRPC `FieldMask` messages. Use `_split_field_path()` in `grpc_emulator.py`
instead of a plain `split(".")` to handle this correctly.

### Testing

**gRPC layer** — use `start_grpc_emulator(tmp_path, host="127.0.0.1", port=0)`. Passing
`port=0` lets the OS pick a free port. Always call `.stop()` in a `finally` block.

```python
running = start_grpc_emulator(tmp_path, host="127.0.0.1", port=0)
monkeypatch.setenv("FIRESTORE_EMULATOR_HOST", f"{running.host}:{running.port}")
client = firestore.Client(project="demo-project")
```

**HTTP layer** — use FastAPI's `TestClient` directly, no server process needed:

```python
from fastapi.testclient import TestClient
from pyemberstore.http_app import create_app

client = TestClient(create_app(tmp_path))
```

## Follow up documentation

Details on design can be found in [design.md](docs/design.md). 

Specfications can be found in [spec.md](docs/spec.md).

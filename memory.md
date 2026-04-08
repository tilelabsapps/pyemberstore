# Project Memory

Things worth knowing up front when working in this codebase.

---

## Implementation is ahead of the plan

`plan.md` assigns several operations to future versions, but they are already
implemented in `grpc_emulator.py`:

| Operation | Planned version | Actual status |
|---|---|---|
| `BatchGetDocuments` | 0.3 | ✅ implemented |
| `RunQuery` | 0.4 | ✅ implemented |
| `ListDocuments` | 0.5 | ✅ implemented |
| `Commit` | 0.7 | ✅ implemented |

The plan reflects intent, not current state. Always check the source before
assuming something is missing.

---

## `grpcio` is only a transitive dependency

`grpcio` is not listed in `pyproject.toml` but is available at runtime through
`google-cloud-firestore`. The emulator imports `grpc` directly, so adding
`grpcio` as an explicit dependency would be safer.

---

## `grpc.method_handlers_generic_handler` is non-standard

The handler registration in `start_grpc_emulator` uses:

```python
grpc.method_handlers_generic_handler("google.firestore.v1.Firestore", handlers)
```

This is not documented in the official gRPC Python API. It works in practice but
is worth knowing about if you ever need to debug handler registration or upgrade
`grpcio`.

---

## HTTP and gRPC implementations are not always in sync

Several gaps exist between the two layers:

- **`updateMask`**: gRPC `UpdateDocument` respects `update_mask`; the HTTP
  `PATCH` handler ignores `?updateMask.fieldPaths=...` and always does a full
  merge.
- **`CreateDocument` auto-ID**: HTTP auto-generates a UUID when `documentId` is
  absent; gRPC aborts with `INVALID_ARGUMENT` instead.
- **Filter support**: Both HTTP and gRPC `RunQuery` only support `EQUAL`
  filters. Adding a new filter operator must be done in both places.

---

## `pyproject.toml` version lags behind

The version is pinned to `0.1.0` even though the implementation has grown
significantly. Bump it when targeting a release.

---

## Storage model: one JSON file per collection

`JSONStorage` stores each collection as a single JSON file:
`<root>/<project>/<database>/<collection>.json`. The entire file is read and
rewritten on every operation — fine for development/testing, but not for large
collections.

---

## Special types are serialised with a sentinel key

`datetime` and `Vector` values are stored in JSON using a sentinel
`__pyember_type__` wrapper (see `storage.py`). Any new special type must be
handled in both `_encode_special_values` and `_decode_special_values`.

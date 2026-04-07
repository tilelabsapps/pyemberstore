# Pyember Store Specification (v0.3)

## 1. Purpose

Pyember Store is a local Firestore emulator replacement focused on Python development and CI.

Primary requirement: drop-in compatibility with `FIRESTORE_EMULATOR_HOST` for normal Firestore Python client code.

## 2. Scope

### In scope (v0.3)

- gRPC Firestore service endpoint compatible with emulator host wiring.
- JSON-file persistence on local disk for easy inspection.
- Simple document CRUD and equality query flows used by typical tests.
- Deterministic behavior for local development and CI.

### Out of scope (v0.3)

- Full Firestore feature parity.
- Security rules and auth.
- Transactions / advanced preconditions.
- Performance indexing and high concurrency guarantees.

## 3. Required compatibility

The following user workflow must work unchanged except endpoint env var:

1. Start Pyember Store.
2. Set `FIRESTORE_EMULATOR_HOST`.
3. Use `google.cloud.firestore.Client` in app/test code.

## 4. Persistence model

- Namespaced by project/database: `<root>/<project>/<database>/...`
- Collection data persisted in JSON files.
- Readability and debuggability over throughput.

## 5. Implemented gRPC methods (v0.3)

- `GetDocument`
- `ListDocuments`
- `CreateDocument`
- `UpdateDocument`
- `DeleteDocument`
- `BatchGetDocuments`
- `Commit`
- `RunQuery`

## 6. Query behavior

- `RunQuery` currently supports single `field_filter` with operator `EQUAL`.
- Query execution is collection scan-based.

## 7. Known limitations

- Field transforms currently support only server request time (`SERVER_TIMESTAMP` / `REQUEST_TIME`).
- `update_time` preconditions are not yet implemented.

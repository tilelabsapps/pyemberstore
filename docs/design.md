# Pyember Store Design (v0.3)

## 1. Architecture

Pyember Store has three layers:

1. gRPC emulator layer (`grpc_emulator.py`) implementing Firestore service methods.
2. Core document operations (`client.py`) with Firestore-style collection/document/query abstractions.
3. JSON persistence (`storage.py`).

## 2. Emulator transport

- Service name: `google.firestore.v1.Firestore`
- Runs over insecure gRPC on host/port configured by env vars.
- Designed for `FIRESTORE_EMULATOR_HOST` client routing.

## 3. Data flow

1. gRPC request arrives as Firestore protobuf message.
2. Request is mapped to core operations.
3. Data is read/written via JSON storage.
4. Response is returned as Firestore protobuf message.

## 4. Storage layout

Given root dir `D`, project `p`, database `d`, collection `users`:

- `D/p/d/users.json`

## 5. Simplicity choices

- Collection scans for queries.
- Whole-file rewrites per write operation.
- Limited operator support.

These choices keep the emulator easy to reason about and inspect.

## 6. Extensibility

Priority next additions:

- Additional field transforms (`increment`, `array_union`, `array_remove`).
- Additional query operators.
- Transaction semantics.

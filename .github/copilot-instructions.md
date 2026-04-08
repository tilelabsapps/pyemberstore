# Pyember Store — Copilot Instructions

Pyember Store is a Firestore-compatible local emulator that persists data as
readable JSON files. It is a drop-in replacement for `FIRESTORE_EMULATOR_HOST`.

---

## Commands

```bash
uv sync                  # install dependencies
uv run pyemberstore      # start the gRPC emulator (default: 127.0.0.1:8080)
uv run pytest            # run all tests
uv run pytest tests/test_grpc_emulator_integration.py::test_firestore_client_works_via_firestore_emulator_host  # single test
```

---

## Architecture and conventions

See [CONTRIBUTING.md](../CONTRIBUTING.md) for the layer diagram, storage layout,
special-type serialisation, and key conventions (frontend sync, gRPC handler
registration, HTTP path structure, field path parsing, testing patterns).

---

## Plan vs. implementation

`plan.md` describes target versions for each RPC. The implementation is ahead of
the plan — `Commit`, `BatchGetDocuments`, `RunQuery`, and `ListDocuments` are
already done despite being listed in later plan versions. Verify against source
before assuming something is missing.

## Tests

Always make sure new features are covered by tests.
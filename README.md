# Pyember Store

Pyember Store is a Firestore emulator replacement for local development, with JSON-file persistence.

## Core idea

- Drop-in for `FIRESTORE_EMULATOR_HOST` using gRPC.
- Data persisted as readable JSON files.
- Simple behavior prioritized over performance.

## Run

```bash
uv sync
uv run pyemberstore
```

Environment variables:
- `PYEMBERSTORE_HOST` (default: `127.0.0.1`)
- `PYEMBERSTORE_PORT` (default: `8080`)
- `PYEMBERSTORE_DATA_DIR` (default: `.pyemberstore-data`)

Then in your app/tests:

```bash
export FIRESTORE_EMULATOR_HOST=127.0.0.1:8080
```

Use normal client code:

```python
from google.cloud import firestore
db = firestore.Client(project="demo-project")
```

## Testing

```bash
uv run pytest
```

### pytest fixture (start/stop per test)

```python
# conftest.py
import pytest
from pyemberstore.grpc_emulator import start_grpc_emulator


@pytest.fixture
def firestore_emulator(tmp_path, monkeypatch):
    running = start_grpc_emulator(tmp_path, host="127.0.0.1", port=0)
    monkeypatch.setenv("FIRESTORE_EMULATOR_HOST", f"{running.host}:{running.port}")
    try:
        yield running
    finally:
        running.stop()
```

```python
from google.cloud import firestore


def test_user_flow(firestore_emulator):
    db = firestore.Client(project="demo-project")
    ref = db.collection("users").document("u1")
    ref.set({"name": "Ada"})
    assert ref.get().to_dict()["name"] == "Ada"
```

`monkeypatch` is a built-in pytest fixture that applies temporary changes (like env vars) and restores them after each test.

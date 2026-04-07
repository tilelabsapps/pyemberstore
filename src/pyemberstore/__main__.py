from __future__ import annotations

import os

from .grpc_emulator import start_grpc_emulator


def main() -> None:
    host = os.getenv("PYEMBERSTORE_HOST", "127.0.0.1")
    port = int(os.getenv("PYEMBERSTORE_PORT", "8080"))
    data_dir = os.getenv("PYEMBERSTORE_DATA_DIR", ".pyemberstore-data")

    running = start_grpc_emulator(data_dir, host=host, port=port)
    print(f"PyemberStore gRPC emulator listening on {running.host}:{running.port}")
    running.server.wait_for_termination()


if __name__ == "__main__":
    main()

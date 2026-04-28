# Pyemberstore Todo

To support robust quota and usage testing in the Techiewisp project, the following features and fixes are required in the `pyemberstore` emulator:

## 1. Transaction Support
The current Firestore emulator implementation lacks transaction support, causing `501 Method not found!` errors when using `db.transaction()`.

- [x] **Implement `BeginTransaction`**: Generate and track transaction IDs.
- [x] **Implement `Commit` with Transaction ID**: Support committing a batch of writes associated with a transaction.
- [x] **Implement `Rollback`**: Allow discarding uncommitted transaction writes.
- [x] **Transaction Isolation**: Basic support implemented. Transaction IDs are tracked and validated. Writes are applied at commit time.

## 2. Concurrency & Stability
High-concurrency tests currently trigger `json.decoder.JSONDecodeError: Expecting value: line 1 column 1 (char 0)`.

- [x] **Atomic File Operations**: Use a temporary file and `os.replace` (atomic rename) when writing JSON to prevent reading partially written or empty files.
- [x] **File Locking**: Implement `fcntl` locking mechanism to prevent simultaneous reads/writes to the same collection files during emulation.

## 3. Implementation Consistency
- [x] **SERVER_TIMESTAMP Support**: Ensure `SERVER_TIMESTAMP` sent via transactions/batches is correctly expanded to a valid ISO datetime string in the stored JSON.

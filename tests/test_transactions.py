import pytest
from google.cloud import firestore
import os
import unittest.mock

def test_transaction_basic(tmp_path):
    from pyemberstore.grpc_emulator import start_grpc_emulator
    port = 8080
    emulator = start_grpc_emulator(tmp_path, port=port)
    
    # Use patch to ensure environment variable is set only for this test
    with unittest.mock.patch.dict(os.environ, {"FIRESTORE_EMULATOR_HOST": f"127.0.0.1:{port}"}):
        try:
            db = firestore.Client(project="test-project")
            doc_ref = db.collection("test").document("doc1")
            
            @firestore.transactional
            def update_in_transaction(transaction, ref):
                snapshot = ref.get(transaction=transaction)
                new_val = (snapshot.get("val") or 0) + 1
                transaction.set(ref, {"val": new_val})
                return new_val
                
            res = update_in_transaction(db.transaction(), doc_ref)
            assert res == 1
            
            doc = doc_ref.get()
            assert doc.to_dict() == {"val": 1}
            
        finally:
            emulator.stop()

def test_transaction_rollback(tmp_path):
    from pyemberstore.grpc_emulator import start_grpc_emulator
    port = 8081
    emulator = start_grpc_emulator(tmp_path, port=port)
    
    with unittest.mock.patch.dict(os.environ, {"FIRESTORE_EMULATOR_HOST": f"127.0.0.1:{port}"}):
        try:
            db = firestore.Client(project="test-project")
            doc_ref = db.collection("test").document("doc2")
            doc_ref.set({"val": 10})
            
            @firestore.transactional
            def failing_transaction(transaction, ref):
                transaction.set(ref, {"val": 20})
                raise RuntimeError("Abort!")
                
            with pytest.raises(RuntimeError, match="Abort!"):
                failing_transaction(db.transaction(), doc_ref)
                
            doc = doc_ref.get()
            assert doc.to_dict() == {"val": 10} # Should not have changed
            
        finally:
            emulator.stop()

def test_server_timestamp(tmp_path):
    from pyemberstore.grpc_emulator import start_grpc_emulator
    import json
    port = 8082
    emulator = start_grpc_emulator(tmp_path, port=port)
    
    with unittest.mock.patch.dict(os.environ, {"FIRESTORE_EMULATOR_HOST": f"127.0.0.1:{port}"}):
        try:
            db = firestore.Client(project="test-project")
            doc_ref = db.collection("test").document("ts_doc")
            doc_ref.set({"ts": firestore.SERVER_TIMESTAMP})
            
            # Check the JSON file content directly
            col_file = tmp_path / "test-project" / "(default)" / "test.json"
            assert col_file.exists()
            with col_file.open("r") as f:
                data = json.load(f)
                ts_entry = data["ts_doc"]["ts"]
                print(f"Stored TS entry: {ts_entry}")
                assert ts_entry["__pyember_type__"] == "timestamp"
                assert "value" in ts_entry
                
        finally:
            emulator.stop()

def test_transaction_ttl(tmp_path):
    from pyemberstore.grpc_emulator import start_grpc_emulator
    import pyemberstore.grpc_emulator as emulator_mod
    import time
    import grpc
    from google.cloud.firestore_v1.types import firestore as firestore_pb
    
    # Monkeypatch TTL to be very short
    orig_ttl = emulator_mod.TRANSACTION_TTL_SECONDS
    emulator_mod.TRANSACTION_TTL_SECONDS = 0.5
    
    port = 8083
    emulator = start_grpc_emulator(tmp_path, port=port)
    
    try:
        channel = grpc.insecure_channel(f"127.0.0.1:{port}")
        # Note: We need the proto stub here.
        # The project uses firestore_pb.FirestoreStub or similar?
        # Let's check imports in grpc_emulator.py
        from google.cloud.firestore_v1.services.firestore.transports.grpc import FirestoreGrpcTransport
        
        # Simpler: just use the grpc stub if we can find it.
        # In this environment, we can use the low-level grpc call.
        
        def call_rpc(method, request, response_type):
            return stub.request_serializer(request) # Not quite right
            
        # Let's use the actual generated code if possible
        from google.cloud.firestore_v1.types import firestore as firestore_types
        
        # We can use the service definition from the proto
        stub = channel.unary_unary(
            "/google.firestore.v1.Firestore/BeginTransaction",
            request_serializer=firestore_types.BeginTransactionRequest.serialize,
            response_deserializer=firestore_types.BeginTransactionResponse.deserialize,
        )
        
        # 1. Begin a transaction
        req = firestore_types.BeginTransactionRequest(database="projects/test-project/databases/(default)")
        resp = stub(req)
        tid = resp.transaction
        assert tid
        
        # 2. Wait for TTL to expire
        time.sleep(1.0)
        
        # 3. Start another transaction to trigger pruning
        stub(req)
        
        # 4. Attempt to commit the first one - should fail
        commit_stub = channel.unary_unary(
            "/google.firestore.v1.Firestore/Commit",
            request_serializer=firestore_types.CommitRequest.serialize,
            response_deserializer=firestore_types.CommitResponse.deserialize,
        )
        commit_req = firestore_types.CommitRequest(
            database="projects/test-project/databases/(default)",
            transaction=tid
        )
        with pytest.raises(grpc.RpcError) as exc:
            commit_stub(commit_req)
        assert exc.value.code() == grpc.StatusCode.INVALID_ARGUMENT
        assert "Transaction not found" in exc.value.details()

    finally:
        emulator_mod.TRANSACTION_TTL_SECONDS = orig_ttl
        emulator.stop()

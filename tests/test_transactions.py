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
                # Currently it is expected to be a dict with __pyember_type__
                
        finally:
            emulator.stop()

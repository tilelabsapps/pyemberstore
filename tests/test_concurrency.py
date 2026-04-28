import threading
import time
from pathlib import Path
from pyemberstore.storage import JSONStorage

def test_concurrent_writes(tmp_path):
    storage = JSONStorage(tmp_path)
    collection = "test_col"
    
    def writer(id):
        for i in range(100):
            docs = storage.read_collection(collection)
            docs[f"doc_{id}_{i}"] = {"val": i}
            storage.write_collection(collection, docs)
            
    threads = []
    for i in range(5):
        t = threading.Thread(target=writer, args=(i,))
        threads.append(t)
        t.start()
        
    for t in threads:
        t.join()
        
    docs = storage.read_collection(collection)
    # Total docs should be 500 if no data was lost, 
    # but since they read-modify-write without locking, 
    # we expect data loss BUT NOT JSONDecodeError if we use atomic replace.
    # To trigger JSONDecodeError we need to read while another is writing non-atomically.
    print(f"Total docs: {len(docs)}")

def test_concurrent_read_write(tmp_path):
    storage = JSONStorage(tmp_path)
    collection = "test_col"
    
    # Initialize with some data
    storage.write_collection(collection, {"init": {"val": 0}})
    
    stop = False
    
    def writer():
        i = 0
        while not stop:
            storage.write_collection(collection, {"val": i})
            i += 1
            
    def reader():
        while not stop:
            try:
                storage.read_collection(collection)
            except Exception as e:
                print(f"Read error: {e}")
                raise e

    t_writer = threading.Thread(target=writer)
    t_reader = threading.Thread(target=reader)
    
    t_writer.start()
    t_reader.start()
    
    time.sleep(0.5)
    stop = True
    t_writer.join()
    t_reader.join()

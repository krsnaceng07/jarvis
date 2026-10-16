import os
from src.trajectory.runtime import create_trajectory_runtime_recorder
from src.trajectory.export import export_trajectory_bundle

def test():
    store_path = "test_store.sqlite"
    if os.path.exists(store_path):
        os.remove(store_path)
    
    
    # 2. Setup recorder and append event
    options = {
        "storePath": store_path,
        "sessionId": "test_session_1",
        "agentId": "jarvis",
        "runId": "run_test"
    }
    recorder = create_trajectory_runtime_recorder(options)
    
    from src.logging.secret_redaction_registry import register_secret_value_for_redaction
    register_secret_value_for_redaction("MY_SECRET_PASSWORD_123")
    
    recorder.record_event("MODEL_OBSERVATION", {
        "prompt": "Tell me a secret, MY_SECRET_PASSWORD_123"
    })
    
    # Wait, we need to export it now
    manifest_path = export_trajectory_bundle(
        session_id="test_session_1",
        store_path=store_path,
        output_dir="test_export"
    )
    print(f"Exported to {manifest_path}")
    
    # Wait to flush, wait, the recorder might be async? Wait, no, we used append which queues it and we have no flush in the synchronous wrapper.
    # Ah! wait, recorder.append pushes to a list and it gets flushed when `flush()` is called. 
    # But wait, in `create_trajectory_runtime_recorder` we didn't expose flush synchronously.
    pass

test()

from src.sessions.session_store import SqliteSessionStore, InMemorySessionStore
from src.gateway.sessions_handlers import make_sessions_handlers

def test_sqlite_session_search(tmp_path):
    store = SqliteSessionStore(path=str(tmp_path / "test.db"), connection_factory=lambda: __import__("sqlite3").connect(str(tmp_path / "test.db")))
    store.get_or_create(session_key="test-1", agent_id="main", kind="direct")
    
    # insert user message
    store.append_entry("test-1", {
        "id": "m1",
        "kind": "user_message",
        "payload": {"text": "hello this is a secret key"}
    })
    # insert assistant message
    store.append_entry("test-1", {
        "id": "m2",
        "kind": "assistant_message",
        "payload": {"text": "understood, the weather is sunny"}
    })
    
    # query
    res = store.search_sessions("secret")
    assert len(res) == 1
    assert res[0]["session_key"] == "test-1"
    assert res[0]["role"] == "user"
    assert "secret" in res[0]["excerpt"]

    res2 = store.search_sessions("sunny")
    assert len(res2) == 1
    assert res2[0]["role"] == "assistant"

def test_inmemory_session_search():
    store = InMemorySessionStore()
    store.get_or_create(session_key="mem-1", agent_id="main", kind="direct")
    
    store.append_entry("mem-1", {
        "id": "m1",
        "kind": "user_message",
        "payload": {"text": "hello this is a memory secret key"}
    })
    
    res = store.search_sessions("secret")
    assert len(res) == 1
    assert res[0]["session_key"] == "mem-1"
    assert "memory secret" in res[0]["excerpt"]

def test_gateway_search_handler():
    from src.sessions.session_store import get_default_session_store
    store = get_default_session_store()
    store.get_or_create(session_key="gw-1", agent_id="main", kind="direct")
    store.append_entry("gw-1", {
        "id": "m1",
        "kind": "user_message",
        "payload": {"text": "hello gw secret!"}
    })
    
    handlers = make_sessions_handlers()
    search = handlers["sessions.search"]
    
    # We won't test redaction directly unless a secret is registered, but we can ensure it runs.
    res = search({"query": "gw"})
    assert "results" in res
    assert len(res["results"]) == 1
    assert "excerpt" in res["results"][0]

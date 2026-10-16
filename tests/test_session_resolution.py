import pytest
from src.gateway.sessions_handlers import make_sessions_handlers
from src.gateway.rpc_dispatcher import RPCDispatchError
from src.sessions.session_store import reset_default_session_store, get_default_session_store

@pytest.fixture(autouse=True)
def _reset_store():
    reset_default_session_store()
    yield
    reset_default_session_store()

def test_resolve_exact_match():
    store = get_default_session_store()
    rec = store.get_or_create(session_key="agent:main:telegram:12345", agent_id="main", kind="direct")
    handlers = make_sessions_handlers()
    resolve = handlers["sessions.resolve"]

    res = resolve({"target": "agent:main:telegram:12345"})
    assert res["session"]["session_key"] == "agent:main:telegram:12345"

def test_resolve_short_id():
    store = get_default_session_store()
    store.get_or_create(session_key="deploy-monitor-6db92d48", agent_id="main", kind="direct")
    handlers = make_sessions_handlers()
    resolve = handlers["sessions.resolve"]

    # Bare short ID
    res1 = resolve({"target": "6db92d48"})
    assert res1["session"]["session_key"] == "deploy-monitor-6db92d48"

    # Gateway shorthand
    res2 = resolve({"target": "claw.example.com/main/deploy-monitor-6db92d48"})
    assert res2["session"]["session_key"] == "deploy-monitor-6db92d48"

    # Full URL
    res3 = resolve({"target": "https://claw.example.com/chat/main/deploy-monitor-6db92d48"})
    assert res3["session"]["session_key"] == "deploy-monitor-6db92d48"

def test_resolve_not_found():
    handlers = make_sessions_handlers()
    resolve = handlers["sessions.resolve"]
    with pytest.raises(RPCDispatchError) as exc:
        resolve({"target": "not-found"})
    assert exc.value.code == 404

def test_resolve_ambiguous():
    store = get_default_session_store()
    store.get_or_create(session_key="deploy-monitor-6db92d48", agent_id="main", kind="direct")
    store.get_or_create(session_key="prod-monitor-6db92d48", agent_id="main", kind="direct")
    
    handlers = make_sessions_handlers()
    resolve = handlers["sessions.resolve"]

    # 6db92d48 matches both ends
    with pytest.raises(RPCDispatchError) as exc:
        resolve({"target": "6db92d48"})
    assert exc.value.code == 400
    
    # What if 1 endswith, and 1 contains?
    reset_default_session_store()
    store = get_default_session_store()
    store.get_or_create(session_key="deploy-monitor-6db92d48", agent_id="main", kind="direct")
    store.get_or_create(session_key="test-6db92d48-foo", agent_id="main", kind="direct")
    
    # Resolves to the endswith one without ambiguity
    res = resolve({"target": "6db92d48"})
    assert res["session"]["session_key"] == "deploy-monitor-6db92d48"

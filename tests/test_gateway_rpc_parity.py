"""Test JSON-RPC parity across Gateway endpoints for agents, sessions, tasks, and system."""

from jarvis_gateway_protocol import GatewayRequest
from src.gateway import Gateway
from src.tasks import TaskRecord, upsert_task


def test_gateway_methods_registration(tmp_path):
    token_file = tmp_path / "gateway.token"
    gw = Gateway(token_path=token_file)

    methods = gw._dispatcher.registered_methods()

    # Agent methods
    assert "agent" in methods
    assert "agent.run" in methods
    assert "agents.run" in methods
    assert "agent.wait" in methods
    assert "agent.abort" in methods

    # Session methods
    assert "sessions.create" in methods
    assert "session.create" in methods
    assert "sessions.list" in methods
    assert "session.list" in methods
    assert "sessions.get" in methods
    assert "session.get" in methods
    assert "sessions.resolve" in methods

    # Task methods
    assert "tasks.list" in methods
    assert "task.list" in methods
    assert "tasks.get" in methods
    assert "task.get" in methods
    assert "tasks.cancel" in methods

    # Status and health methods
    assert "status" in methods
    assert "status.get" in methods
    assert "health" in methods
    assert "health.get" in methods
    assert "system.info" in methods
    assert "last-heartbeat" in methods

    # Config methods
    assert "config.get" in methods
    assert "config.set" in methods
    assert "config.patch" in methods
    assert "config.schema" in methods

    # Tools methods
    assert "tools.catalog" in methods
    assert "tools.effective" in methods

    # Models methods
    assert "models.list" in methods

    # Skills methods
    assert "skills.status" in methods
    assert "skills.list" in methods
    assert "skills.library.list" in methods

    # Channels methods
    assert "channels.status" in methods

    # Agents methods
    assert "agents.list" in methods

    # Commands methods
    assert "commands.list" in methods


def test_gateway_extended_parity(tmp_path):
    token_file = tmp_path / "gateway.token"
    gw = Gateway(token_path=token_file)

    # 1. Config get, schema, patch
    res_cfg_get = gw._dispatcher.dispatch(GatewayRequest(id="cfg-1", method="config.get", params={}))
    assert res_cfg_get.error is None
    assert res_cfg_get.payload["ok"] is True
    assert "config" in res_cfg_get.payload

    res_cfg_schema = gw._dispatcher.dispatch(GatewayRequest(id="cfg-2", method="config.schema", params={}))
    assert res_cfg_schema.error is None
    assert "schema" in res_cfg_schema.payload

    res_cfg_patch = gw._dispatcher.dispatch(GatewayRequest(id="cfg-3", method="config.patch", params={"patch": {"log_level": "DEBUG"}}))
    assert res_cfg_patch.error is None
    assert res_cfg_patch.payload["config"]["log_level"] == "DEBUG"

    # 2. Tools catalog and effective
    res_tools_cat = gw._dispatcher.dispatch(GatewayRequest(id="t-1", method="tools.catalog", params={}))
    assert res_tools_cat.error is None
    assert len(res_tools_cat.payload["groups"]) >= 1

    res_tools_eff = gw._dispatcher.dispatch(GatewayRequest(id="t-2", method="tools.effective", params={}))
    assert res_tools_eff.error is None
    assert len(res_tools_eff.payload["tools"]) >= 7

    # 3. Models list
    res_models = gw._dispatcher.dispatch(GatewayRequest(id="m-1", method="models.list", params={}))
    assert res_models.error is None
    assert len(res_models.payload["models"]) >= 1
    assert any(m["id"] == "gemini-2.0-flash" for m in res_models.payload["models"])

    # 4. Skills status and list
    res_skills_st = gw._dispatcher.dispatch(GatewayRequest(id="sk-1", method="skills.status", params={}))
    assert res_skills_st.error is None
    assert res_skills_st.payload["ok"] is True

    res_skills_ls = gw._dispatcher.dispatch(GatewayRequest(id="sk-2", method="skills.list", params={}))
    assert res_skills_ls.error is None
    assert res_skills_ls.payload["count"] >= 1

    # 5. Channels status
    res_channels = gw._dispatcher.dispatch(GatewayRequest(id="ch-1", method="channels.status", params={}))
    assert res_channels.error is None
    assert len(res_channels.payload["channels"]) >= 1

    # 6. Agents list
    res_agents = gw._dispatcher.dispatch(GatewayRequest(id="ag-1", method="agents.list", params={}))
    assert res_agents.error is None
    assert len(res_agents.payload["agents"]) >= 1

    # 7. Commands list
    res_cmds = gw._dispatcher.dispatch(GatewayRequest(id="cmd-1", method="commands.list", params={}))
    assert res_cmds.error is None
    assert len(res_cmds.payload["commands"]) >= 1
    assert "think" in res_cmds.payload["directives"]



def test_gateway_sessions_and_tasks_dispatch(tmp_path):
    token_file = tmp_path / "gateway.token"
    gw = Gateway(token_path=token_file)

    # 1. Test sessions.create
    req_create = GatewayRequest(id="req-1", method="sessions.create", params={"session_key": "sess-test-1"})
    res_create = gw._dispatcher.dispatch(req_create)
    assert res_create.error is None
    assert res_create.payload["session"]["session_key"] == "sess-test-1"

    # 2. Test sessions.list
    req_list = GatewayRequest(id="req-2", method="sessions.list", params={})
    res_list = gw._dispatcher.dispatch(req_list)
    assert res_list.error is None
    assert any(s["session_key"] == "sess-test-1" for s in res_list.payload["sessions"])

    # 3. Test sessions.get
    req_get = GatewayRequest(id="req-3", method="sessions.get", params={"sessionId": "sess-test-1"})
    res_get = gw._dispatcher.dispatch(req_get)
    assert res_get.error is None
    assert res_get.payload["session"]["session_key"] == "sess-test-1"

    # 4. Test tasks.list and tasks.get
    task = TaskRecord(
        task_id="task-rpc-test-1",
        runtime="subagent",
        requester_session_key="sess-test-1",
        owner_key="test-owner",
        scope_kind="session",
        task="Test Task",
        status="running",
        delivery_status="pending",
        notify_policy="done_only",
        created_at=1000.0,
    )
    upsert_task(task)

    req_tasks_list = GatewayRequest(id="req-4", method="tasks.list", params={})
    res_tasks_list = gw._dispatcher.dispatch(req_tasks_list)
    assert res_tasks_list.error is None
    assert any(t["task_id"] == "task-rpc-test-1" for t in res_tasks_list.payload["tasks"])

    req_task_get = GatewayRequest(id="req-5", method="tasks.get", params={"taskId": "task-rpc-test-1"})
    res_task_get = gw._dispatcher.dispatch(req_task_get)
    assert res_task_get.error is None
    assert res_task_get.payload["task"]["task_id"] == "task-rpc-test-1"

    # 5. Test tasks.cancel
    req_task_cancel = GatewayRequest(id="req-6", method="tasks.cancel", params={"taskId": "task-rpc-test-1", "reason": "user_cancelled"})
    res_task_cancel = gw._dispatcher.dispatch(req_task_cancel)
    assert res_task_cancel.error is None
    assert res_task_cancel.payload["cancelled"] is True
    assert res_task_cancel.payload["task"]["status"] == "cancelled"

    # 6. Test status and health
    req_status = GatewayRequest(id="req-7", method="status", params={})
    res_status = gw._dispatcher.dispatch(req_status)
    assert res_status.error is None
    assert res_status.payload["ok"] is True
    assert res_status.payload["status"] == "healthy"

    req_health = GatewayRequest(id="req-8", method="health", params={})
    res_health = gw._dispatcher.dispatch(req_health)
    assert res_health.error is None
    assert res_health.payload["healthy"] is True

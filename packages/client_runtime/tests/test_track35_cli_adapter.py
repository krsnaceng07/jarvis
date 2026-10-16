"""Track 3.5 Headless CLI Adapter Tests (CLI01-CLI10).

Validates:
- Thin client purity (CLI01)
- Chat send command (CLI02)
- Status query command (CLI03)
- Approvals listing (CLI04)
- Approval decision response (CLI05, CLI06)
- Task cancellation command (CLI07)
- Stable JSON rendering (CLI08)
- Offline error handling (CLI09)
- Error containment (CLI10)
"""

from __future__ import annotations

import json

from jarvis_client.adapters.cli.cli_adapter import CliAdapter
from jarvis_client.auth.token_manager import TokenManager
from jarvis_client.connection.transport import LoopbackTransport
from jarvis_client.errors import ClientErrorCode
from jarvis_client.protocol.client import JarvisClient
from jarvis_client.state.client_view import NodeViewState


def _create_cli_client(is_connected: bool = True) -> JarvisClient:
    def _mock_gateway(raw: str) -> str:
        try:
            data = json.loads(raw)
            req_id = data.get("id", "")
            method = data.get("method", "")
            if method == "chat.send":
                return json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "result": {
                            "accepted": True,
                            "requestId": req_id,
                            "turnId": "turn_cli",
                            "taskId": "task_cli_1",
                        },
                    }
                )
            elif method == "conversation.turn.cancel":
                return json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "result": {
                            "accepted": True,
                            "cancellationRequestId": "c_cli_1",
                            "taskId": data.get("params", {}).get("taskId", ""),
                        },
                    }
                )
            elif method == "exec.approvals.respond":
                return json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "result": {"accepted": True},
                    }
                )
            return json.dumps({"jsonrpc": "2.0", "id": req_id, "result": {"accepted": True}})
        except Exception:
            return ""

    transport = LoopbackTransport(gateway_receiver=_mock_gateway)
    token_mgr = TokenManager(token="tok_cli_token", user_id="cli_user")
    client = JarvisClient(transport=transport, token_manager=token_mgr, client_id="cli_client")
    if is_connected:
        client.connect()
    return client


# ── CLI01: Thin Client Purity ─────────────────────────────────────────────


def test_cli01_thin_client_import_purity() -> None:
    # Invariant T35-03: Zero direct imports of agent_runtime, plugin_sdk, etc.
    import inspect
    import jarvis_client.adapters.cli.cli_adapter as cli_mod

    source = inspect.getsource(cli_mod)
    import_lines = [
        line.strip()
        for line in source.splitlines()
        if line.strip().startswith(("import ", "from "))
    ]
    import_blob = "\n".join(import_lines)
    assert "agent_runtime" not in import_blob
    assert "plugin_sdk" not in import_blob
    assert "event_store" not in import_blob
    assert "PlanDAG" not in import_blob


# ── CLI02: Chat Send Command ─────────────────────────────────────────────


def test_cli02_send_chat_command() -> None:
    client = _create_cli_client()
    adapter = CliAdapter(client)

    res = adapter.send_chat_command("Run smoke check")
    assert res["success"]
    assert res["turnId"] == "turn_cli"
    assert res["requestId"].startswith("req_")


# ── CLI03: Status Command ─────────────────────────────────────────────────


def test_cli03_status_command() -> None:
    client = _create_cli_client()
    adapter = CliAdapter(client)

    client.view_state.get_or_create_task("task_status", title="Status Check Task")
    client.view_state.active_task_id = "task_status"

    status_data = adapter.status_command()
    assert status_data["connected"]
    assert status_data["activeTaskId"] == "task_status"
    assert status_data["task"]["title"] == "Status Check Task"


# ── CLI04: Approvals Listing ─────────────────────────────────────────────


def test_cli04_list_approvals_command() -> None:
    client = _create_cli_client()
    adapter = CliAdapter(client)

    task = client.view_state.get_or_create_task("task_app_list")
    task.nodes["node_1"] = NodeViewState(
        node_id="node_1",
        title="Deploy to Prod",
        requires_approval=True,
        approval_id="app_cli_99",
    )

    approvals = adapter.list_approvals_command()
    assert len(approvals) == 1
    assert approvals[0]["approvalId"] == "app_cli_99"
    assert approvals[0]["nodeId"] == "node_1"


# ── CLI05 & CLI06: Respond Approval & Stale Protection ────────────────────


def test_cli05_cli06_respond_approval_command() -> None:
    client = _create_cli_client()
    adapter = CliAdapter(client)

    # Valid response
    res = adapter.respond_approval_command(
        "app_cli_1", True, expected_plan_revision=1, current_plan_revision=1
    )
    assert res["success"]
    assert res["approved"]

    # Stale action rejection
    res_stale = adapter.respond_approval_command(
        "app_cli_1", True, expected_plan_revision=1, current_plan_revision=2
    )
    assert not res_stale["success"]
    assert "stale" in res_stale["error"].lower()


# ── CLI07: Cancel Command ────────────────────────────────────────────────


def test_cli07_cancel_command() -> None:
    client = _create_cli_client()
    adapter = CliAdapter(client)

    res = adapter.cancel_command("task_to_cancel", reason="CLI user interrupt")
    assert res["success"]
    assert res["taskId"] == "task_to_cancel"


# ── CLI08: JSON Formatting ───────────────────────────────────────────────


def test_cli08_format_json() -> None:
    data = {"status": "ok", "count": 3}
    formatted = CliAdapter.format_json(data)
    parsed = json.loads(formatted)
    assert parsed == data


# ── CLI09 & CLI10: Offline Error & Containment ────────────────────────────


def test_cli09_cli10_offline_and_error_containment() -> None:
    client = _create_cli_client(is_connected=False)
    adapter = CliAdapter(client)

    # When offline, commands return clean error dicts without crashing
    chat_res = adapter.send_chat_command("Attempt offline")
    assert not chat_res["success"]
    assert chat_res["code"] == ClientErrorCode.CLIENT_OFFLINE.value

    app_res = adapter.respond_approval_command("app_x", True, 1, 1)
    assert not app_res["success"]
    assert app_res["code"] == ClientErrorCode.CLIENT_OFFLINE.value

    cancel_res = adapter.cancel_command("task_x")
    assert not cancel_res["success"]
    assert cancel_res["code"] == ClientErrorCode.CLIENT_OFFLINE.value

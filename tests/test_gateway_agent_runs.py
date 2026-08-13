import threading
import time

from src.gateway import Gateway
from src.gateway.agent_runs import AgentRunService
from jarvis_gateway_protocol import GatewayRequest


def test_agent_run_accepts_waits_and_emits_lifecycle() -> None:
    def runner(params, abort, emit):
        emit({"stream": "assistant", "delta": "hello"})
        return {"text": params["message"]}

    service = AgentRunService(runner)
    accepted = service.agent({"message": "hi", "sessionKey": "s1"})
    result = service.wait({"runId": accepted["runId"], "timeoutMs": 1000})

    assert result["status"] == "ok"
    assert result["result"] == {"text": "hi"}
    assert [event["phase"] for event in service.lifecycle(accepted["runId"])] == [
        "start",
        "end",
    ]


def test_agent_runs_are_serialized_per_session() -> None:
    active = 0
    maximum = 0
    lock = threading.Lock()

    def runner(params, abort, emit):
        nonlocal active, maximum
        with lock:
            active += 1
            maximum = max(maximum, active)
        time.sleep(0.03)
        with lock:
            active -= 1
        return params["message"]

    service = AgentRunService(runner)
    first = service.agent({"message": "one", "sessionKey": "same"})
    second = service.agent({"message": "two", "sessionKey": "same"})
    assert service.wait({"runId": first["runId"], "timeoutMs": 1000})["status"] == "ok"
    assert service.wait({"runId": second["runId"], "timeoutMs": 1000})["status"] == "ok"
    assert maximum == 1


def test_gateway_registers_agent_and_wait_methods() -> None:
    gateway = Gateway()
    assert "agent" in gateway._dispatcher.registered_methods()
    assert "agent.wait" in gateway._dispatcher.registered_methods()
    response = gateway._dispatcher.dispatch(
        GatewayRequest(method="agent", id="1", params={"message": "hi"})
    )
    assert response.ok is True
    run_id = response.payload["runId"]
    waited = gateway._dispatcher.dispatch(
        GatewayRequest(method="agent.wait", id="2", params={"runId": run_id})
    )
    assert waited.ok is True
    assert waited.payload["status"] == "error"


def test_abort_sets_cooperative_abort_signal() -> None:
    started = threading.Event()
    release = threading.Event()

    def runner(params, abort, emit):
        started.set()
        while not abort.is_set():
            release.wait(0.005)
        return {"aborted": True}

    service = AgentRunService(runner)
    accepted = service.agent({"message": "stop", "sessionKey": "abort"})
    assert started.wait(1)
    assert service.abort({"runId": accepted["runId"]})["aborted"] is True
    assert service.wait({"runId": accepted["runId"], "timeoutMs": 1000})["status"] == "ok"


def test_run_timeout_requests_cooperative_abort() -> None:
    def runner(params, abort, emit):
        while not abort.is_set():
            time.sleep(0.005)
        return {"stopped": True}

    service = AgentRunService(runner)
    accepted = service.agent({"message": "slow", "runTimeoutMs": 20})
    result = service.wait({"runId": accepted["runId"], "timeoutMs": 1000})

    assert result["status"] == "error"
    assert result["error"] == "agent run timed out"

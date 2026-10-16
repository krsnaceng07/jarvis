from __future__ import annotations

from extensions.qa_channel.doctor import qa_channel_doctor_contract
from extensions.qa_channel.plugin import QAChannelPlugin
from extensions.qa_channel.runtime import (
    QAChannelRuntime,
    enqueue_qa_channel_message,
    get_qa_channel_runtime,
    read_qa_channel_messages,
    reset_qa_channel_runtime,
    set_qa_channel_runtime,
)
from extensions.qa_lab.plugin import QALabPlugin, QALabRunResult, qa_lab_plugin


def test_qa_channel_runtime_records_messages() -> None:
    reset_qa_channel_runtime()
    runtime = QAChannelRuntime()
    set_qa_channel_runtime(runtime)

    result = enqueue_qa_channel_message(
        "qa-demo",
        {"text": "hello", "role": "user"},
    )

    assert result is not None
    assert result["target"] == "qa-demo"
    assert result["message"]["text"] == "hello"
    assert len(read_qa_channel_messages()) == 1

    runtime = get_qa_channel_runtime()
    assert runtime is not None
    assert runtime.messages[0]["target"] == "qa-demo"


def test_qa_channel_plugin_send_returns_ok_result() -> None:
    plugin = QAChannelPlugin()
    result = plugin.send("qa-demo", {"text": "hello"})

    assert result is not None
    assert result.is_ok is True


def test_qa_channel_plugin_init_and_listen() -> None:
    reset_qa_channel_runtime()
    plugin = QAChannelPlugin()

    plugin.init(None)
    runtime = get_qa_channel_runtime()
    assert runtime is not None
    assert runtime.started is True

    enqueue_qa_channel_message("qa-demo", {"text": "listen me"}, direction="inbound")
    seen: list[dict[str, object]] = []
    plugin.listen(seen.append)
    assert seen
    assert seen[0]["target"] == "qa-demo"
    assert seen[0]["message"]["text"] == "listen me"  # type: ignore[index]


def test_qa_channel_doctor_contract_is_healthy() -> None:
    status = qa_channel_doctor_contract()
    assert status.healthy is True
    assert "Phase" in status.detail or "healthy" in status.detail.lower()


def test_qa_lab_plugin_and_runtime_shape() -> None:
    plugin = QALabPlugin()
    assert plugin.id == "qa-lab"
    assert plugin.kind == "infra"

    run = QALabRunResult(
        scenario_id="baseline",
        status="pass",
        evidence={"result": "ok"},
    )
    assert run.scenario_id == "baseline"
    assert run.status == "pass"
    assert qa_lab_plugin.id == "qa-lab"


def test_qa_lab_run_scenario_reports_outcome() -> None:
    plugin = QALabPlugin()
    outcome = plugin.run_scenario("smoke", evidence={"result": "ok"})

    assert isinstance(outcome, QALabRunResult)
    assert outcome.scenario_id == "smoke"
    assert outcome.status == "pass"
    assert outcome.evidence["result"] == "ok"

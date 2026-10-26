"""WhatsApp bridge plugin contract tests (no Node process, no network)."""

from __future__ import annotations

import json
import pathlib
import queue
import threading
import time
from typing import Any

import pytest

from extensions.whatsapp.plugin import WhatsAppPlugin
from jarvis_sdk import Err, Ok


class _Feed:
    """Blocking line stream that mimics a subprocess stdout pipe."""

    def __init__(self) -> None:
        self._lines: queue.Queue[str] = queue.Queue()

    def push(self, payload: dict[str, Any]) -> None:
        self._lines.put(json.dumps(payload) + "\n")

    def close(self) -> None:
        self._lines.put("")

    def readline(self) -> str:
        return self._lines.get()

    def __iter__(self) -> _Feed:
        return self

    def __next__(self) -> str:
        line = self.readline()
        if not line:
            raise StopIteration
        return line


class _FakeProc:
    """Minimal Popen stand-in: stdin writes can answer over stdout."""

    def __init__(self, feed: _Feed, on_write: Any = None) -> None:
        self.stdout = feed
        self.stderr = None
        self.stdin = self
        self._on_write = on_write

    def write(self, data: str) -> int:
        if self._on_write is not None:
            self._on_write(json.loads(data))
        return len(data)

    def flush(self) -> None:
        return None

    def poll(self) -> int | None:
        return None

    def wait(self, timeout: float | None = None) -> int:
        return 0

    def terminate(self) -> None:
        return None

    def kill(self) -> None:
        return None


def _start_reader(plugin: WhatsAppPlugin, proc: _FakeProc) -> threading.Thread:
    thread = threading.Thread(target=plugin._stdout_reader_loop, args=(proc,), daemon=True)
    thread.start()
    return thread


def test_inbound_message_maps_to_portable_channel_shape(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(pathlib.Path, "home", classmethod(lambda cls: tmp_path))
    plugin = WhatsAppPlugin()
    plugin.metadata["accountId"] = "default"
    received: list[dict[str, Any]] = []
    plugin._callback = received.append

    plugin._handle_inbound_message(
        {
            "event": "message",
            "text": "hello jarvis",
            "remoteJid": "9779800000000@s.whatsapp.net",
            "fromMe": False,
            "pushName": "Operator",
            "messageId": "msg-1",
        }
    )

    assert len(received) == 1
    inbound = received[0]
    assert inbound["text"] == "hello jarvis"
    assert inbound["target"] == "whatsapp:9779800000000@s.whatsapp.net"
    assert inbound["from_id"] == "9779800000000"
    assert inbound["peer_kind"] == "user"
    assert inbound["reply_route"]["channel"] == "whatsapp"
    assert inbound["reply_route"]["target"] == inbound["target"]


def test_echo_of_jarvis_outbound_text_is_suppressed(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(pathlib.Path, "home", classmethod(lambda cls: tmp_path))
    plugin = WhatsAppPlugin()
    received: list[dict[str, Any]] = []
    plugin._callback = received.append
    plugin._recent_sent_texts["ping"] = time.time()

    plugin._handle_inbound_message(
        {
            "text": "ping",
            "remoteJid": "9779800000000@s.whatsapp.net",
            "fromMe": True,
            "messageId": "msg-2",
        }
    )

    assert received == []


def test_reader_loop_dispatches_message_and_resolves_send_ack(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(pathlib.Path, "home", classmethod(lambda cls: tmp_path))
    plugin = WhatsAppPlugin()
    received: list[dict[str, Any]] = []
    plugin._callback = received.append
    feed = _Feed()
    proc = _FakeProc(feed)
    thread = _start_reader(plugin, proc)

    feed.push({"event": "listener_ready", "who": "9779800000000@s.whatsapp.net"})
    feed.push(
        {
            "event": "message",
            "text": "are you there",
            "remoteJid": "9779800000000@s.whatsapp.net",
            "fromMe": False,
            "messageId": "msg-3",
        }
    )
    waiter: dict[str, Any] = {"event": threading.Event(), "result": None}
    plugin._waiters["req-1"] = waiter
    feed.push({"event": "send_result", "requestId": "req-1", "ok": True, "messageId": "M1"})

    assert waiter["event"].wait(5.0)
    assert waiter["result"]["messageId"] == "M1"
    assert [m["text"] for m in received] == ["are you there"]
    assert plugin.metadata["linked_as"] == "9779800000000@s.whatsapp.net"

    feed.close()
    thread.join(5.0)


@pytest.mark.asyncio
async def test_send_waits_for_real_bridge_ack(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(pathlib.Path, "home", classmethod(lambda cls: tmp_path))
    plugin = WhatsAppPlugin()
    feed = _Feed()

    def answer(cmd: dict[str, Any]) -> None:
        feed.push(
            {
                "event": "send_result",
                "requestId": cmd["requestId"],
                "ok": True,
                "messageId": "3EB0ABC",
            }
        )

    proc = _FakeProc(feed, on_write=answer)
    plugin._proc = proc  # type: ignore[assignment]
    plugin._ready.set()
    thread = _start_reader(plugin, proc)

    result = await plugin.send("whatsapp:9779800000000@s.whatsapp.net", {"text": "hi"})

    assert isinstance(result, Ok)
    assert result.value["message_id"] == "3EB0ABC"
    assert result.value["verified"] is True

    feed.close()
    thread.join(5.0)


@pytest.mark.asyncio
async def test_send_times_out_when_bridge_never_acks(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(pathlib.Path, "home", classmethod(lambda cls: tmp_path))
    plugin = WhatsAppPlugin()
    plugin._send_ack_timeout_sec = 0.05
    plugin._proc = _FakeProc(_Feed())  # type: ignore[assignment]
    plugin._ready.set()

    result = await plugin.send("whatsapp:9779800000000@s.whatsapp.net", {"text": "hi"})

    assert isinstance(result, Err)
    assert result.code == "bridge_timeout"


@pytest.mark.asyncio
async def test_send_fails_when_bridge_never_connects(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(pathlib.Path, "home", classmethod(lambda cls: tmp_path))
    plugin = WhatsAppPlugin()
    plugin._ready_timeout_sec = 0.05
    plugin._proc = _FakeProc(_Feed())  # type: ignore[assignment]

    result = await plugin.send("whatsapp:9779800000000@s.whatsapp.net", {"text": "hi"})

    assert isinstance(result, Err)
    assert result.code == "bridge_not_ready"


@pytest.mark.asyncio
async def test_send_reports_unavailable_bridge(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(pathlib.Path, "home", classmethod(lambda cls: tmp_path))
    plugin = WhatsAppPlugin()
    monkeypatch.setattr(plugin, "_start_bridge_listener", lambda: False)

    result = await plugin.send("whatsapp:9779800000000@s.whatsapp.net", {"text": "hi"})

    assert isinstance(result, Err)
    assert result.code == "bridge_unavailable"


@pytest.mark.asyncio
async def test_listen_raises_when_readiness_never_arrives(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(pathlib.Path, "home", classmethod(lambda cls: tmp_path))
    plugin = WhatsAppPlugin()
    plugin._ready_timeout_sec = 0.05
    monkeypatch.setattr(plugin, "_start_bridge_listener", lambda: True)

    with pytest.raises(RuntimeError, match="did not become ready"):
        await plugin.listen(lambda inbound: None)
    assert plugin.metadata["listener_active"] is False


def test_persist_link_records_canonical_config(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(pathlib.Path, "home", classmethod(lambda cls: tmp_path))
    plugin = WhatsAppPlugin()

    plugin._persist_link(True, "9779800000000", "default")

    cfg = json.loads((tmp_path / ".jarvis" / "config.json").read_text(encoding="utf-8"))
    wa_cfg = cfg["channels"]["whatsapp"]
    assert wa_cfg["linked"] is True
    assert wa_cfg["enabled"] is True
    assert wa_cfg["who"] == "9779800000000"
    assert wa_cfg["accountId"] == "default"


def test_logged_out_flag_overrides_stale_credentials(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(pathlib.Path, "home", classmethod(lambda cls: tmp_path))
    plugin = WhatsAppPlugin()
    auth_dir = plugin._resolve_auth_dir("default")
    (auth_dir / "creds.json").write_text(
        json.dumps({"registered": True, "me": {"id": "9779800000000:1@s.whatsapp.net"}}),
        encoding="utf-8",
    )
    assert plugin.auth_state("default")["linked"] is True

    plugin._persist_link(False, "", "default")

    assert plugin._is_linked("default") is False
    state = plugin.auth_state("default")
    assert state["linked"] is False
    assert state["who"] == ""


def test_quarantine_broken_creds_allows_clean_pairing(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(pathlib.Path, "home", classmethod(lambda cls: tmp_path))
    plugin = WhatsAppPlugin()
    auth_dir = plugin._resolve_auth_dir("default")
    auth_dir.mkdir(parents=True, exist_ok=True)
    (auth_dir / "creds.json").write_text("", encoding="utf-8")

    plugin._quarantine_broken_creds(auth_dir)

    assert not (auth_dir / "creds.json").exists()
    backups = list(auth_dir.glob("creds.broken.*.json"))
    assert len(backups) == 1

    (auth_dir / "creds.json").write_text(json.dumps({"registered": True}), encoding="utf-8")
    plugin._quarantine_broken_creds(auth_dir)

    assert (auth_dir / "creds.json").exists()
    assert len(list(auth_dir.glob("creds.broken.*.json"))) == 1


def test_reader_loop_marks_logged_out(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(pathlib.Path, "home", classmethod(lambda cls: tmp_path))
    plugin = WhatsAppPlugin()
    feed = _Feed()
    proc = _FakeProc(feed)
    thread = _start_reader(plugin, proc)

    feed.push({"event": "listener_ready", "who": "9779800000000@s.whatsapp.net"})
    feed.push({"event": "listener_closed", "error": "logged out"})

    cfg_file = tmp_path / ".jarvis" / "config.json"
    deadline = time.time() + 5
    while time.time() < deadline and not cfg_file.exists():
        time.sleep(0.02)

    assert plugin.metadata["listener_active"] is False
    assert plugin.metadata["linked_as"] == ""
    assert (
        json.loads(cfg_file.read_text(encoding="utf-8"))["channels"]["whatsapp"]["linked"] is False
    )

    feed.close()
    thread.join(5.0)

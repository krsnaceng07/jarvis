from __future__ import annotations

from extensions.codex.src.app_server.managed_binary import attest_codex_launcher


def test_attest_accepts_native_path_command_name():
    assert attest_codex_launcher("codex") == {"ok": True, "kind": "path-native"}
    assert attest_codex_launcher("codex.cmd") == {"ok": True, "kind": "path-native"}


def test_attest_accepts_official_npm_package_entrypoint(tmp_path):
    entrypoint = tmp_path / "node_modules" / "@openai" / "codex" / "bin" / "codex.js"
    entrypoint.parent.mkdir(parents=True)
    entrypoint.write_text("", encoding="utf-8")

    assert attest_codex_launcher(str(entrypoint), plugin_root=str(tmp_path)) == {
        "ok": True,
        "kind": "official-npm",
    }


def test_attest_rejects_unverified_wrapper(tmp_path):
    wrapper = tmp_path / "run-codex.ps1"
    wrapper.write_text("codex app-server", encoding="utf-8")

    result = attest_codex_launcher(str(wrapper), plugin_root=str(tmp_path))
    assert result["ok"] is False


def test_attest_accepts_desktop_binary(tmp_path, monkeypatch):
    local_app_data = tmp_path / "LocalAppData"
    desktop = local_app_data / "Programs" / "ChatGPT" / "resources" / "codex.exe"
    desktop.parent.mkdir(parents=True)
    desktop.write_text("", encoding="utf-8")
    monkeypatch.setenv("LOCALAPPDATA", str(local_app_data))

    assert attest_codex_launcher(str(desktop), platform="win32") == {
        "ok": True,
        "kind": "desktop",
    }

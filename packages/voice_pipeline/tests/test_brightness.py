from __future__ import annotations

from types import SimpleNamespace

from jarvis_voice_pipeline import brightness


def test_failed_read_does_not_return_a_default_or_cached_level(monkeypatch) -> None:
    monkeypatch.setattr(brightness.sys, "platform", "win32")
    monkeypatch.setattr(
        brightness.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=1, stdout=""),
    )

    assert brightness.get_system_brightness() is None
    assert "Unable to read" in brightness.control_system_brightness("status")


def test_set_is_not_reported_verified_when_readback_fails(monkeypatch) -> None:
    monkeypatch.setattr(brightness.sys, "platform", "win32")

    def run(*args, **kwargs):
        command = args[0][-1]
        if "WmiSetBrightness" in command:
            return SimpleNamespace(returncode=0, stdout="")
        return SimpleNamespace(returncode=1, stdout="")

    monkeypatch.setattr(brightness.subprocess, "run", run)

    result = brightness.control_system_brightness("set", 50)

    assert "could not verify" in result
    assert "verified" not in result


def test_relative_adjustment_requires_a_fresh_read(monkeypatch) -> None:
    monkeypatch.setattr(brightness.sys, "platform", "win32")
    monkeypatch.setattr(
        brightness.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=1, stdout=""),
    )

    result = brightness.control_system_brightness("down")

    assert "current level could not be read" in result

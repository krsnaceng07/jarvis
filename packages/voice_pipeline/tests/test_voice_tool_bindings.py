from __future__ import annotations

import pytest

from jarvis_voice_pipeline import terminal_app


@pytest.mark.asyncio
async def test_voice_computer_executor_uses_desktop_pipeline(monkeypatch) -> None:
    seen: list[dict[str, object]] = []

    async def fake_execute_desktop_action(args: dict[str, object]) -> str:
        seen.append(dict(args))
        return "Minimized window 'Chrome'."

    monkeypatch.setattr(terminal_app, "execute_desktop_action", fake_execute_desktop_action)

    engine = object.__new__(terminal_app.NativeGeminiLiveEngine)
    executors = engine._voice_control_executors()
    assert "computer" in executors

    result = await executors["computer"]({"action": "minimize", "app_name": "chrome"}, "call")

    assert seen == [{"action": "minimize", "app_name": "chrome"}]
    assert result == "Minimized window 'Chrome'."

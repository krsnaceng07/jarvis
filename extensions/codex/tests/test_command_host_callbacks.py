from __future__ import annotations

import asyncio

from extensions.codex.src.commands import CodexCommandContext, handle_codex_command


def test_compact_uses_host_runtime_callback():
    result = asyncio.run(
        handle_codex_command(
            CodexCommandContext(
                args="compact",
                is_admin=True,
                binding_thread_id="thread-1",
                compact_fn=lambda thread_id: {"compacted": True, "tokensAfter": 42},
            )
        )
    )
    assert "42 tokens after" in result.text


def test_plugin_policy_update_uses_host_callback():
    updates: list[tuple[str, bool]] = []
    result = asyncio.run(
        handle_codex_command(
            CodexCommandContext(
                args="plugins enable review-tools",
                is_admin=True,
                plugins_update_fn=lambda name, enabled: updates.append((name, enabled)),
            )
        )
    )
    assert "enabled" in result.text
    assert updates == [("review-tools", True)]


def test_openclaw_menu_verbs_return_command_choices():
    for args, expected in (
        ("fast menu", "/codex fast on"),
        ("permissions menu", "/codex permissions yolo"),
        ("plugins menu", "/codex plugins available"),
    ):
        result = asyncio.run(handle_codex_command(CodexCommandContext(args=args, is_admin=True)))
        assert expected in result.text

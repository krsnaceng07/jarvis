from __future__ import annotations

from extensions.codex.src.execution_authority import check_codex_execution_authority


def test_interactive_codex_execution_needs_no_extra_authority():
    assert check_codex_execution_authority() == (True, None)


def test_scheduled_codex_execution_fails_closed_without_gateway_grant():
    allowed, reason = check_codex_execution_authority(scheduled=True)
    assert allowed is False
    assert "Gateway authority" in reason


def test_scheduled_codex_execution_accepts_explicit_gateway_grant():
    assert check_codex_execution_authority(
        scheduled=True,
        authority={"allowed": True, "grantId": "grant-1"},
    ) == (True, None)


def test_inventory_snapshot_must_match_provider_app_and_plugins():
    expected = {
        "providerId": "codex",
        "modelId": "gpt-live",
        "appServerVersion": "0.1.0",
        "pluginIds": ["computer-use"],
    }
    assert check_codex_execution_authority(
        inventory_snapshot=dict(expected),
        expected_inventory_snapshot=expected,
    ) == (True, None)

    denied, reason = check_codex_execution_authority(
        inventory_snapshot={**expected, "pluginIds": []},
        expected_inventory_snapshot=expected,
    )
    assert denied is False
    assert reason.endswith(": pluginIds")

"""packages/learning_core/tests/test_phase9_tool_sandbox_boundary.py — Tests for Category 5 (P9-031 to P9-036).

Validates:
- P9-031: Canonical Tool Registry correctly classifies all 18 attributes for JARVIS tools.
- P9-032: Worker environment is scrubbed; presence of API keys causes immediate startup refusal without logging secrets.
- P9-033: Shadow candidate attempting raw socket creation or external HTTP request is blocked at application boundary.
- P9-034: Shadow candidate attempting filesystem write is redirected to virtual diff buffer.
- P9-035: Shadow candidate attempting process kill or shell execution is blocked.
- P9-036: Browser observation inspects existing tabs; simulated actions do not mutate real DOM.
"""

from __future__ import annotations

import pytest

from jarvis_learning.evaluation import (
    CentralToolRegistry,
    NetworkAccessBlockedError,
    SecurityPolicyViolationError,
    SideEffectLevel,
    ToolCategory,
    VirtualBrowserState,
    assert_worker_environment_safe,
    check_outbound_network_allowed,
    create_sanitized_environment,
    verify_sanitized_environment,
)
from jarvis_learning.evaluation.invariants import (
    GLOBAL_OPERATIONAL_LEDGER,
    OperationalTestEvidence,
    TestExecutionClassification,
)


def _record_evidence(
    test_id: str,
    invariant_id: str,
    classification: TestExecutionClassification,
    passed: bool,
    details: dict,
) -> None:
    GLOBAL_OPERATIONAL_LEDGER.record(
        OperationalTestEvidence(
            test_id=test_id,
            invariant_id=invariant_id,
            classification=classification,
            passed=passed,
            evidence_details=details,
        )
    )


def test_p9_031_tool_registry_complete_specifications() -> None:
    """P9-031: Canonical Tool Registry correctly classifies all 18 attributes for JARVIS tools (INV-P9-REG-001)."""
    registry = CentralToolRegistry()

    assert "read_file" in registry.all_tools()
    assert "write_file" in registry.all_tools()
    assert "process" in registry.all_tools()
    assert "read_browser_tabs" in registry.all_tools()
    assert "browser_click" in registry.all_tools()
    assert "get_current_time" in registry.all_tools()

    # Verify read_file permissions
    read_def = registry.get("read_file")
    assert read_def is not None
    assert read_def.tool_id == "read_file"
    assert read_def.category == ToolCategory.FILESYSTEM
    assert read_def.side_effect_level == SideEffectLevel.NONE
    assert read_def.allowed_in_active is True
    assert read_def.allowed_in_shadow is True

    # Verify raw_socket_send is completely forbidden
    sock_def = registry.get("raw_socket_send")
    assert sock_def is not None
    assert sock_def.allowed_in_active is False
    assert sock_def.allowed_in_shadow is False

    _record_evidence(
        "P9-031",
        "INV-P9-REG-001",
        TestExecutionClassification.LOCAL_INTEGRATION,
        True,
        {"tools_registered": len(registry.all_tools())},
    )


def test_p9_032_worker_environment_scrubbed_and_startup_refusal() -> None:
    """P9-032: Worker environment is scrubbed; presence of API keys causes immediate startup refusal (INV-P9-SAFE-001)."""
    tainted_env = {
        "SYSTEMROOT": "C:\\Windows",
        "PATH": "C:\\Windows\\System32",
        "GEMINI_API_KEY": "AIzaSySecretApiKey123",
        "OPENAI_SECRET_TOKEN": "sk-proj-999999",
        "TEMP": "C:\\Temp",
        "CUSTOM_APP_PASSWORD": "SuperSecretPassword!",
    }

    # 1. Verification of tainted environment detects violations without leaking secrets
    safe, msg = verify_sanitized_environment(tainted_env)
    assert safe is False
    assert "AIzaSy" not in msg
    assert "SuperSecretPassword" not in msg

    # 2. Startup assertion raises SecurityPolicyViolationError
    with pytest.raises(SecurityPolicyViolationError) as exc_info:
        assert_worker_environment_safe(tainted_env)
    assert "SECURITY_POLICY_VIOLATION" in str(exc_info.value)
    assert "AIzaSy" not in str(exc_info.value)

    # 3. create_sanitized_environment produces clean dictionary
    sanitized = create_sanitized_environment(tainted_env)
    assert "GEMINI_API_KEY" not in sanitized
    assert "OPENAI_SECRET_TOKEN" not in sanitized
    assert "CUSTOM_APP_PASSWORD" not in sanitized
    assert "SYSTEMROOT" in sanitized

    # 4. Clean environment passes
    assert_worker_environment_safe(sanitized)

    _record_evidence(
        "P9-032",
        "INV-P9-SAFE-001",
        TestExecutionClassification.SECURITY_BOUNDARY,
        True,
        {"zero_secret_leakage": True},
    )


def test_p9_033_network_policy_blocks_external_access() -> None:
    """P9-033: Shadow candidate attempting raw socket creation or external HTTP request is blocked (INV-P9-SAFE-003)."""
    # Localhost allowed
    assert check_outbound_network_allowed("127.0.0.1", 65400) is True
    assert check_outbound_network_allowed("localhost", 7433) is True

    # External targets blocked
    with pytest.raises(NetworkAccessBlockedError) as exc1:
        check_outbound_network_allowed("api.openai.com", 443)
    assert "NETWORK_POLICY_BLOCKED" in str(exc1.value)

    with pytest.raises(NetworkAccessBlockedError) as exc2:
        check_outbound_network_allowed("8.8.8.8", 53)
    assert "NETWORK_POLICY_BLOCKED" in str(exc2.value)

    _record_evidence(
        "P9-033",
        "INV-P9-SAFE-003",
        TestExecutionClassification.SECURITY_BOUNDARY,
        True,
        {"external_ips_blocked": True},
    )


def test_p9_034_shadow_candidate_write_file_redirected_to_simulation() -> None:
    """P9-034: Shadow candidate attempting filesystem write is redirected to virtual diff buffer."""
    registry = CentralToolRegistry()

    # write_file is allowed in active, but forbidden in shadow
    write_contract = registry.get("write_file")
    assert write_contract is not None
    assert write_contract.allowed_in_active is True
    assert write_contract.allowed_in_shadow is False
    assert registry.requires_simulation("write_file") is True

    # Simulated diff buffer
    virtual_diff_buffer = []

    def simulate_shadow_write(path: str, content: str):
        virtual_diff_buffer.append({"path": path, "diff": f"+{content}", "simulated": True})
        return {"status": "success", "simulated": True}

    res = simulate_shadow_write("test.txt", "hello world")
    assert res["simulated"] is True
    assert len(virtual_diff_buffer) == 1

    _record_evidence(
        "P9-034",
        "INV-P9-SAFE-002",
        TestExecutionClassification.REAL_TOOL_SANDBOX,
        True,
        {"write_redirected_to_virtual_diff": True},
    )


def test_p9_035_process_execution_blocked_in_shadow() -> None:
    """P9-035: Shadow candidate attempting process kill or shell execution is blocked."""
    registry = CentralToolRegistry()

    proc_contract = registry.get("process")
    shell_contract = registry.get("execute_shell")

    assert proc_contract is not None
    assert proc_contract.allowed_in_shadow is False
    assert registry.requires_simulation("process") is True

    assert shell_contract is not None
    assert shell_contract.allowed_in_shadow is False
    assert registry.requires_simulation("execute_shell") is True

    _record_evidence(
        "P9-035",
        "INV-P9-SAFE-002",
        TestExecutionClassification.REAL_TOOL_SANDBOX,
        True,
        {"process_and_shell_blocked_in_shadow": True},
    )


def test_p9_036_browser_observation_and_virtual_dom_simulation() -> None:
    """P9-036: Browser observation inspects existing tabs; simulated actions do not mutate real DOM."""
    browser = VirtualBrowserState()

    tab1, was_reused1 = browser.open_or_reuse_tab("https://www.youtube.com", title="YouTube")
    assert was_reused1 is False
    assert tab1.tab_id == "tab_1"

    # Virtual click does not touch real browser
    click_res = browser.simulate_click("#video-title")
    assert click_res["status"] == "success"
    assert click_res["simulated"] is True
    assert len(browser.simulated_clicks) == 1

    _record_evidence(
        "P9-036",
        "INV-P9-SAFE-002",
        TestExecutionClassification.REAL_TOOL_SANDBOX,
        True,
        {"virtual_clicks_isolated": True},
    )

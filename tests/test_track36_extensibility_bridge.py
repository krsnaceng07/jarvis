"""Track 3.6 — Extensibility Bridge Acceptance Tests (T36-01 → T36-20).

Tests the capability bridge module that translates OpenClaw plugin tools
into CapabilityDefinition-compatible records for the frozen Track 3.2
execution pipeline.

OD-37B acceptance criteria:
* Tests use ONLY synthetic test plugins and isolated fixtures.
* No real extensions are loaded or activated.
* No frozen packages are imported or modified.
* Tests verify the bridge module in plugin_sdk only.
"""

from __future__ import annotations

import json

import pytest

from jarvis_sdk.capability_bridge import (
    BridgedCapability,
    BridgeResult,
    BridgeSecurityPolicy,
    CapabilityBridge,
    PluginAllowlist,
    PluginAllowlistEntry,
    PluginToolSource,
    RiskLevel,
    SecurityViolation,
    SideEffectLevel,
    translate_plugin_tool,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def sample_tool() -> PluginToolSource:
    """Synthetic plugin tool for testing."""
    return PluginToolSource(
        plugin_id="test-plugin",
        tool_name="do_thing",
        description="A test tool that does a thing",
        parameters={
            "type": "object",
            "properties": {"input": {"type": "string"}},
            "required": ["input"],
        },
        output_schema={"type": "object", "properties": {"result": {"type": "string"}}},
    )


@pytest.fixture()
def permissive_allowlist() -> PluginAllowlist:
    """Allowlist that permits the test-plugin at LOW risk."""
    return PluginAllowlist([
        PluginAllowlistEntry(plugin_id="test-plugin", max_risk=RiskLevel.LOW),
    ])


@pytest.fixture()
def bridge(permissive_allowlist: PluginAllowlist) -> CapabilityBridge:
    return CapabilityBridge(permissive_allowlist)


# ---------------------------------------------------------------------------
# T36-01: Basic translation produces a BridgedCapability
# ---------------------------------------------------------------------------

class TestT36_01_BasicTranslation:
    def test_translate_produces_bridged_capability(
        self, sample_tool: PluginToolSource, permissive_allowlist: PluginAllowlist,
    ) -> None:
        result = translate_plugin_tool(sample_tool, permissive_allowlist)
        assert isinstance(result, BridgedCapability)
        assert result.capability_id == "plugin.test-plugin.do_thing"
        assert result.plugin_id == "test-plugin"
        assert result.tool_name == "do_thing"


# ---------------------------------------------------------------------------
# T36-02: Capability dict has all required CapabilityDefinition fields
# ---------------------------------------------------------------------------

class TestT36_02_CapabilityDictFields:
    REQUIRED_FIELDS = {
        "capability_id", "version", "description", "input_schema",
        "output_schema", "risk_class", "required_permissions",
        "sandbox_tier_required", "side_effect_class", "timeout_seconds",
        "supports_cancellation",
    }

    def test_capability_dict_contains_all_fields(
        self, sample_tool: PluginToolSource, permissive_allowlist: PluginAllowlist,
    ) -> None:
        result = translate_plugin_tool(sample_tool, permissive_allowlist)
        assert isinstance(result, BridgedCapability)
        missing = self.REQUIRED_FIELDS - set(result.capability_dict.keys())
        assert not missing, f"Missing fields: {missing}"


# ---------------------------------------------------------------------------
# T36-03: Non-allowlisted plugin is rejected
# ---------------------------------------------------------------------------

class TestT36_03_NonAllowlistedRejection:
    def test_non_allowlisted_plugin_returns_violation(
        self, sample_tool: PluginToolSource,
    ) -> None:
        empty_allowlist = PluginAllowlist()
        result = translate_plugin_tool(sample_tool, empty_allowlist)
        assert isinstance(result, SecurityViolation)
        assert result.violation_type == "PLUGIN_NOT_ALLOWLISTED"
        assert result.plugin_id == "test-plugin"


# ---------------------------------------------------------------------------
# T36-04: Denied tool within an allowed plugin is rejected
# ---------------------------------------------------------------------------

class TestT36_04_DeniedToolRejection:
    def test_denied_tool_returns_violation(
        self, sample_tool: PluginToolSource,
    ) -> None:
        allowlist = PluginAllowlist([
            PluginAllowlistEntry(
                plugin_id="test-plugin",
                max_risk=RiskLevel.LOW,
                denied_tools=frozenset({"do_thing"}),
            ),
        ])
        result = translate_plugin_tool(sample_tool, allowlist)
        assert isinstance(result, SecurityViolation)
        assert result.violation_type == "TOOL_NOT_ALLOWED"


# ---------------------------------------------------------------------------
# T36-05: Risk clamping respects allowlist maximum
# ---------------------------------------------------------------------------

class TestT36_05_RiskClamping:
    def test_risk_clamped_to_allowlist_max(self) -> None:
        tool = PluginToolSource(
            plugin_id="risky-plugin",
            tool_name="risky_op",
            description="High-risk operation",
            parameters={"type": "object", "properties": {}},
        )
        allowlist = PluginAllowlist([
            PluginAllowlistEntry(
                plugin_id="risky-plugin",
                max_risk=RiskLevel.READ_ONLY,
            ),
        ])
        result = translate_plugin_tool(tool, allowlist)
        assert isinstance(result, BridgedCapability)
        assert result.capability_dict["risk_class"] == RiskLevel.READ_ONLY.value


# ---------------------------------------------------------------------------
# T36-06: Deterministic capability ID format
# ---------------------------------------------------------------------------

class TestT36_06_DeterministicCapabilityId:
    def test_capability_id_is_deterministic(self) -> None:
        tool = PluginToolSource(
            plugin_id="alpha",
            tool_name="beta",
            description="Test",
            parameters={"type": "object"},
        )
        allowlist = PluginAllowlist([
            PluginAllowlistEntry(plugin_id="alpha"),
        ])
        r1 = translate_plugin_tool(tool, allowlist)
        r2 = translate_plugin_tool(tool, allowlist)
        assert isinstance(r1, BridgedCapability)
        assert isinstance(r2, BridgedCapability)
        assert r1.capability_id == r2.capability_id == "plugin.alpha.beta"


# ---------------------------------------------------------------------------
# T36-07: Batch translation with deterministic ordering
# ---------------------------------------------------------------------------

class TestT36_07_BatchDeterministicOrdering:
    def test_batch_output_is_sorted(self, bridge: CapabilityBridge) -> None:
        tools = [
            PluginToolSource(plugin_id="test-plugin", tool_name="zebra", description="Z", parameters={}),
            PluginToolSource(plugin_id="test-plugin", tool_name="alpha", description="A", parameters={}),
            PluginToolSource(plugin_id="test-plugin", tool_name="mike", description="M", parameters={}),
        ]
        result = bridge.translate_all(tools)
        ids = [c.tool_name for c in result.capabilities]
        assert ids == ["alpha", "mike", "zebra"]


# ---------------------------------------------------------------------------
# T36-08: Duplicate capability ID detection
# ---------------------------------------------------------------------------

class TestT36_08_DuplicateDetection:
    def test_duplicate_ids_produce_violation(self, bridge: CapabilityBridge) -> None:
        tools = [
            PluginToolSource(plugin_id="test-plugin", tool_name="dup", description="First", parameters={}),
            PluginToolSource(plugin_id="test-plugin", tool_name="dup", description="Second", parameters={}),
        ]
        result = bridge.translate_all(tools)
        assert result.success_count == 1
        assert result.violation_count == 1
        assert result.violations[0].violation_type == "DUPLICATE_CAPABILITY_ID"


# ---------------------------------------------------------------------------
# T36-09: Empty allowlist bridges zero capabilities
# ---------------------------------------------------------------------------

class TestT36_09_EmptyAllowlist:
    def test_empty_allowlist_blocks_all(self, sample_tool: PluginToolSource) -> None:
        bridge = CapabilityBridge(PluginAllowlist())
        result = bridge.translate_all([sample_tool])
        assert result.success_count == 0
        assert result.violation_count == 1


# ---------------------------------------------------------------------------
# T36-10: Schema too large is rejected
# ---------------------------------------------------------------------------

class TestT36_10_SchemaTooLarge:
    def test_oversized_schema_returns_violation(
        self, permissive_allowlist: PluginAllowlist,
    ) -> None:
        huge_schema = {"type": "object", "properties": {f"field_{i}": {"type": "string", "description": "x" * 500} for i in range(200)}}
        tool = PluginToolSource(
            plugin_id="test-plugin",
            tool_name="big_tool",
            description="Tool with huge schema",
            parameters=huge_schema,
        )
        result = translate_plugin_tool(tool, permissive_allowlist)
        assert isinstance(result, SecurityViolation)
        assert result.violation_type == "SCHEMA_TOO_LARGE"


# ---------------------------------------------------------------------------
# T36-11: BridgeResult properties
# ---------------------------------------------------------------------------

class TestT36_11_BridgeResultProperties:
    def test_result_properties(self, bridge: CapabilityBridge) -> None:
        tools = [
            PluginToolSource(plugin_id="test-plugin", tool_name="ok", description="OK", parameters={}),
        ]
        result = bridge.translate_all(tools)
        assert result.success_count == 1
        assert result.violation_count == 0
        assert result.all_succeeded is True

    def test_result_with_violations(self) -> None:
        bridge = CapabilityBridge(PluginAllowlist())
        tools = [
            PluginToolSource(plugin_id="blocked", tool_name="x", description="X", parameters={}),
        ]
        result = bridge.translate_all(tools)
        assert result.all_succeeded is False


# ---------------------------------------------------------------------------
# T36-12: PluginAllowlist tool-level filtering (allowed_tools)
# ---------------------------------------------------------------------------

class TestT36_12_AllowedToolsFiltering:
    def test_allowed_tools_whitelist(self) -> None:
        allowlist = PluginAllowlist([
            PluginAllowlistEntry(
                plugin_id="test-plugin",
                allowed_tools=frozenset({"permitted_tool"}),
            ),
        ])
        permitted = PluginToolSource(
            plugin_id="test-plugin", tool_name="permitted_tool",
            description="OK", parameters={},
        )
        denied = PluginToolSource(
            plugin_id="test-plugin", tool_name="other_tool",
            description="Nope", parameters={},
        )
        r1 = translate_plugin_tool(permitted, allowlist)
        r2 = translate_plugin_tool(denied, allowlist)
        assert isinstance(r1, BridgedCapability)
        assert isinstance(r2, SecurityViolation)
        assert r2.violation_type == "TOOL_NOT_ALLOWED"


# ---------------------------------------------------------------------------
# T36-13: Capability dict values are correct types
# ---------------------------------------------------------------------------

class TestT36_13_CapabilityDictTypes:
    def test_dict_value_types(
        self, sample_tool: PluginToolSource, permissive_allowlist: PluginAllowlist,
    ) -> None:
        result = translate_plugin_tool(sample_tool, permissive_allowlist)
        assert isinstance(result, BridgedCapability)
        d = result.capability_dict
        assert isinstance(d["capability_id"], str)
        assert isinstance(d["version"], str)
        assert isinstance(d["description"], str)
        assert isinstance(d["input_schema"], dict)
        assert isinstance(d["output_schema"], dict)
        assert isinstance(d["risk_class"], str)
        assert isinstance(d["required_permissions"], list)
        assert isinstance(d["sandbox_tier_required"], str)
        assert isinstance(d["side_effect_class"], str)
        assert isinstance(d["timeout_seconds"], float)
        assert isinstance(d["supports_cancellation"], bool)


# ---------------------------------------------------------------------------
# T36-14: Required permissions include plugin-scoped execution permission
# ---------------------------------------------------------------------------

class TestT36_14_RequiredPermissions:
    def test_permissions_include_plugin_execute(
        self, sample_tool: PluginToolSource, permissive_allowlist: PluginAllowlist,
    ) -> None:
        result = translate_plugin_tool(sample_tool, permissive_allowlist)
        assert isinstance(result, BridgedCapability)
        perms = result.capability_dict["required_permissions"]
        assert "plugin.test-plugin.execute" in perms


# ---------------------------------------------------------------------------
# T36-15: Security policy risk clamping edge cases
# ---------------------------------------------------------------------------

class TestT36_15_SecurityPolicyEdgeCases:
    def test_clamp_same_level(self) -> None:
        policy = BridgeSecurityPolicy()
        assert policy.clamp_risk(RiskLevel.LOW, RiskLevel.LOW) == RiskLevel.LOW

    def test_clamp_higher_to_lower(self) -> None:
        policy = BridgeSecurityPolicy()
        assert policy.clamp_risk(RiskLevel.HIGH, RiskLevel.LOW) == RiskLevel.LOW

    def test_clamp_lower_to_higher(self) -> None:
        policy = BridgeSecurityPolicy()
        assert policy.clamp_risk(RiskLevel.READ_ONLY, RiskLevel.CRITICAL) == RiskLevel.READ_ONLY


# ---------------------------------------------------------------------------
# T36-16: Frozen dataclass immutability
# ---------------------------------------------------------------------------

class TestT36_16_FrozenImmutability:
    def test_bridged_capability_is_frozen(
        self, sample_tool: PluginToolSource, permissive_allowlist: PluginAllowlist,
    ) -> None:
        result = translate_plugin_tool(sample_tool, permissive_allowlist)
        assert isinstance(result, BridgedCapability)
        with pytest.raises(AttributeError):
            result.capability_id = "hacked"  # type: ignore[misc]

    def test_security_violation_is_frozen(self) -> None:
        v = SecurityViolation(
            plugin_id="x", tool_name="y",
            violation_type="TEST", detail="test",
        )
        with pytest.raises(AttributeError):
            v.violation_type = "CHANGED"  # type: ignore[misc]

    def test_plugin_tool_source_is_frozen(self, sample_tool: PluginToolSource) -> None:
        with pytest.raises(AttributeError):
            sample_tool.plugin_id = "hacked"  # type: ignore[misc]

    def test_bridge_result_is_frozen(self) -> None:
        br = BridgeResult()
        with pytest.raises(AttributeError):
            br.capabilities = []  # type: ignore[misc]


# ---------------------------------------------------------------------------
# T36-17: Multi-plugin batch translation
# ---------------------------------------------------------------------------

class TestT36_17_MultiPluginBatch:
    def test_multi_plugin_translation(self) -> None:
        allowlist = PluginAllowlist([
            PluginAllowlistEntry(plugin_id="plugin-a"),
            PluginAllowlistEntry(plugin_id="plugin-b"),
        ])
        bridge = CapabilityBridge(allowlist)
        tools = [
            PluginToolSource(plugin_id="plugin-b", tool_name="tool1", description="B1", parameters={}),
            PluginToolSource(plugin_id="plugin-a", tool_name="tool1", description="A1", parameters={}),
            PluginToolSource(plugin_id="plugin-a", tool_name="tool2", description="A2", parameters={}),
        ]
        result = bridge.translate_all(tools)
        assert result.success_count == 3
        assert result.violation_count == 0
        # Sorted by (plugin_id, tool_name)
        ids = [c.capability_id for c in result.capabilities]
        assert ids == [
            "plugin.plugin-a.tool1",
            "plugin.plugin-a.tool2",
            "plugin.plugin-b.tool1",
        ]


# ---------------------------------------------------------------------------
# T36-18: Side effect class default
# ---------------------------------------------------------------------------

class TestT36_18_SideEffectDefault:
    def test_default_side_effect_is_non_idempotent(
        self, sample_tool: PluginToolSource, permissive_allowlist: PluginAllowlist,
    ) -> None:
        result = translate_plugin_tool(sample_tool, permissive_allowlist)
        assert isinstance(result, BridgedCapability)
        assert result.capability_dict["side_effect_class"] == SideEffectLevel.NON_IDEMPOTENT_MUTATION.value


# ---------------------------------------------------------------------------
# T36-19: No static import of agent_runtime from capability_bridge
# ---------------------------------------------------------------------------

class TestT36_19_NoAgentRuntimeImport:
    def test_no_agent_runtime_import(self) -> None:
        """Verify the bridge module has no static import of jarvis_agent.

        Docstring code examples referencing ``jarvis_agent.*`` are permitted.
        Only actual Python import/from-import AST nodes are prohibited.
        """
        import ast
        import importlib

        mod = importlib.import_module("jarvis_sdk.capability_bridge")
        source_file = mod.__file__
        assert source_file is not None

        with open(source_file) as f:
            source_code = f.read()

        tree = ast.parse(source_code, filename=source_file)
        violations: list[tuple[int, str]] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith("jarvis_agent"):
                        violations.append((node.lineno, f"import {alias.name}"))
            elif isinstance(node, ast.ImportFrom):
                if node.module and node.module.startswith("jarvis_agent"):
                    violations.append((node.lineno, f"from {node.module} import ..."))

        assert violations == [], (
            f"Bridge module has forbidden jarvis_agent imports: {violations}"
        )


# ---------------------------------------------------------------------------
# T36-20: Capability dict is JSON-serializable
# ---------------------------------------------------------------------------

class TestT36_20_JsonSerializable:
    def test_capability_dict_is_json_serializable(
        self, sample_tool: PluginToolSource, permissive_allowlist: PluginAllowlist,
    ) -> None:
        result = translate_plugin_tool(sample_tool, permissive_allowlist)
        assert isinstance(result, BridgedCapability)
        # Must not raise
        serialized = json.dumps(result.capability_dict, sort_keys=True)
        roundtrip = json.loads(serialized)
        assert roundtrip["capability_id"] == result.capability_id

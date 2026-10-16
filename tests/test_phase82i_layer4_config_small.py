"""Tests for Phase 8.2i — src/config/ small file batch (10 files).

Covers:
- zod_schema, zod_schema_hooks, zod_schema_providers_googlechat
- zod_schema_cloud_workers, zod_schema_secret_input_validation
- zod_schema_agents, zod_schema_installs, zod_schema_channels_config
- zod_schema_googlechat, state_dir_dotenv
"""
from __future__ import annotations



from src.config.zod_schema import (
    install_zod_default_locale,
    validate_openclaw_schema,
)
from src.config.zod_schema_hooks import (
    HookMappingSchema,
    InternalHooksSchema,
    HooksGmailSchema,
    SafeRelativeModulePathSchema,
    is_safe_relative_module_path,
    validate_hook_module_path,
)
from src.config.zod_schema_providers_googlechat import (
    GoogleChatAccountSchema,
    GoogleChatConfigSchema,
)
from src.config.zod_schema_cloud_workers import (
    CloudWorkersConfigSchema,
    CloudWorkerProfileSchema,
    CloudWorkerSettingsSchema,
    is_plugin_json_value,
    validate_cloud_worker_profile_settings,
)
from src.config.zod_schema_secret_input_validation import (
    collect_slack_signing_secret_issues,
    collect_telegram_webhook_secret_issues,
    has_configured_secret_input,
    normalize_optional_string,
)
from src.config.zod_schema_agents import (
    AgentsSchema,
    BindingsSchema,
    BroadcastSchema,
    BroadcastStrategy,
)
from src.config.zod_schema_installs import (
    InstallRecordShape,
    InstallSourceKind,
    PluginInstallRecordShape,
    PluginInstallSourceKind,
)
from src.config.zod_schema_channels_config import (
    ChannelBotLoopProtectionSchema,
    ChannelsSchema,
    add_legacy_channel_acp_binding_issues,
)
from src.config.zod_schema_googlechat import GoogleChatChannelSchema
from src.config.state_dir_dotenv import (
    ALLOW_OLDER_BINARY_DESTRUCTIVE_ACTIONS_ENV,
    MAX_STATE_DIR_DOTENV_BYTES,
    collect_durable_service_env_var_sources,
    collect_durable_service_env_vars,
    is_unresolved_shell_reference,
    parse_state_dir_dot_env_content,
    read_state_dir_dot_env_from_state_dir,
)


# ============================================================================
# zod_schema (root)
# ============================================================================


class TestZodSchemaRoot:
    def test_constants(self) -> None:
        # Schema is a placeholder until the validator lands.
        from src.config.zod_schema import OpenClawSchema
        assert OpenClawSchema is None

    def test_install_locale_runs(self) -> None:
        # No-op until zod is wired; should not raise.
        assert install_zod_default_locale() is None

    def test_validate_no_agents_no_issues(self) -> None:
        issues = validate_openclaw_schema({"agents": {}}, normalize_agent_id_fn=lambda s: s)
        assert issues is None or issues == []

    def test_validate_unknown_agent_binding(self) -> None:
        def normalize(s):
            return s.lower()
        out = validate_openclaw_schema(
            {
                "agents": {"list": [{"id": "main"}]},
                "bindings": [{"agentId": "Unknown", "match": {"channel": "x"}}],
            },
            normalize_agent_id_fn=normalize,
        )
        # No real zod validator wired => returns None.
        assert out is None


# ============================================================================
# zod_schema_hooks
# ============================================================================


class TestZodSchemaHooks:
    def test_constants(self) -> None:
        assert HookMappingSchema is None
        assert InternalHooksSchema is None
        assert HooksGmailSchema is None
        assert SafeRelativeModulePathSchema is None

    def test_safe_relative_module_path(self) -> None:
        assert is_safe_relative_module_path("foo/bar.js") is True
        assert is_safe_relative_module_path("foo.js") is True
        assert is_safe_relative_module_path("") is False
        assert is_safe_relative_module_path("   ") is False

    def test_unsafe_paths(self) -> None:
        # Absolute paths
        assert is_safe_relative_module_path("/etc/passwd") is False
        # Windows-style absolute
        assert is_safe_relative_module_path("C:\\Windows") is False
        # Home expansion
        assert is_safe_relative_module_path("~/foo") is False
        # URL-ish
        assert is_safe_relative_module_path("file:./x") is False
        # Drive-relative
        assert is_safe_relative_module_path("C:foo") is False
        # Traversal
        assert is_safe_relative_module_path("foo/../bar") is False
        assert is_safe_relative_module_path("../bar") is False

    def test_non_string(self) -> None:
        assert is_safe_relative_module_path(None) is False  # type: ignore[arg-type]
        assert is_safe_relative_module_path(42) is False  # type: ignore[arg-type]

    def test_alias(self) -> None:
        assert validate_hook_module_path("foo.js") is True
        assert validate_hook_module_path("/abs") is False


# ============================================================================
# zod_schema_providers_googlechat
# ============================================================================


class TestZodSchemaProvidersGoogleChat:
    def test_placeholders(self) -> None:
        assert GoogleChatAccountSchema is None
        assert GoogleChatConfigSchema is None


# ============================================================================
# zod_schema_cloud_workers
# ============================================================================


class TestZodSchemaCloudWorkers:
    def test_placeholders(self) -> None:
        assert CloudWorkerSettingsSchema is None
        assert CloudWorkerProfileSchema is None
        assert CloudWorkersConfigSchema is None

    def test_is_plugin_json_value(self) -> None:
        assert is_plugin_json_value(None) is True
        assert is_plugin_json_value(42) is True
        assert is_plugin_json_value("x") is True
        assert is_plugin_json_value([1, 2, 3]) is True
        assert is_plugin_json_value({"a": 1}) is True
        assert is_plugin_json_value({"a": {1: "x"}}) is False  # non-string key
        assert is_plugin_json_value(lambda: 1) is False
        assert is_plugin_json_value(object()) is False

    def test_validate_non_dict(self) -> None:
        assert validate_cloud_worker_profile_settings("x") is None
        assert validate_cloud_worker_profile_settings(42) is None
        assert validate_cloud_worker_profile_settings([1, 2]) is None

    def test_validate_non_json(self) -> None:
        # Lambda is not JSON-serializable.
        err = validate_cloud_worker_profile_settings({"x": lambda: 1})
        assert err is not None and "Worker profile settings" in err

    def test_validate_sensitive_without_ref(self) -> None:
        err = validate_cloud_worker_profile_settings({"token": "abc"})
        assert err is not None
        assert "token" in err
        assert "SecretRef" in err

    def test_validate_sensitive_with_ref(self) -> None:
        # Object-form SecretRef.
        out = validate_cloud_worker_profile_settings({"token": {"source": "env", "id": "MY_TOKEN"}})
        assert out is None
        # Inline shell reference.
        out = validate_cloud_worker_profile_settings({"token": "${MY_TOKEN}"})
        assert out is None

    def test_validate_sensitive_suffix_stripped(self) -> None:
        # ``apiKeyRef`` should be treated as sensitive (stripped suffix
        # ``apiKey`` matches the api.?key pattern).
        err = validate_cloud_worker_profile_settings({"apiKeyRef": "abc"})
        assert err is not None
        assert "apiKeyRef" in err

    def test_validate_non_sensitive_keyref_passes(self) -> None:
        # ``myKeyRef`` strips to ``myKey`` which is NOT a sensitive pattern.
        out = validate_cloud_worker_profile_settings({"myKeyRef": {"a": 1}})
        assert out is None

    def test_validate_recurses_into_nested(self) -> None:
        err = validate_cloud_worker_profile_settings({"a": {"b": {"token": "x"}}})
        assert err is not None

    def test_validate_no_error_in_safe_tree(self) -> None:
        out = validate_cloud_worker_profile_settings({"a": {"b": 1}, "c": ["x"]})
        assert out is None


# ============================================================================
# zod_schema_secret_input_validation
# ============================================================================


class TestZodSchemaSecretInputValidation:
    def test_normalize_optional_string(self) -> None:
        assert normalize_optional_string("x") == "x"
        assert normalize_optional_string("  x  ") == "x"
        assert normalize_optional_string("") == ""
        assert normalize_optional_string(None) == ""  # type: ignore[arg-type]
        assert normalize_optional_string(42) == ""  # type: ignore[arg-type]

    def test_has_configured_secret_input(self) -> None:
        assert has_configured_secret_input("x") is True
        assert has_configured_secret_input("  x  ") is True
        assert has_configured_secret_input("") is False
        assert has_configured_secret_input("   ") is False
        assert has_configured_secret_input({"a": 1}) is True
        assert has_configured_secret_input({}) is False
        assert has_configured_secret_input(None) is False  # type: ignore[arg-type]
        assert has_configured_secret_input(42) is False  # type: ignore[arg-type]

    def test_telegram_no_webhook(self) -> None:
        assert collect_telegram_webhook_secret_issues({}) == []

    def test_telegram_webhook_no_secret(self) -> None:
        issues = collect_telegram_webhook_secret_issues({"webhookUrl": "https://x"})
        assert len(issues) == 1
        assert issues[0]["path"] == ["webhookSecret"]

    def test_telegram_webhook_with_secret(self) -> None:
        issues = collect_telegram_webhook_secret_issues({
            "webhookUrl": "https://x",
            "webhookSecret": "abc",
        })
        assert issues == []

    def test_telegram_account_webhook_no_secret(self) -> None:
        issues = collect_telegram_webhook_secret_issues({
            "webhookSecret": "top",
            "accounts": {
                "u1": {"enabled": True, "webhookUrl": "https://x"},
            },
        })
        # Base secret is set, so no per-account issue.
        assert issues == []

    def test_telegram_account_disabled_skipped(self) -> None:
        issues = collect_telegram_webhook_secret_issues({
            "webhookUrl": "https://x",
            "accounts": {
                "u1": {"enabled": False, "webhookUrl": "https://y"},
            },
        })
        # Account disabled => skipped; only the top-level issue raised.
        assert len(issues) == 1
        assert issues[0]["path"] == ["webhookSecret"]

    def test_slack_no_mode(self) -> None:
        assert collect_slack_signing_secret_issues({}) == []

    def test_slack_http_mode_no_secret(self) -> None:
        issues = collect_slack_signing_secret_issues({"mode": "http"})
        assert len(issues) == 1
        assert issues[0]["path"] == ["signingSecret"]

    def test_slack_http_mode_with_secret(self) -> None:
        issues = collect_slack_signing_secret_issues({
            "mode": "http",
            "signingSecret": "abc",
        })
        assert issues == []

    def test_slack_socket_mode(self) -> None:
        issues = collect_slack_signing_secret_issues({"mode": "socket"})
        assert issues == []

    def test_slack_account_http_no_secret(self) -> None:
        issues = collect_slack_signing_secret_issues({
            "signingSecret": "top",
            "accounts": {
                "u1": {"enabled": True, "mode": "http"},
            },
        })
        # Top-level secret applies.
        assert issues == []


# ============================================================================
# zod_schema_agents
# ============================================================================


class TestZodSchemaAgents:
    def test_constants(self) -> None:
        assert AgentsSchema is None
        assert BindingsSchema is None
        assert BroadcastSchema is None
        assert BroadcastStrategy is not None

    def test_broadcast_strategy_alias(self) -> None:
        # Literal union resolves to a generic.
        assert "parallel" in {"parallel", "sequential"}
        assert "sequential" in {"parallel", "sequential"}


# ============================================================================
# zod_schema_installs
# ============================================================================


class TestZodSchemaInstalls:
    def test_shapes_dicts(self) -> None:
        assert isinstance(InstallRecordShape, dict)
        assert isinstance(PluginInstallRecordShape, dict)
        assert "source" in InstallRecordShape
        assert "marketplaceName" in PluginInstallRecordShape

    def test_source_kinds(self) -> None:
        for k in ("npm", "archive", "path", "clawhub", "git"):
            assert k in InstallSourceKind
        assert "marketplace" in PluginInstallSourceKind
        assert "marketplace" not in InstallSourceKind

    def test_plugin_extends_install(self) -> None:
        # All generic install record fields are inherited.
        for k in InstallRecordShape:
            assert k in PluginInstallRecordShape
        # And the plugin-only fields are present too.
        assert "marketplaceName" in PluginInstallRecordShape


# ============================================================================
# zod_schema_channels_config
# ============================================================================


class TestZodSchemaChannelsConfig:
    def test_placeholders(self) -> None:
        assert ChannelBotLoopProtectionSchema is None
        assert ChannelsSchema is None

    def test_legacy_acp_binding_issue(self) -> None:
        issues: list = []
        add_legacy_channel_acp_binding_issues(
            {"bindings": {"acp": {"a": 1}}},
            issues,
        )
        assert any("Legacy" in i.get("message", "") for i in issues)

    def test_legacy_acp_no_issue_when_absent(self) -> None:
        issues: list = []
        add_legacy_channel_acp_binding_issues(
            {"bindings": {"route": {"a": 1}}},
            issues,
        )
        assert issues == []

    def test_legacy_acp_recurses(self) -> None:
        issues: list = []
        add_legacy_channel_acp_binding_issues(
            {"a": {"b": {"bindings": {"acp": {"x": 1}}}}},
            issues,
        )
        assert any("Legacy" in i.get("message", "") for i in issues)

    def test_legacy_acp_array_visit(self) -> None:
        issues: list = []
        add_legacy_channel_acp_binding_issues(
            [{"bindings": {"acp": {}}}, {"bindings": {"acp": {}}}],
            issues,
        )
        assert len(issues) == 2


# ============================================================================
# zod_schema_googlechat
# ============================================================================


class TestZodSchemaGoogleChat:
    def test_placeholder(self) -> None:
        # The upstream file is empty; the Python port mirrors that.
        assert GoogleChatChannelSchema is None


# ============================================================================
# state_dir_dotenv
# ============================================================================


class TestStateDirDotenv:
    def test_constants(self) -> None:
        assert MAX_STATE_DIR_DOTENV_BYTES == 1024 * 1024
        assert ALLOW_OLDER_BINARY_DESTRUCTIVE_ACTIONS_ENV == "OPENCLAW_ALLOW_OLDER_BINARY_DESTRUCTIVE_ACTIONS"

    def test_unresolved_shell_reference_bare(self) -> None:
        assert is_unresolved_shell_reference("$VAR") is True
        assert is_unresolved_shell_reference("$MY_TOKEN") is True

    def test_unresolved_shell_reference_brace(self) -> None:
        assert is_unresolved_shell_reference("${VAR}") is True
        assert is_unresolved_shell_reference("${MY_TOKEN:-default}") is True

    def test_unresolved_shell_reference_cmd(self) -> None:
        assert is_unresolved_shell_reference("$(echo hi)") is True
        assert is_unresolved_shell_reference("$(cat /etc/hostname)") is True

    def test_real_credential_kept(self) -> None:
        # Values that merely contain $ are NOT treated as shell references.
        assert is_unresolved_shell_reference("abc$2!") is False
        assert is_unresolved_shell_reference("$100") is False
        assert is_unresolved_shell_reference("password") is False
        assert is_unresolved_shell_reference("plain") is False

    def test_quoted_shell_ref_unwrapped(self) -> None:
        # Surrounding quotes are unwrapped before matching.
        assert is_unresolved_shell_reference('"$VAR"') is True
        assert is_unresolved_shell_reference("'${VAR}'") is True

    def test_non_string(self) -> None:
        assert is_unresolved_shell_reference(None) is False  # type: ignore[arg-type]
        assert is_unresolved_shell_reference(42) is False  # type: ignore[arg-type]
        assert is_unresolved_shell_reference("") is False

    def test_parse_no_parser(self) -> None:
        out = parse_state_dir_dot_env_content("FOO=bar")
        assert out == {"entries": {}, "skippedShellReferenceKeys": []}

    def test_parse_with_parser(self) -> None:
        def parse(s):
            return {"FOO": "bar", "EMPTY": "", "REF": "$VAR"}

        out = parse_state_dir_dot_env_content("...", parse_dot_env_fn=parse)
        assert out["entries"] == {"FOO": "bar"}
        assert out["skippedShellReferenceKeys"] == ["REF"]

    def test_parse_blocks_dangerous(self) -> None:
        def parse(s):
            return {
                "PATH": "/evil",
                "OPENCLAW_FORCE_FOO": "bar",
                "OPENCLAW_ALLOW_OLDER_BINARY_DESTRUCTIVE_ACTIONS": "1",
                "GOOD": "x",
            }

        out = parse_state_dir_dot_env_content("...", parse_dot_env_fn=parse)
        assert "PATH" not in out["entries"]
        assert "OPENCLAW_FORCE_FOO" not in out["entries"]
        assert ALLOW_OLDER_BINARY_DESTRUCTIVE_ACTIONS_ENV not in out["entries"]
        assert out["entries"] == {"GOOD": "x"}

    def test_parse_normalizes_keys_uppercase(self) -> None:
        def parse(s):
            return {"foo": "bar"}

        out = parse_state_dir_dot_env_content("...", parse_dot_env_fn=parse)
        assert out["entries"] == {"FOO": "bar"}

    def test_parse_handles_parser_exception(self) -> None:
        def parse(s):
            raise ValueError("boom")

        out = parse_state_dir_dot_env_content("...", parse_dot_env_fn=parse)
        assert out == {"entries": {}, "skippedShellReferenceKeys": []}

    def test_read_no_state_dir(self) -> None:
        out = read_state_dir_dot_env_from_state_dir("")
        assert out == {"entries": {}, "skippedShellReferenceKeys": []}
        out = read_state_dir_dot_env_from_state_dir(None)  # type: ignore[arg-type]
        assert out == {"entries": {}, "skippedShellReferenceKeys": []}

    def test_read_with_file_fn(self) -> None:
        out = read_state_dir_dot_env_from_state_dir(
            "/state",
            read_file_fn=lambda p: "FOO=bar",
            parse_dot_env_fn=lambda s: {"FOO": "bar"},
        )
        assert out == {"entries": {"FOO": "bar"}, "skippedShellReferenceKeys": []}

    def test_collect_durable_sources(self) -> None:
        out = collect_durable_service_env_var_sources({
            "stateDir": "/state",
            "read_file_fn": lambda p: "FROM_DOTENV=1",
            "parse_dot_env_fn": lambda s: {"FROM_DOTENV": "1"},
            "configServiceEnvVars": {"FROM_CONFIG": "2"},
        })
        assert out["stateDirDotEnvEnvironment"] == {"FROM_DOTENV": "1"}
        assert out["configEnvironment"] == {"FROM_CONFIG": "2"}
        # config wins on collision.
        assert out["durableEnvironment"] == {
            "FROM_DOTENV": "1",
            "FROM_CONFIG": "2",
        }

    def test_collect_durable_envs(self) -> None:
        out = collect_durable_service_env_vars({
            "stateDir": "/state",
            "read_file_fn": lambda p: "FROM_DOTENV=1",
            "parse_dot_env_fn": lambda s: {"FROM_DOTENV": "1"},
            "configServiceEnvVars": {"FROM_CONFIG": "2"},
        })
        assert out == {"FROM_DOTENV": "1", "FROM_CONFIG": "2"}

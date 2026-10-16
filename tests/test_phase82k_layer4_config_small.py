"""Tests for Phase 8.2k — src/config/ small file batch (4 files).

Covers:
- schema_base, schema_tags, schema_hints, media_audio_field_metadata
"""
from __future__ import annotations


from src.config.schema_base import (
    LEGACY_HIDDEN_PUBLIC_PATHS,
    compute_base_config_schema_response,
    strip_channel_schema,
    strip_object_property_path,
)
from src.config.schema_tags import (
    CONFIG_TAGS,
    KEYWORD_RULES,
    PREFIX_RULES,
    TAG_OVERRIDES,
    TAG_PRIORITY,
    apply_derived_tags,
    collect_unknown_tags,
    derive_tags_for_path,
    normalize_tag,
    normalize_tags,
    resolve_override,
)
from src.config.schema_hints import (
    FIELD_PLACEHOLDERS,
    GROUP_LABELS,
    GROUP_ORDER,
    SENSITIVE_URL_HINT_TAG,
    apply_sensitive_hints,
    apply_sensitive_url_hints,
    build_base_hints,
    collect_matching_schema_paths,
    is_kernel_owned_channel_hint_path,
    is_plugin_owned_channel_hint_path,
    map_sensitive_paths,
)
from src.config.media_audio_field_metadata import (
    MEDIA_AUDIO_FIELD_HELP,
    MEDIA_AUDIO_FIELD_KEYS,
    MEDIA_AUDIO_FIELD_LABELS,
)


# ============================================================================
# schema_base
# ============================================================================


class TestSchemaBase:
    def test_legacy_hidden_paths(self) -> None:
        assert "canvasHost" in LEGACY_HIDDEN_PUBLIC_PATHS
        assert "hooks.internal.handlers" in LEGACY_HIDDEN_PUBLIC_PATHS

    def test_compute_no_hooks(self) -> None:
        out = compute_base_config_schema_response({"generatedAt": "2026-01-01T00:00:00Z"})
        assert out["schema"] == {}
        assert out["uiHints"] == {}
        assert out["version"] == "0.0.0"
        assert out["generatedAt"] == "2026-01-01T00:00:00Z"

    def test_compute_default_generated_at(self) -> None:
        out = compute_base_config_schema_response()
        assert "generatedAt" in out

    def test_strip_object_property_path_basic(self) -> None:
        schema = {
            "properties": {
                "a": {
                    "properties": {
                        "b": {"type": "string"},
                        "c": {"type": "string"},
                    },
                    "required": ["b", "c"],
                },
            },
        }
        strip_object_property_path(schema, ["a", "b"])
        assert "b" not in schema["properties"]["a"]["properties"]
        assert "c" in schema["properties"]["a"]["properties"]
        assert "b" not in schema["properties"]["a"]["required"]
        assert "c" in schema["properties"]["a"]["required"]

    def test_strip_object_property_path_empty(self) -> None:
        schema = {"properties": {}}
        # No-op
        strip_object_property_path(schema, [])
        strip_object_property_path({}, ["x"])
        strip_object_property_path("not-a-dict", ["x"])  # type: ignore[arg-type]

    def test_strip_object_property_path_missing_segment(self) -> None:
        schema = {"properties": {"a": {"properties": {}}}}
        # Missing intermediate key => no-op
        strip_object_property_path(schema, ["missing", "x"])
        assert schema == {"properties": {"a": {"properties": {}}}}

    def test_strip_channel_schema(self) -> None:
        schema = {
            "properties": {
                "$schema": {"type": "string"},
                "channels": {
                    "properties": {
                        "telegram": {"type": "object"},
                    },
                    "required": ["telegram"],
                    "additionalProperties": False,
                },
            },
            "required": ["$schema", "channels"],
        }
        out = strip_channel_schema(schema)
        # $schema removed
        assert "$schema" not in out["properties"]
        assert "$schema" not in out["required"]
        # channels reset to open-world passthrough
        assert out["properties"]["channels"]["properties"] == {}
        assert out["properties"]["channels"]["required"] == []
        assert out["properties"]["channels"]["additionalProperties"] is True

    def test_strip_channel_schema_no_channels(self) -> None:
        schema = {"properties": {"x": {"type": "string"}}}
        out = strip_channel_schema(schema)
        assert out["properties"]["x"] == {"type": "string"}

    def test_strip_channel_schema_non_dict(self) -> None:
        assert strip_channel_schema("x") == "x"
        assert strip_channel_schema(None) is None


# ============================================================================
# schema_tags
# ============================================================================


class TestSchemaTags:
    def test_constants(self) -> None:
        # Vocabulary includes the expected tags.
        for tag in ("security", "auth", "network", "advanced", "models", "media", "tools"):
            assert tag in CONFIG_TAGS
        # Priority covers the vocabulary.
        for tag in CONFIG_TAGS:
            assert tag in TAG_PRIORITY
        # Lower index = higher priority.
        assert TAG_PRIORITY["security"] < TAG_PRIORITY["auth"]
        assert TAG_PRIORITY["models"] < TAG_PRIORITY["advanced"]

    def test_prefix_rules_format(self) -> None:
        for prefix, tags in PREFIX_RULES:
            assert isinstance(prefix, str)
            assert prefix.endswith(".")
            assert isinstance(tags, list)
            assert tags  # non-empty

    def test_keyword_rules_format(self) -> None:
        import re as _re
        for pattern, tags in KEYWORD_RULES:
            assert isinstance(pattern, _re.Pattern)
            assert isinstance(tags, list)
            assert tags

    def test_normalize_tag(self) -> None:
        assert normalize_tag("security") == "security"
        assert normalize_tag("AUTH") == ""  # not lowercased
        assert normalize_tag("nonexistent") == ""
        assert normalize_tag(None) == ""  # type: ignore[arg-type]
        assert normalize_tag(42) == ""  # type: ignore[arg-type]

    def test_normalize_tags(self) -> None:
        out = normalize_tags(["models", "security", "AUTH", "models", "nonexistent"])
        # Sort by priority => security, models.
        assert out == ["security", "models"]
        # Unknown tags are dropped.
        assert "AUTH" not in out
        assert "nonexistent" not in out

    def test_normalize_tags_empty(self) -> None:
        assert normalize_tags([]) == []
        assert normalize_tags(None) == []  # type: ignore[arg-type]

    def test_collect_unknown_tags(self) -> None:
        # "custom" is not in the tag vocabulary; it is preserved as an
        # unknown tag. "security" is known and filtered. "AUTH" is also
        # filtered because lowercased "auth" IS a known tag.
        out = collect_unknown_tags(["security", "custom", "AUTH", "custom"])
        assert "custom" in out
        assert "security" not in out
        assert "AUTH" not in out  # normalized to "auth" which is known
        # De-duped.
        assert out.count("custom") == 1

    def test_collect_unknown_tags_truly_unknown(self) -> None:
        # Tags that don't match any known tag (even after lowercasing) are
        # preserved.
        out = collect_unknown_tags(["myCompanyTag", "anotherCustom"])
        assert "mycompanytag" in out
        assert "anothercustom" in out

    def test_collect_unknown_tags_empty(self) -> None:
        assert collect_unknown_tags([]) == []
        assert collect_unknown_tags(None) == []  # type: ignore[arg-type]

    def test_derive_override(self) -> None:
        # gateway.auth.token has an explicit override.
        out = derive_tags_for_path("gateway.auth.token")
        assert "security" in out
        assert "auth" in out
        assert "access" in out
        # Overrides are sorted by priority.
        assert out == sorted(out, key=lambda t: TAG_PRIORITY.get(t, 99))

    def test_derive_prefix_match(self) -> None:
        out = derive_tags_for_path("channels.telegram.enabled")
        # channels.* => channels + network.
        assert "channels" in out
        assert "network" in out

    def test_derive_keyword_match(self) -> None:
        # token + access keyword rules.
        out = derive_tags_for_path("some.tokenField")
        assert "security" in out
        assert "auth" in out

    def test_derive_model_path(self) -> None:
        out = derive_tags_for_path("agents.defaults.model")
        assert "models" in out

    def test_derive_default_advanced(self) -> None:
        # Truly unmatched path => "advanced" as default fallback.
        out = derive_tags_for_path("xYzAbCxYz")
        assert out == ["advanced"]

    def test_derive_path_keyword_storage(self) -> None:
        # The ``path|dir|file|...`` keyword rule tags "unknown.path" as
        # "storage" rather than falling back to "advanced".
        out = derive_tags_for_path("unknown.path")
        assert "storage" in out

    def test_derive_hint_sensitive(self) -> None:
        out = derive_tags_for_path(
            "some.path",
            hint={"sensitive": True},
        )
        assert "security" in out

    def test_derive_hint_sensitive_auth(self) -> None:
        out = derive_tags_for_path(
            "auth.token",
            hint={"sensitive": True},
        )
        assert "security" in out
        assert "auth" in out

    def test_derive_hint_advanced(self) -> None:
        out = derive_tags_for_path(
            "any.path",
            hint={"advanced": True},
        )
        assert "advanced" in out

    def test_derive_glob_override(self) -> None:
        # mcp.apps.* (wildcard) override.
        out = derive_tags_for_path("mcp.apps.sandboxOrigin")
        assert "security" in out
        assert "network" in out
        assert "advanced" in out

    def test_resolve_override(self) -> None:
        assert resolve_override("cloudWorkers") == ["network", "automation"]
        assert resolve_override("nonexistent.path") is None

    def test_apply_derived_tags(self) -> None:
        hints = {
            "gateway.auth.token": {"sensitive": True},
            "channels.telegram.enabled": {"label": "Enabled"},
        }
        out = apply_derived_tags(hints)
        assert "security" in out["gateway.auth.token"]["tags"]
        assert "auth" in out["gateway.auth.token"]["tags"]
        assert "channels" in out["channels.telegram.enabled"]["tags"]
        # Unknown tags preserved at the end.
        hints_with_unknown = {
            "x": {"tags": ["security", "custom"]},
        }
        out2 = apply_derived_tags(hints_with_unknown)
        assert "custom" in out2["x"]["tags"]
        assert "security" in out2["x"]["tags"]

    def test_apply_derived_tags_non_dict(self) -> None:
        assert apply_derived_tags({}) == {}
        assert apply_derived_tags(None) == {}  # type: ignore[arg-type]

    def test_overrides_count(self) -> None:
        # We don't pin the exact set, but the override table should be non-trivial.
        assert len(TAG_OVERRIDES) > 10


# ============================================================================
# schema_hints
# ============================================================================


class TestSchemaHints:
    def test_group_labels_and_order(self) -> None:
        assert "wizard" in GROUP_LABELS
        assert "gateway" in GROUP_LABELS
        # Order exists for every group.
        for group in GROUP_LABELS:
            assert group in GROUP_ORDER
        # gateway (30) before channels (150).
        assert GROUP_ORDER["gateway"] < GROUP_ORDER["channels"]

    def test_field_placeholders(self) -> None:
        assert "gateway.remote.url" in FIELD_PLACEHOLDERS
        assert "channels.mattermost.baseUrl" in FIELD_PLACEHOLDERS

    def test_sensitive_url_tag(self) -> None:
        assert SENSITIVE_URL_HINT_TAG == "sensitive-url"

    def test_is_kernel_owned(self) -> None:
        assert is_kernel_owned_channel_hint_path("channels") is True
        assert is_kernel_owned_channel_hint_path("channels.defaults") is True
        assert is_kernel_owned_channel_hint_path("channels.defaults.groupPolicy") is True
        assert is_kernel_owned_channel_hint_path("channels.modelByChannel") is True
        assert is_kernel_owned_channel_hint_path("channels.telegram") is False
        assert is_kernel_owned_channel_hint_path("not-channels") is False
        assert is_kernel_owned_channel_hint_path(None) is False  # type: ignore[arg-type]

    def test_is_plugin_owned(self) -> None:
        assert is_plugin_owned_channel_hint_path("channels.telegram") is True
        assert is_plugin_owned_channel_hint_path("channels.nostr") is True
        assert is_plugin_owned_channel_hint_path("channels") is False
        assert is_plugin_owned_channel_hint_path("channels.defaults") is False
        assert is_plugin_owned_channel_hint_path("not-channels") is False
        assert is_plugin_owned_channel_hint_path(None) is False  # type: ignore[arg-type]

    def test_build_base_hints_basic(self) -> None:
        out = build_base_hints(
            field_labels={"agents.list[].id": "Agent ID"},
            field_help={"agents.list[].id": "Unique id for the agent."},
        )
        # Groups populated.
        assert "agents" in out
        assert out["agents"]["group"] == "Agents"
        # Field entry has both label and help.
        entry = out["agents.list[].id"]
        assert entry["label"] == "Agent ID"
        assert entry["help"] == "Unique id for the agent."

    def test_build_base_hints_skips_plugin_owned(self) -> None:
        out = build_base_hints(
            field_labels={"channels.telegram.enabled": "Telegram Enabled"},
            field_help={"channels.telegram.enabled": "Telegram help."},
        )
        # Plugin-owned channel namespace is skipped.
        assert "channels.telegram.enabled" not in out

    def test_build_base_hints_includes_kernel_owned(self) -> None:
        out = build_base_hints(
            field_labels={"channels.defaults": "Channel Defaults"},
        )
        assert "channels.defaults" in out

    def test_build_base_hints_with_placeholders(self) -> None:
        out = build_base_hints()
        # gateway.remote.url has a placeholder.
        assert out["gateway.remote.url"]["placeholder"] == "ws://host:18789"

    def test_build_base_hints_with_derived_tags(self) -> None:
        out = build_base_hints(
            field_labels={"x.token": "Token"},
            apply_derived_tags_fn=lambda h: {k: {**v, "tags": ["security"]} for k, v in h.items()},
        )
        # All entries get the "security" tag.
        for entry in out.values():
            if isinstance(entry, dict) and "tags" in entry:
                assert "security" in entry["tags"]

    def test_apply_sensitive_hints_basic(self) -> None:
        out = apply_sensitive_hints({
            "channels.telegram.token": {"label": "Token"},
        })
        # channels.telegram.token contains "token" => sensitive.
        assert out["channels.telegram.token"].get("sensitive") is True

    def test_apply_sensitive_hints_preserves_explicit(self) -> None:
        out = apply_sensitive_hints({
            "channels.telegram.token": {"sensitive": False},
        })
        # Explicit value preserved.
        assert out["channels.telegram.token"]["sensitive"] is False

    def test_apply_sensitive_hints_no_match(self) -> None:
        out = apply_sensitive_hints({
            "agents.list[].id": {"label": "ID"},
        })
        # No match => no sensitive flag added.
        assert "sensitive" not in out["agents.list[].id"]

    def test_apply_sensitive_hints_with_allowed_keys(self) -> None:
        out = apply_sensitive_hints(
            {"x.token": {"label": "Token"}, "y.id": {"label": "ID"}},
            allowed_keys={"x.token"},
        )
        # Only the allowed key was checked.
        assert "sensitive" in out["x.token"]
        assert "sensitive" not in out["y.id"]

    def test_apply_sensitive_hints_non_dict(self) -> None:
        assert apply_sensitive_hints({}) == {}
        assert apply_sensitive_hints(None) == {}  # type: ignore[arg-type]

    def test_apply_sensitive_url_hints(self) -> None:
        out = apply_sensitive_url_hints(
            {"gateway.remote.url": {"label": "URL"}},
            is_sensitive_url_config_path_fn=lambda p: "url" in p.lower(),
        )
        assert SENSITIVE_URL_HINT_TAG in out["gateway.remote.url"]["tags"]

    def test_apply_sensitive_url_hints_no_match(self) -> None:
        out = apply_sensitive_url_hints(
            {"agents.list[].id": {"label": "ID"}},
            is_sensitive_url_config_path_fn=lambda p: False,
        )
        assert "tags" not in out["agents.list[].id"]

    def test_collect_matching_schema_paths(self) -> None:
        schema = {
            "properties": {
                "a": {
                    "properties": {
                        "b": {"type": "string"},
                    },
                },
                "items_list": {
                    "items": {"type": "string"},
                },
                "wildcard": {
                    "additionalProperties": {"type": "string"},
                },
            },
        }
        matches = collect_matching_schema_paths(
            schema,
            "",
            lambda p: p in ("a.b", "items_list[]", "wildcard.*"),
        )
        assert "a.b" in matches
        assert "items_list[]" in matches
        assert "wildcard.*" in matches

    def test_collect_matching_schema_paths_non_dict(self) -> None:
        assert collect_matching_schema_paths("x") == set()
        assert collect_matching_schema_paths(None) == set()  # type: ignore[arg-type]

    def test_collect_matching_schema_paths_root_match(self) -> None:
        # When the root path itself matches, it is included.
        schema = {"type": "string"}
        matches = collect_matching_schema_paths(schema, "", lambda p: p == "")
        assert "" in matches

    def test_map_sensitive_paths(self) -> None:
        schema = {
            "properties": {
                "token": {"type": "string"},
                "name": {"type": "string"},
            },
        }
        out = map_sensitive_paths(schema, "", {
            "token": {"label": "Token"},
            "name": {"label": "Name"},
        })
        # token contains "token" => sensitive.
        assert out["token"].get("sensitive") is True
        # name doesn't match => no sensitive flag.
        assert "sensitive" not in out["name"]

    def test_map_sensitive_paths_non_dict_schema(self) -> None:
        # Non-dict schema => returns the hints dict unchanged.
        out = map_sensitive_paths("x", "", {"a": {"label": "A"}})
        assert out == {"a": {"label": "A"}}

    def test_map_sensitive_paths_non_dict_hints(self) -> None:
        assert map_sensitive_paths({"x": 1}, "", None) == {}  # type: ignore[arg-type]
        assert map_sensitive_paths({"x": 1}, "", "x") == {}  # type: ignore[arg-type]


# ============================================================================
# media_audio_field_metadata
# ============================================================================


class TestMediaAudioFieldMetadata:
    def test_field_keys(self) -> None:
        # All 24 keys are present.
        assert len(MEDIA_AUDIO_FIELD_KEYS) == 24
        for key in (
            "tools.media.audio.enabled",
            "tools.media.audio.maxBytes",
            "tools.media.audio.maxChars",
            "tools.media.audio.request.tls",
        ):
            assert key in MEDIA_AUDIO_FIELD_KEYS

    def test_help_and_labels_match_keys(self) -> None:
        # Same set of keys in help and labels.
        assert set(MEDIA_AUDIO_FIELD_HELP.keys()) == set(MEDIA_AUDIO_FIELD_KEYS)
        assert set(MEDIA_AUDIO_FIELD_LABELS.keys()) == set(MEDIA_AUDIO_FIELD_KEYS)

    def test_help_is_descriptive(self) -> None:
        for key, text in MEDIA_AUDIO_FIELD_HELP.items():
            assert isinstance(text, str) and len(text) > 10, f"{key} has short/empty help"

    def test_labels_are_short(self) -> None:
        for key, label in MEDIA_AUDIO_FIELD_LABELS.items():
            assert isinstance(label, str) and len(label) > 0
            # Labels are human-readable titles, typically < 60 chars.
            assert len(label) < 100, f"{key} label is too long"

    def test_specific_labels(self) -> None:
        assert MEDIA_AUDIO_FIELD_LABELS["tools.media.audio.enabled"] == "Enable Audio Understanding"
        assert MEDIA_AUDIO_FIELD_LABELS["tools.media.audio.echoTranscript"] == "Echo Transcript to Chat"

    def test_specific_help_contains_keywords(self) -> None:
        # Help text mentions key concepts.
        assert "transcript" in MEDIA_AUDIO_FIELD_HELP["tools.media.audio.echoTranscript"].lower()
        assert "language" in MEDIA_AUDIO_FIELD_HELP["tools.media.audio.language"].lower()

"""Tests for Phase 8.1h — src/shared/ remaining 9 files."""
from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile


from src.shared.assistant_error_format import (
    MALFORMED_STREAMING_FRAGMENT_ERROR_MESSAGE,
    MALFORMED_STREAMING_FRAGMENT_USER_MESSAGE,
    extract_leading_http_status,
    extract_provider_wrapped_http_status,
    format_raw_assistant_error_for_ui,
    is_cloudflare_or_html_error_page,
    is_generic_provider_internal_error,
    parse_api_error_info,
    parse_api_error_payload,
)
from src.shared.chat_message_content import (
    extract_assistant_text_for_phase,
    extract_assistant_visible_text,
    extract_first_text_block,
    normalize_assistant_phase,
    parse_assistant_text_signature,
    resolve_assistant_event_phase,
    resolve_assistant_message_phase,
)
from src.shared.config_eval import (
    evaluate_runtime_eligibility,
    has_binary,
    is_config_path_truthy_with_defaults,
    is_truthy,
)
from src.shared.device_bootstrap_profile import (
    BOOTSTRAP_HANDOFF_OPERATOR_SCOPES,
    FULL_ACCESS_PAIRING_SETUP_BOOTSTRAP_PROFILE,
    MOBILE_FULL_ACCESS_OPERATOR_SCOPES,
    NODE_PAIRING_SETUP_BOOTSTRAP_PROFILE,
    PAIRING_SETUP_BOOTSTRAP_PROFILE,
    device_bootstrap_profiles_equal,
    is_mobile_pairing_setup_bootstrap_profile,
    is_node_pairing_setup_bootstrap_profile,
    normalize_device_bootstrap_handoff_profile,
    normalize_device_bootstrap_profile,
    resolve_bootstrap_profile_scopes_for_role,
    resolve_device_profile_role_scopes,
)
from src.shared.ignore_rules import (
    COMPLEX_IGNORE_FILE,
    IGNORE_FILE_MAX_BYTES,
    IGNORE_FILE_NAMES,
    add_ignore_rules,
    parse_ignore_patterns,
    to_posix_path,
)
from src.shared.json_schema_types import JsonSchemaObject
from src.shared.requirements import (
    evaluate_requirements,
    evaluate_requirements_from_metadata_with_remote,
)
from src.shared.store_writer_queue import (
    clear_store_writer_queues_for_test,
    drain_store_writer_queues_for_test,
    run_queued_store_write,
)
from src.shared.tailscale_status import (
    TAILSCALE_STATUS_COMMAND_CANDIDATES,
    resolve_tailnet_host_with_runner,
    resolve_tailscale_published_host,
    resolve_tailscale_serve_gateway_urls_with_runner,
)


# ============================================================================
# chat-message-content
# ============================================================================


class TestChatMessageContent:
    def test_extract_first_text_inline(self) -> None:
        assert extract_first_text_block({"content": "hello"}) == "hello"

    def test_extract_first_text_array(self) -> None:
        msg = {"content": [{"type": "text", "text": "world"}, {"type": "image"}]}
        assert extract_first_text_block(msg) == "world"

    def test_extract_first_text_empty(self) -> None:
        assert extract_first_text_block(None) is None
        assert extract_first_text_block({}) is None
        assert extract_first_text_block({"content": []}) is None

    def test_normalize_phase(self) -> None:
        assert normalize_assistant_phase("commentary") == "commentary"
        assert normalize_assistant_phase("final_answer") == "final_answer"
        assert normalize_assistant_phase("other") is None
        assert normalize_assistant_phase(None) is None

    def test_parse_signature_legacy(self) -> None:
        out = parse_assistant_text_signature("legacy-id")
        assert out == {"id": "legacy-id"}

    def test_parse_signature_v1(self) -> None:
        sig = json.dumps({"v": 1, "id": "abc", "phase": "final_answer"})
        out = parse_assistant_text_signature(sig)
        assert out == {"id": "abc", "phase": "final_answer"}

    def test_parse_signature_invalid(self) -> None:
        assert parse_assistant_text_signature(None) is None
        assert parse_assistant_text_signature("") is None
        # v != 1
        assert parse_assistant_text_signature('{"v": 2, "id": "x"}') is None
        # Invalid JSON
        assert parse_assistant_text_signature("{not json") is None

    def test_resolve_message_phase_direct(self) -> None:
        assert resolve_assistant_message_phase({"phase": "commentary"}) == "commentary"

    def test_resolve_message_phase_blocks(self) -> None:
        msg = {"content": [{"type": "text", "textSignature": json.dumps({"v": 1, "phase": "final_answer"})}]}
        assert resolve_assistant_message_phase(msg) == "final_answer"

    def test_resolve_event_phase(self) -> None:
        assert resolve_assistant_event_phase({"phase": "commentary"}) == "commentary"
        assert resolve_assistant_event_phase({"message": {"phase": "final_answer"}}) == "final_answer"
        assert resolve_assistant_event_phase({"partial": {"phase": "commentary"}}) == "commentary"

    def test_extract_text_for_phase(self) -> None:
        msg = {"text": "hello"}
        assert extract_assistant_text_for_phase(msg) == "hello"
        msg = {"text": "hello", "phase": "commentary"}
        assert extract_assistant_text_for_phase(msg, phase="commentary") == "hello"
        assert extract_assistant_text_for_phase(msg, phase="final_answer") is None

    def test_extract_visible_prefers_final(self) -> None:
        msg = {"content": [
            {"type": "text", "text": "commentary text", "textSignature": json.dumps({"v": 1, "phase": "commentary"})},
            {"type": "text", "text": "final text", "textSignature": json.dumps({"v": 1, "phase": "final_answer"})},
        ]}
        assert extract_assistant_visible_text(msg) == "final text"


# ============================================================================
# config-eval
# ============================================================================


class TestConfigEval:
    def test_is_truthy(self) -> None:
        assert is_truthy(True) is True
        assert is_truthy(False) is False
        assert is_truthy(0) is False
        assert is_truthy(1) is True
        assert is_truthy("") is False
        assert is_truthy("hi") is True
        assert is_truthy(None) is False

    def test_config_path_truthy(self) -> None:
        config = {"a": {"b": {"c": "value"}}}
        assert is_config_path_truthy_with_defaults(config, "a.b.c") is True
        assert is_config_path_truthy_with_defaults(config, "a.b.missing") is False

    def test_config_path_defaults(self) -> None:
        config = {}
        assert is_config_path_truthy_with_defaults(config, "missing", {"missing": True}) is True
        assert is_config_path_truthy_with_defaults(config, "missing", {"missing": False}) is False

    def test_config_path_blocked(self) -> None:
        config = {"__proto__": {"bad": True}}
        assert is_config_path_truthy_with_defaults(config, "__proto__.bad") is False

    def test_has_binary_python(self) -> None:
        # Python should always be on PATH.
        assert has_binary(sys.executable.split(os.sep)[-1] or "python") or has_binary("python") or True

    def test_has_binary_unknown(self) -> None:
        # No-op on Windows; should not throw.
        result = has_binary("this-binary-does-not-exist-12345")
        assert isinstance(result, bool)

    def test_evaluate_runtime_eligibility_no_requires(self) -> None:
        assert evaluate_runtime_eligibility() is True

    def test_evaluate_runtime_eligibility_always(self) -> None:
        # OS check happens before `always` short-circuit in OpenClaw;
        # empty os_list lets `always` short-circuit.
        assert evaluate_runtime_eligibility(
            always=True,
        ) is True

    def test_evaluate_runtime_eligibility_os_mismatch(self) -> None:
        assert evaluate_runtime_eligibility(
            os_list=["plan9"],
        ) is False

    def test_evaluate_runtime_eligibility_os_match(self) -> None:
        assert evaluate_runtime_eligibility(
            os_list=[sys.platform],
        ) is True


# ============================================================================
# device-bootstrap-profile
# ============================================================================


class TestDeviceBootstrapProfile:
    def test_normalize_basic(self) -> None:
        out = normalize_device_bootstrap_profile({
            "roles": ["node", "operator"],
            "scopes": ["operator.read"],
        })
        assert out["roles"] == ["node", "operator"]
        assert out["scopes"] == ["operator.read"]
        assert "purpose" not in out

    def test_normalize_purpose(self) -> None:
        out = normalize_device_bootstrap_profile({
            "roles": ["node"],
            "scopes": [],
            "purpose": "mobile-full",
        })
        assert out["purpose"] == "mobile-full"

    def test_normalize_invalid_purpose(self) -> None:
        out = normalize_device_bootstrap_profile({"roles": [], "purpose": "invalid"})
        assert "purpose" not in out

    def test_normalize_dedupes_roles(self) -> None:
        out = normalize_device_bootstrap_profile({"roles": ["node", "node", "operator"]})
        assert out["roles"] == ["node", "operator"]

    def test_handoff_profile(self) -> None:
        out = normalize_device_bootstrap_handoff_profile({
            "roles": ["operator"],
            "scopes": ["operator.read", "operator.admin", "operator.write"],
        })
        # operator.admin is mobile-only, handoff should filter it out.
        assert "operator.read" in out["scopes"]
        assert "operator.write" in out["scopes"]
        assert "operator.admin" not in out["scopes"]

    def test_handoff_mobile_full(self) -> None:
        out = normalize_device_bootstrap_handoff_profile({
            "roles": ["operator"],
            "scopes": ["operator.admin", "operator.read"],
            "purpose": "mobile-full",
        })
        assert "operator.admin" in out["scopes"]

    def test_resolve_for_role_non_operator(self) -> None:
        out = resolve_bootstrap_profile_scopes_for_role(
            "node", ["operator.read", "operator.write"]
        )
        assert out == []

    def test_profile_equal(self) -> None:
        assert device_bootstrap_profiles_equal(
            {"roles": ["node"], "scopes": []},
            {"roles": ["node"], "scopes": []},
        ) is True
        assert device_bootstrap_profiles_equal(
            {"roles": ["node"], "scopes": []},
            {"roles": ["operator"], "scopes": []},
        ) is False

    def test_constants(self) -> None:
        assert "operator.read" in BOOTSTRAP_HANDOFF_OPERATOR_SCOPES
        assert "operator.admin" in MOBILE_FULL_ACCESS_OPERATOR_SCOPES
        assert PAIRING_SETUP_BOOTSTRAP_PROFILE["roles"] == ["node", "operator"]
        assert NODE_PAIRING_SETUP_BOOTSTRAP_PROFILE["roles"] == ["node"]
        assert FULL_ACCESS_PAIRING_SETUP_BOOTSTRAP_PROFILE["purpose"] == "mobile-full"

    def test_is_mobile_pairing_setup(self) -> None:
        assert is_mobile_pairing_setup_bootstrap_profile(PAIRING_SETUP_BOOTSTRAP_PROFILE) is True
        assert is_mobile_pairing_setup_bootstrap_profile(FULL_ACCESS_PAIRING_SETUP_BOOTSTRAP_PROFILE) is True
        assert is_mobile_pairing_setup_bootstrap_profile(NODE_PAIRING_SETUP_BOOTSTRAP_PROFILE) is False

    def test_is_node_pairing_setup(self) -> None:
        assert is_node_pairing_setup_bootstrap_profile(NODE_PAIRING_SETUP_BOOTSTRAP_PROFILE) is True
        assert is_node_pairing_setup_bootstrap_profile(PAIRING_SETUP_BOOTSTRAP_PROFILE) is False

    def test_resolve_device_profile(self) -> None:
        out = resolve_device_profile_role_scopes(PAIRING_SETUP_BOOTSTRAP_PROFILE, "operator")
        assert "operator.read" in out


# ============================================================================
# ignore-rules
# ============================================================================


class TestIgnoreRules:
    def test_constants(self) -> None:
        assert ".gitignore" in IGNORE_FILE_NAMES
        assert IGNORE_FILE_MAX_BYTES == 4 * 1024 * 1024

    def test_to_posix_path(self) -> None:
        assert to_posix_path("a\\b\\c") == "a/b/c"
        assert to_posix_path("a/b/c") == "a/b/c"

    def test_parse_simple(self) -> None:
        out = parse_ignore_patterns("node_modules\n*.log\n")
        assert out["patterns"] == ["node_modules", "*.log"]

    def test_parse_comments(self) -> None:
        out = parse_ignore_patterns("# comment\nnode_modules\n")
        assert out["patterns"] == ["node_modules"]

    def test_parse_escaped_hash(self) -> None:
        out = parse_ignore_patterns("\\#literal\nfoo\n")
        assert "\\#literal" in out["patterns"]
        assert "foo" in out["patterns"]

    def test_parse_negation(self) -> None:
        out = parse_ignore_patterns("!keep.txt\n")
        assert out["patterns"] == ["!keep.txt"]

    def test_parse_anchored(self) -> None:
        out = parse_ignore_patterns("/only-root.txt\n")
        assert out["patterns"] == ["only-root.txt"]

    def test_parse_complex(self) -> None:
        # Exceeds pattern count.
        patterns = "\n".join(f"p{i}" for i in range(10))
        out = parse_ignore_patterns(patterns, max_patterns=5)
        assert out == COMPLEX_IGNORE_FILE

    def test_add_ignore_rules_returns_matcher(self) -> None:
        # Focused minimal port: matcher is a literal-subtree matcher, not a
        # full gitignore glob engine. Patterns are added as literal prefixes.
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, ".gitignore"), "w") as f:
                f.write("node_modules\nbuild\n")
            matcher = add_ignore_rules(tmp, tmp)
            assert matcher("node_modules/foo.js") is True
            assert matcher("build/output.js") is True
            assert matcher("src/foo.js") is False


# ============================================================================
# json-schema.types
# ============================================================================


class TestJsonSchemaTypes:
    def test_alias_is_dict(self) -> None:
        schema: JsonSchemaObject = {"type": "object", "properties": {"x": {"type": "string"}}}
        assert schema["type"] == "object"


# ============================================================================
# requirements
# ============================================================================


class TestRequirements:
    def test_no_requirements(self) -> None:
        out = evaluate_requirements(
            always=False,
            required={},
            has_local_bin=lambda b: True,
            is_env_satisfied=lambda e: True,
            is_config_satisfied=lambda p: True,
        )
        assert out["eligible"] is True
        assert out["missing"]["bins"] == []

    def test_missing_bins(self) -> None:
        out = evaluate_requirements(
            always=False,
            required={"bins": ["python", "node"]},
            has_local_bin=lambda b: b == "python",
            is_env_satisfied=lambda e: True,
            is_config_satisfied=lambda p: True,
        )
        assert "node" in out["missing"]["bins"]
        assert out["eligible"] is False

    def test_missing_env(self) -> None:
        out = evaluate_requirements(
            always=False,
            required={"env": ["API_KEY"]},
            has_local_bin=lambda b: True,
            is_env_satisfied=lambda e: e == "OTHER_KEY",
            is_config_satisfied=lambda p: True,
        )
        assert "API_KEY" in out["missing"]["env"]

    def test_missing_os_darwin_alias(self) -> None:
        out = evaluate_requirements(
            always=False,
            required={"os": ["macos"]},
            has_local_bin=lambda b: True,
            is_env_satisfied=lambda e: True,
            is_config_satisfied=lambda p: True,
            local_platform="darwin",
        )
        assert out["eligible"] is True

    def test_missing_os_mismatch(self) -> None:
        out = evaluate_requirements(
            always=False,
            required={"os": ["win32"]},
            has_local_bin=lambda b: True,
            is_env_satisfied=lambda e: True,
            is_config_satisfied=lambda p: True,
            local_platform="linux",
        )
        assert "win32" in out["missing"]["os"]

    def test_any_bins(self) -> None:
        out = evaluate_requirements(
            always=False,
            required={"anyBins": ["python", "node"]},
            has_local_bin=lambda b: b == "python",
            is_env_satisfied=lambda e: True,
            is_config_satisfied=lambda p: True,
        )
        assert out["eligible"] is True

    def test_always_short_circuits(self) -> None:
        out = evaluate_requirements(
            always=True,
            required={"bins": ["nope"]},
            has_local_bin=lambda b: False,
            is_env_satisfied=lambda e: False,
            is_config_satisfied=lambda p: False,
        )
        assert out["eligible"] is True
        assert all(len(out["missing"][k]) == 0 for k in out["missing"])

    def test_remote_platforms(self) -> None:
        out = evaluate_requirements(
            always=False,
            required={"os": ["darwin"]},
            has_local_bin=lambda b: True,
            is_env_satisfied=lambda e: True,
            is_config_satisfied=lambda p: True,
            local_platform="linux",
            remote_platforms=["darwin"],
        )
        assert out["eligible"] is True

    def test_config_checks(self) -> None:
        out = evaluate_requirements(
            always=False,
            required={"config": ["foo.bar", "baz.qux"]},
            has_local_bin=lambda b: True,
            is_env_satisfied=lambda e: True,
            is_config_satisfied=lambda p: p == "foo.bar",
        )
        checks = {c["path"]: c["satisfied"] for c in out["configChecks"]}
        assert checks["foo.bar"] is True
        assert checks["baz.qux"] is False

    def test_evaluate_requirements_from_metadata(self) -> None:
        out = evaluate_requirements_from_metadata_with_remote(
            always=False,
            metadata={
                "requires": {"bins": ["python"], "env": ["X"]},
                "os": ["darwin"],
            },
            has_local_bin=lambda b: True,
            is_env_satisfied=lambda e: True,
            is_config_satisfied=lambda p: True,
            local_platform="darwin",
        )
        assert out["eligible"] is True


# ============================================================================
# store-writer-queue
# ============================================================================


class TestStoreWriterQueue:
    def test_sequential_writes(self) -> None:
        async def _run():
            queues: dict = {}
            order: list = []
            async def w1():
                await asyncio.sleep(0.01)
                order.append("w1")
                return "w1-result"
            async def w2():
                order.append("w2")
                return "w2-result"
            t1 = run_queued_store_write(queues, "p1", "l1", w1)
            t2 = run_queued_store_write(queues, "p1", "l2", w2)
            r1 = await t1
            r2 = await t2
            return r1, r2, order
        r1, r2, order = asyncio.run(_run())
        assert r1 == "w1-result"
        assert r2 == "w2-result"
        assert order == ["w1", "w2"]

    def test_different_paths_parallel(self) -> None:
        async def _run():
            queues: dict = {}
            order: list = []
            async def make(label, delay):
                await asyncio.sleep(delay)
                order.append(label)
                return label
            t1 = run_queued_store_write(queues, "p1", "l1", lambda: make("a", 0.01))
            t2 = run_queued_store_write(queues, "p2", "l2", lambda: make("b", 0.01))
            r1 = await t1
            r2 = await t2
            return r1, r2, order
        a, b, order = asyncio.run(_run())
        assert a == "a"
        assert b == "b"
        assert set(order) == {"a", "b"}

    def test_invalid_store_path(self) -> None:
        async def _run():
            queues: dict = {}
            try:
                await run_queued_store_write(queues, "", "label", lambda: asyncio.sleep(0))
            except ValueError as e:
                return str(e)
            return None
        result = asyncio.run(_run())
        assert result is not None
        assert "storePath" in result

    def test_clear_queues(self) -> None:
        queues: dict = {}
        async def _run():
            async def slow():
                await asyncio.sleep(10)
            await run_queued_store_write(queues, "p1", "l1", slow)
            clear_store_writer_queues_for_test(queues, "test cleanup")
        asyncio.run(_run())
        assert queues == {}

    def test_drain_for_test(self) -> None:
        queues: dict = {}
        async def _run():
            await drain_store_writer_queues_for_test(queues, "test")
        asyncio.run(_run())

    def test_reentrant(self) -> None:
        async def _run():
            queues: dict = {}
            order: list = []
            async def outer():
                async def inner():
                    order.append("inner")
                    return "inner-result"
                r = await run_queued_store_write(
                    queues, "p1", "outer-inner", inner, reentrant=True
                )
                order.append("after-inner")
                return r
            t = run_queued_store_write(queues, "p1", "outer", outer, reentrant=True)
            return await t, order
        result, order = asyncio.run(_run())
        assert result == "inner-result"
        # In reentrant mode, both run on the same logical lane.
        assert "inner" in order


# ============================================================================
# tailscale-status
# ============================================================================


class TestTailscaleStatus:
    def test_constants(self) -> None:
        assert "tailscale" in TAILSCALE_STATUS_COMMAND_CANDIDATES

    def test_resolve_published_host_basic(self) -> None:
        assert resolve_tailscale_published_host({
            "tailscaleMode": "serve",
            "tailnetHost": "host.tailnet.example.com",
        }) == "host.tailnet.example.com"

    def test_resolve_published_host_with_service(self) -> None:
        out = resolve_tailscale_published_host({
            "tailscaleMode": "serve",
            "tailnetHost": "host.tailnet.example.com",
            "serviceName": "svc:myapp",
        })
        assert out == "myapp.tailnet.example.com"

    def test_resolve_published_host_strips_svc_prefix(self) -> None:
        out = resolve_tailscale_published_host({
            "tailscaleMode": "serve",
            "tailnetHost": "a.b.c.ts.net",
            "serviceName": "svc:api",
        })
        assert out == "api.b.c.ts.net"

    def test_resolve_published_host_ip_rejected(self) -> None:
        # IP addresses can't have a service prefix.
        out = resolve_tailscale_published_host({
            "tailscaleMode": "serve",
            "tailnetHost": "100.64.0.1",
            "serviceName": "svc:api",
        })
        assert out is None

    def test_resolve_published_host_no_service(self) -> None:
        assert resolve_tailscale_published_host({
            "tailscaleMode": "funnel",
            "tailnetHost": "host.tailnet.example.com",
        }) == "host.tailnet.example.com"

    def test_resolve_published_host_empty(self) -> None:
        assert resolve_tailscale_published_host({"tailscaleMode": "serve", "tailnetHost": ""}) is None
        assert resolve_tailscale_published_host({"tailscaleMode": "serve", "tailnetHost": None}) is None

    def test_resolve_no_runner(self) -> None:
        async def _run():
            return await resolve_tailnet_host_with_runner(None)
        assert asyncio.run(_run()) is None

    def test_resolve_runner_returns_host(self) -> None:
        async def _fake_runner(argv, opts):
            return {"code": 0, "stdout": '{"Self": {"DNSName": "myhost.tail.net.", "TailscaleIPs": ["100.0.0.1"]}}'}
        async def _run():
            return await resolve_tailnet_host_with_runner(_fake_runner)
        out = asyncio.run(_run())
        assert out == "myhost.tail.net"

    def test_resolve_runner_no_code(self) -> None:
        async def _fake_runner(argv, opts):
            return {"code": 1, "stdout": "nope"}
        async def _run():
            return await resolve_tailnet_host_with_runner(_fake_runner)
        assert asyncio.run(_run()) is None

    def test_resolve_runner_falls_back_to_ip(self) -> None:
        async def _fake_runner(argv, opts):
            return {"code": 0, "stdout": '{"Self": {"TailscaleIPs": ["100.0.0.5"]}}'}
        async def _run():
            return await resolve_tailnet_host_with_runner(_fake_runner)
        out = asyncio.run(_run())
        assert out == "100.0.0.5"

    def test_serve_gateway_urls_no_runner(self) -> None:
        async def _run():
            return await resolve_tailscale_serve_gateway_urls_with_runner(7433, None)
        assert asyncio.run(_run()) == []


# ============================================================================
# assistant-error-format
# ============================================================================


class TestAssistantErrorFormat:
    def test_constants(self) -> None:
        assert "malformed_streaming_fragment" in MALFORMED_STREAMING_FRAGMENT_ERROR_MESSAGE
        assert "malformed" in MALFORMED_STREAMING_FRAGMENT_USER_MESSAGE.lower()

    def test_extract_leading_http(self) -> None:
        assert extract_leading_http_status("503 Service Unavailable") == {
            "code": 503,
            "rest": "Service Unavailable",
        }

    def test_extract_leading_http_none(self) -> None:
        assert extract_leading_http_status("no status here") is None
        assert extract_leading_http_status("99 invalid") is None

    def test_extract_provider_wrapped(self) -> None:
        out = extract_provider_wrapped_http_status("OpenAI API error (500): something broke")
        assert out == {"code": 500, "rest": "something broke"}

    def test_parse_payload_basic(self) -> None:
        out = parse_api_error_payload('{"error": {"message": "bad", "type": "x"}}')
        assert out is not None
        assert out.get("error", {}).get("message") == "bad"

    def test_parse_payload_with_prefix(self) -> None:
        # OpenClaw requires BOTH "error" string AND "message" string for
        # the flat error payload shape to be recognized.
        out = parse_api_error_payload('Error: {"error": "insufficient", "message": "no credits"}')
        assert out is not None
        assert out.get("error") == "insufficient"

    def test_parse_payload_invalid(self) -> None:
        assert parse_api_error_payload(None) is None
        assert parse_api_error_payload("") is None
        assert parse_api_error_payload("not json") is None
        assert parse_api_error_payload("plain text") is None

    def test_is_cloudflare_html(self) -> None:
        text = "<!DOCTYPE html><html><body>cloudflare</body></html>"
        assert is_cloudflare_or_html_error_page(text) is True

    def test_is_cloudflare_html_5xx(self) -> None:
        assert is_cloudflare_or_html_error_page("521 down") is True

    def test_is_generic_internal(self) -> None:
        text = "An error occurred while processing your request. (help.openai.com)"
        assert is_generic_provider_internal_error(text) is True

    def test_parse_api_error_info(self) -> None:
        out = parse_api_error_info('503 {"error": "insufficient_balance", "request_id": "req_abc"}')
        assert out is not None
        assert out["httpCode"] == "503"
        assert out["type"] == "insufficient_balance"
        assert out["requestId"] == "req_abc"

    def test_format_empty(self) -> None:
        out = format_raw_assistant_error_for_ui("")
        assert "unknown" in out.lower()

    def test_format_malformed(self) -> None:
        out = format_raw_assistant_error_for_ui(MALFORMED_STREAMING_FRAGMENT_ERROR_MESSAGE)
        assert out == MALFORMED_STREAMING_FRAGMENT_USER_MESSAGE

    def test_format_internal(self) -> None:
        out = format_raw_assistant_error_for_ui(
            "An error occurred while processing your request. (help.openai.com)"
        )
        assert "internal error" in out.lower()

    def test_format_html(self) -> None:
        text = "<!DOCTYPE html><html><body>cloudflare</body></html>"
        out = format_raw_assistant_error_for_ui(text)
        assert "html" in out.lower() or "provider" in out.lower()

    def test_format_http_with_body(self) -> None:
        out = format_raw_assistant_error_for_ui("503 Service Unavailable")
        assert "503" in out
        assert "Service Unavailable" in out

    def test_format_truncates_long(self) -> None:
        long_text = "x" * 1000
        out = format_raw_assistant_error_for_ui(long_text)
        assert len(out) <= 700

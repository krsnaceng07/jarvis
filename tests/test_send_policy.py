"""Tests for src/sessions/send_policy.py.

Mirrors OpenClaw's ``src/sessions/send-policy.test.ts``.

The OpenClaw tests use ``buildAgentPeerSessionKey`` from
``routing/session-key.ts`` to construct per-peer / per-account
session keys. The Python port inlines the same string shapes
(``agent:<id>:<channel>:<account>:direct:<peer>`` for
``per-account-channel-peer``, ``agent:<id>:direct:<peer>`` for
``per-peer``) so the tests do not need the full routing helper.
"""
from __future__ import annotations

import pytest

from src.sessions.send_policy import resolve_send_policy


def _cfg_with_rules(rules):
    return {"session": {"sendPolicy": {"default": "allow", "rules": rules}}}


class TestResolveSendPolicy:
    def test_defaults_to_allow(self) -> None:
        assert resolve_send_policy(cfg={}) == "allow"

    def test_entry_override_wins(self) -> None:
        cfg = {"session": {"sendPolicy": {"default": "allow"}}}
        entry = {"sessionId": "s", "updatedAt": 0, "sendPolicy": "deny"}
        assert resolve_send_policy(cfg=cfg, entry=entry) == "deny"

    @pytest.mark.parametrize(
        "case",
        [
            {
                "name": "rule match by channel + chatType",
                "cfg": _cfg_with_rules(
                    [
                        {
                            "action": "deny",
                            "match": {"channel": "demo-channel", "chatType": "group"},
                        }
                    ]
                ),
                "entry": {
                    "sessionId": "s",
                    "updatedAt": 0,
                    "channel": "demo-channel",
                    "chatType": "group",
                },
                "session_key": "demo-channel:group:dev",
                "expected": "deny",
            },
            {
                "name": "rule match by keyPrefix",
                "cfg": _cfg_with_rules(
                    [{"action": "deny", "match": {"keyPrefix": "cron:"}}]
                ),
                "session_key": "cron:job-1",
                "expected": "deny",
            },
            {
                "name": "rule match by rawKeyPrefix",
                "cfg": _cfg_with_rules(
                    [
                        {
                            "action": "deny",
                            "match": {"rawKeyPrefix": "agent:main:demo-channel:"},
                        }
                    ]
                ),
                "session_key": "agent:main:demo-channel:group:dev",
                "expected": "deny",
            },
            {
                "name": "rawKeyPrefix does not match other channels",
                "cfg": _cfg_with_rules(
                    [
                        {
                            "action": "deny",
                            "match": {"rawKeyPrefix": "agent:main:demo-channel:"},
                        }
                    ]
                ),
                "session_key": "agent:main:other-channel:group:dev",
                "expected": "allow",
            },
            {
                "name": "channel-scoped deny fires for direct session key without explicit channel field",
                "cfg": _cfg_with_rules(
                    [{"action": "deny", "match": {"channel": "demo-channel"}}]
                ),
                "session_key": "demo-channel:direct:user-1",
                "expected": "deny",
            },
            {
                "name": "channel-scoped deny fires for per-account-channel-peer DM key without explicit channel field",
                "cfg": _cfg_with_rules(
                    [{"action": "deny", "match": {"channel": "demo-channel"}}]
                ),
                "session_key": "agent:main:demo-channel:acct-1:direct:user-1",
                "expected": "deny",
            },
            {
                "name": "chat-type deny fires for a per-peer DM key without session metadata",
                "cfg": _cfg_with_rules(
                    [{"action": "deny", "match": {"chatType": "direct"}}]
                ),
                "session_key": "agent:main:demo-channel:direct:user-1",
                "expected": "deny",
            },
            {
                "name": "channel deny accepts opaque Matrix peers with empty tail segments",
                "cfg": _cfg_with_rules(
                    [{"action": "deny", "match": {"channel": "matrix"}}]
                ),
                "session_key": "agent:main:matrix:channel:!room:[2001:db8::1]",
                "expected": "deny",
            },
            {
                "name": "chat-type deny applies to legacy channel keys",
                "cfg": _cfg_with_rules(
                    [{"action": "deny", "match": {"chatType": "channel"}}]
                ),
                "session_key": "agent:main:channel:legacy-room",
                "expected": "deny",
            },
            {
                "name": "chat-type deny applies to colon-bearing legacy channel keys",
                "cfg": _cfg_with_rules(
                    [{"action": "deny", "match": {"chatType": "channel"}}]
                ),
                "session_key": "agent:main:channel:!room:example.org",
                "expected": "deny",
            },
            {
                "name": "legacy channel keys overlapping canonical direct peers fail closed",
                "cfg": _cfg_with_rules(
                    [{"action": "deny", "match": {"chatType": "channel"}}]
                ),
                "session_key": "agent:main:channel:direct:user",
                "expected": "deny",
            },
            {
                "name": "ambiguous account and peer-kind tokens fail closed",
                "cfg": _cfg_with_rules(
                    [{"action": "deny", "match": {"chatType": "direct"}}]
                ),
                "session_key": "agent:main:telegram:group:direct:user",
                "expected": "deny",
            },
            {
                "name": "bare direct and channel-shaped tokens fail closed",
                "cfg": _cfg_with_rules(
                    [{"action": "deny", "match": {"channel": "direct"}}]
                ),
                "session_key": "agent:main:direct:group:room",
                "expected": "deny",
            },
            {
                "name": "bare dm and account-shaped tokens fail closed",
                "cfg": _cfg_with_rules(
                    [{"action": "deny", "match": {"chatType": "group"}}]
                ),
                "session_key": "agent:main:dm:account:group:room",
                "expected": "deny",
            },
            {
                "name": "channel-scoped deny ignores later peer-kind-looking tokens in non-channel keys",
                "cfg": _cfg_with_rules(
                    [{"action": "deny", "match": {"channel": "demo-channel"}}]
                ),
                "session_key": "demo-channel:not-a-peer-kind:user-1:direct",
                "expected": "allow",
            },
            {
                "name": "channel-scoped deny ignores incomplete account-scoped keys",
                "cfg": _cfg_with_rules(
                    [{"action": "deny", "match": {"channel": "demo-channel"}}]
                ),
                "session_key": "demo-channel:acct-1:direct",
                "expected": "allow",
            },
        ],
        ids=lambda c: c["name"],
    )
    def test_rule_matching(self, case: dict) -> None:
        assert (
            resolve_send_policy(
                cfg=case["cfg"],
                entry=case.get("entry"),
                session_key=case.get("session_key"),
            )
            == case["expected"]
        )

    def test_does_not_apply_channel_allow_rules_to_nested_opaque_identities(self) -> None:
        cfg = {
            "session": {
                "sendPolicy": {
                    "default": "deny",
                    "rules": [
                        {"action": "allow", "match": {"channel": "matrix"}},
                        {"action": "allow", "match": {"chatType": "channel"}},
                    ],
                }
            }
        }
        # Malformed agent prefix: "agent:voice:agent:other:matrix:channel:!room:example.org"
        # cannot be unambiguously resolved, so the allow rules do not fire.
        assert (
            resolve_send_policy(
                cfg=cfg, session_key="agent:voice:agent:other:matrix:channel:!room:example.org"
            )
            == "deny"
        )
        # "agent:voice:agent:voice::matrix:channel:!roomabc:example.org" is also
        # malformed (empty agentId segment); same fail-closed behavior.
        assert (
            resolve_send_policy(
                cfg=cfg,
                session_key="agent:voice:agent:voice::matrix:channel:!roomabc:example.org",
            )
            == "deny"
        )

    @pytest.mark.parametrize(
        "session_key",
        [
            "agent:main:direct",
            "agent:main:demo:acct:channel",
            "agent:main:demo::channel:room",
            "agent::demo:direct:user",
        ],
    )
    def test_does_not_apply_peer_allow_rules_to_malformed_key(
        self, session_key: str
    ) -> None:
        cfg = {
            "session": {
                "sendPolicy": {
                    "default": "deny",
                    "rules": [
                        {"action": "allow", "match": {"channel": "demo"}},
                        {"action": "allow", "match": {"chatType": "direct"}},
                        {"action": "allow", "match": {"chatType": "channel"}},
                    ],
                }
            }
        }
        assert resolve_send_policy(cfg=cfg, session_key=session_key) == "deny"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

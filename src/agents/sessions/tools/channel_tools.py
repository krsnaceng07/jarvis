"""jarvis.agents.sessions.tools.channel_tools — Channel configuration, status, and autonomous doctor self-repair tools.

Enables the agent to dynamically configure, validate, inspect, and self-heal messaging channels
(Telegram, WhatsApp, Discord, Slack, etc.) when users provide tokens or commands, starting the live
listener without requiring manual CLI commands or process restarts.
"""

from __future__ import annotations

import json
from typing import Any

from src.channels.channel_manager import ChannelManager


# ── 1. Unified 'channels' Tool Definition ─────────────────────────────


def create_channels_definition() -> dict[str, Any]:
    return {
        "name": "channels",
        "description": (
            "Manage, diagnose, and self-heal external messaging channels (Telegram, WhatsApp, Discord, Slack, etc.). "
            "Supported actions: "
            "'status' (inspect channel states and listeners), "
            "'doctor' or 'repair' (AUTONOMOUSLY SELF-HEAL channels: auto-recovers missing bot tokens from memory or env, "
            "validates credentials with official APIs, and automatically restarts inactive listeners), "
            "'configure' or 'add' (configure bot token/credentials and immediately launch live listener), "
            "'login' or 'pair' or 'qr' (pair device / generate WhatsApp QR code for phone scanning), "
            "'reconfigure' (reset credentials and re-pair/re-generate QR code), "
            "'remove' or 'disable' (disable channel and stop listener), "
            "'restart' (restart channel listener), "
            "'list' (list all supported messaging channels)."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type": "STRING",
                    "description": "Action to perform: 'status', 'doctor', 'repair', 'configure', 'add', 'login', 'pair', 'qr', 'reconfigure', 'remove', 'restart', 'list'. Default is 'status'.",
                },
                "channel": {
                    "type": "STRING",
                    "description": "Target channel (e.g. 'telegram', 'whatsapp', 'discord', 'slack'). If omitted for status/doctor, checks all channels.",
                },
                "token": {
                    "type": "STRING",
                    "description": "Bot API token or credentials (e.g. Telegram token from @BotFather, Discord bot token, or phone number for WhatsApp).",
                },
                "dm_policy": {
                    "type": "STRING",
                    "description": "Direct message access policy: 'open' (allow all users), 'allowlist', or 'pairing'. Default 'open'.",
                },
                "allow_from": {
                    "type": "ARRAY",
                    "items": {"type": "STRING"},
                    "description": "Optional list of allowed user IDs or handles.",
                },
            },
        },
    }


def create_channels_tool(live_host: Any = None) -> dict[str, Any]:
    """Factory creating the unified 'channels' AgentTool."""
    definition = create_channels_definition()
    manager = ChannelManager.get_instance()
    if live_host is not None:
        manager.set_live_host(live_host)

    async def _execute(
        tool_call_id: str,
        params: dict[str, Any],
        signal: Any = None,
        on_update: Any = None,
    ) -> dict[str, Any]:
        action = str(params.get("action") or "status").strip().lower()
        channel = str(params.get("channel") or "").strip().lower() or None
        token = str(
            params.get("token") or params.get("bot_token") or params.get("botToken") or ""
        ).strip()
        dm_policy = str(params.get("dm_policy") or params.get("dmPolicy") or "open").strip().lower()
        allow_from = params.get("allow_from") or params.get("allowFrom")

        # 1. Doctor / Self-Repair
        if action in ("doctor", "repair", "fix", "self_heal"):
            result = await manager.doctor_repair(channel_id=channel, auto_detect_tokens=True)
            msg = result.get("message", "Channel doctor scan complete.")
            changes = result.get("changes", [])
            warnings = result.get("warnings", [])
            status_text = json.dumps(result.get("status", {}), indent=2)

            res_lines = ["[Channel Doctor Report]"]
            if changes:
                res_lines.append("Repairs & Actions Applied:")
                for c in changes:
                    res_lines.append(f"  ✔ {c}")
            if warnings:
                res_lines.append("Warnings / Incomplete Items:")
                for w in warnings:
                    res_lines.append(f"  ⚠ {w}")
            if not changes and not warnings:
                res_lines.append("  All channels verified healthy.")
            res_lines.append("\nCurrent Status:")
            res_lines.append(status_text)
            full_text = "\n".join(res_lines)

            return {
                "content": [{"type": "text", "text": full_text}],
                "data": result,
                "result": full_text,
            }

        # 2. Login / Pair / QR Pairing
        if action in ("login", "pair", "qr", "reconfigure", "relink"):
            target_chan = channel or "whatsapp"
            if target_chan == "whatsapp":
                is_force = bool(params.get("force", False)) or action in ("reconfigure", "relink")
                phone = token or str(params.get("phone") or "").strip() or None
                result = await manager.login_whatsapp(
                    action="start",
                    account_id=str(params.get("account_id") or "default").strip(),
                    force=is_force,
                    phone=phone,
                )
                msg = result.get("message", "WhatsApp pairing initiated.")
                if result.get("qr_data_url"):
                    qr_url = result["qr_data_url"]
                    ascii_qr = result.get("ascii_qr", "")
                    msg = (
                        "### WhatsApp Pairing QR Code\n\n"
                        f"![WhatsApp QR]({qr_url})\n\n"
                        "Open WhatsApp on your mobile device > Settings > Linked Devices > Link a Device, and scan the QR code above.\n\n"
                        f"```\n{ascii_qr}\n```"
                    )
                return {
                    "content": [{"type": "text", "text": msg}],
                    "data": result,
                    "result": msg,
                }

        # 3. Configure / Add
        if action in ("configure", "add", "set"):
            if not channel:
                return {
                    "content": [
                        {
                            "type": "text",
                            "text": "Error: 'channel' parameter is required for configure.",
                        }
                    ]
                }
            result = await manager.configure_channel(
                channel=channel,
                token=token,
                dm_policy=dm_policy,
                allow_from=allow_from,
            )
            msg = result.get("message", f"Configured channel {channel}.")
            if result.get("qr_data_url"):
                qr_url = result["qr_data_url"]
                ascii_qr = result.get("ascii_qr", "")
                msg = (
                    f"{msg}\n\n"
                    "### WhatsApp Pairing QR Code\n\n"
                    f"![WhatsApp QR]({qr_url})\n\n"
                    "Open WhatsApp on your mobile device > Settings > Linked Devices > Link a Device, and scan the QR code above.\n\n"
                    f"```\n{ascii_qr}\n```"
                )
            return {
                "content": [{"type": "text", "text": msg}],
                "data": result,
                "result": msg,
            }

        # 3. Restart / Reload listener
        if action in ("restart", "reload"):
            if not channel:
                return {
                    "content": [
                        {
                            "type": "text",
                            "text": "Error: 'channel' parameter is required for restart.",
                        }
                    ]
                }
            res = await manager.start_channel_listener(channel)
            msg = (
                f"Restarted channel listener for '{channel}': {res.get('status', 'ok')}"
                if res.get("ok")
                else f"Failed to restart '{channel}': {res.get('error')}"
            )
            return {
                "content": [{"type": "text", "text": msg}],
                "data": res,
                "result": msg,
            }

        # 4. Remove / Disable
        if action in ("remove", "disable", "stop"):
            if not channel:
                return {
                    "content": [
                        {
                            "type": "text",
                            "text": "Error: 'channel' parameter is required for remove.",
                        }
                    ]
                }
            await manager.stop_channel_listener(channel)
            cfg = (
                manager._read_canonical_config()
                if hasattr(manager, "_read_canonical_config")
                else {}
            )
            # Disable in config
            from src.channels.channel_manager import _read_canonical_config, _write_canonical_config

            cfg = _read_canonical_config()
            if "channels" in cfg and channel in cfg["channels"]:
                cfg["channels"][channel]["enabled"] = False
                _write_canonical_config(cfg)
            msg = f"Channel '{channel}' disabled and stopped."
            return {
                "content": [{"type": "text", "text": msg}],
                "result": msg,
            }

        # 5. List supported
        if action in ("list", "supported"):
            supported = manager.list_supported_channels()
            text = json.dumps(supported, indent=2)
            return {
                "content": [{"type": "text", "text": text}],
                "data": supported,
                "result": text,
            }

        # 6. Status (default)
        status = manager.get_channel_status(channel)
        text = json.dumps(status, indent=2)
        return {
            "content": [{"type": "text", "text": text}],
            "data": status,
            "result": text,
        }

    return {
        "name": definition["name"],
        "label": "Channels",
        "description": definition["description"],
        "parameters": definition["parameters"],
        "execute": _execute,
    }


# ── 2. Channel Doctor Tool Definition ─────────────────────────────────


def create_channel_doctor_definition() -> dict[str, Any]:
    return {
        "name": "channel_doctor",
        "description": (
            "Diagnose and automatically self-heal external messaging channels (Telegram, WhatsApp, Discord, Slack). "
            "Use this tool whenever the user reports channel connection issues, asks to fix channel config, "
            "or says they have provided a bot token. It will recover missing tokens from memory/env, "
            "validate them against official APIs, update config.json, and launch the live listener automatically."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "channel": {
                    "type": "STRING",
                    "description": "Optional specific channel to diagnose and repair (e.g. 'telegram'). If omitted, heals all channels.",
                },
                "auto_fix": {
                    "type": "BOOLEAN",
                    "description": "Whether to automatically apply repairs and start listeners. Default is true.",
                },
            },
        },
    }


def create_channel_doctor_tool(live_host: Any = None) -> dict[str, Any]:
    """Factory creating the channel_doctor AgentTool."""
    definition = create_channel_doctor_definition()
    manager = ChannelManager.get_instance()
    if live_host is not None:
        manager.set_live_host(live_host)

    async def _execute(
        tool_call_id: str,
        params: dict[str, Any],
        signal: Any = None,
        on_update: Any = None,
    ) -> dict[str, Any]:
        channel = str(params.get("channel") or "").strip().lower() or None
        auto_fix = bool(params.get("auto_fix", True))

        if auto_fix:
            result = await manager.doctor_repair(channel_id=channel, auto_detect_tokens=True)
        else:
            result = await manager.doctor_diagnose(channel_id=channel)

        changes = result.get("changes", [])
        warnings = result.get("warnings", [])
        status_text = json.dumps(result.get("status", {}), indent=2)

        res_lines = ["[Channel Doctor Autonomous Repair Report]"]
        if changes:
            res_lines.append("Repairs Applied:")
            for c in changes:
                res_lines.append(f"  ✔ {c}")
        if warnings:
            res_lines.append("Warnings / Action Required:")
            for w in warnings:
                res_lines.append(f"  ⚠ {w}")
        if not changes and not warnings:
            res_lines.append("  All channel listeners and configurations verified healthy.")
        res_lines.append("\nCurrent State:")
        res_lines.append(status_text)
        full_text = "\n".join(res_lines)

        return {
            "content": [{"type": "text", "text": full_text}],
            "data": result,
            "result": full_text,
        }

    return {
        "name": definition["name"],
        "label": "Channel Doctor",
        "description": definition["description"],
        "parameters": definition["parameters"],
        "execute": _execute,
    }


# ── 3. Configure Channel Tool Definition ──────────────────────────────


def create_configure_channel_definition() -> dict[str, Any]:
    return {
        "name": "configure_channel",
        "description": (
            "Configure, validate, and connect an external messaging channel (e.g. Telegram, Discord, Slack). "
            "Use this tool WHENEVER the user provides a channel bot token (e.g. Telegram Bot token from @BotFather) "
            "or asks to configure/connect a messaging bot. "
            "This tool validates the token against the official API, writes canonical configuration "
            "to ~/.jarvis/config.json, and automatically starts the live listener so incoming messages "
            "flow directly into JARVIS."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "channel": {
                    "type": "STRING",
                    "description": "Messaging channel identifier (e.g. 'telegram', 'discord', 'slack').",
                },
                "token": {
                    "type": "STRING",
                    "description": "Bot API token (e.g. Telegram token from @BotFather, Discord bot token, etc.).",
                },
                "dm_policy": {
                    "type": "STRING",
                    "description": "Direct message access policy: 'open' (allow all users), 'allowlist', or 'pairing'. Default 'open'.",
                },
                "allow_from": {
                    "type": "ARRAY",
                    "items": {"type": "STRING"},
                    "description": "Optional list of allowed user IDs or handles.",
                },
            },
            "required": ["channel", "token"],
        },
    }


def create_configure_channel_tool(live_host: Any = None) -> dict[str, Any]:
    """Factory creating the configure_channel AgentTool."""
    definition = create_configure_channel_definition()
    manager = ChannelManager.get_instance()
    if live_host is not None:
        manager.set_live_host(live_host)

    async def _execute(
        tool_call_id: str,
        params: dict[str, Any],
        signal: Any = None,
        on_update: Any = None,
    ) -> dict[str, Any]:
        channel = str(params.get("channel", "")).strip().lower()
        token = str(
            params.get("token") or params.get("bot_token") or params.get("botToken") or ""
        ).strip()
        dm_policy = str(params.get("dm_policy") or "open").strip().lower()
        allow_from = params.get("allow_from")

        if not channel:
            return {
                "content": [{"type": "text", "text": "Error: 'channel' parameter is required."}]
            }
        if not token:
            return {"content": [{"type": "text", "text": "Error: 'token' parameter is required."}]}

        result = await manager.configure_channel(
            channel=channel,
            token=token,
            dm_policy=dm_policy,
            allow_from=allow_from,
        )

        if not result.get("ok"):
            err_msg = result.get("error", "Channel configuration failed.")
            return {
                "content": [{"type": "text", "text": f"❌ {err_msg}"}],
                "result": f"Error: {err_msg}",
            }

        msg = result.get("message", "Channel configured and listening.")
        bot_user = result.get("bot_username", "")
        bot_id = result.get("bot_id", "")
        status = result.get("status", "")

        return {
            "content": [{"type": "text", "text": f"✅ {msg}"}],
            "data": {
                "channel": channel,
                "bot_username": bot_user,
                "bot_id": bot_id,
                "status": status,
            },
            "result": msg,
        }

    return {
        "name": definition["name"],
        "label": "Configure Channel",
        "description": definition["description"],
        "parameters": definition["parameters"],
        "execute": _execute,
    }


# ── 4. Channel Status Tool Definition ─────────────────────────────────


def create_channel_status_definition() -> dict[str, Any]:
    return {
        "name": "channel_status",
        "description": (
            "Inspect the configuration, verification, and live listener status of messaging channels "
            "(Telegram, WhatsApp, Discord, Slack). Use this to check whether a bot is connected and listening."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "channel": {
                    "type": "STRING",
                    "description": "Optional channel name to query (e.g. 'telegram'). If omitted, returns all channels.",
                },
            },
        },
    }


def create_channel_status_tool() -> dict[str, Any]:
    """Factory creating the channel_status AgentTool."""
    definition = create_channel_status_definition()
    manager = ChannelManager.get_instance()

    async def _execute(
        tool_call_id: str,
        params: dict[str, Any],
        signal: Any = None,
        on_update: Any = None,
    ) -> dict[str, Any]:
        channel = params.get("channel")
        status = manager.get_channel_status(channel)
        text = json.dumps(status, indent=2)
        return {
            "content": [{"type": "text", "text": text}],
            "data": status,
            "result": text,
        }

    return {
        "name": definition["name"],
        "label": "Channel Status",
        "description": definition["description"],
        "parameters": definition["parameters"],
        "execute": _execute,
    }


# ── 5. WhatsApp Login Tool Definition ─────────────────────────────────


def create_whatsapp_login_definition() -> dict[str, Any]:
    return {
        "name": "whatsapp_login",
        "description": (
            "Interactive WhatsApp login and QR code generator. Supported actions: "
            "'start', 'login', 'pair', 'qr' (generates and returns an embedded QR code image to scan with phone), "
            "'wait' or 'check' (waits for or checks pairing status), "
            "'reconfigure' (forces a new pairing session / fresh QR code)."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type": "STRING",
                    "description": "Action to perform: 'start', 'login', 'pair', 'qr', 'wait', 'check', 'reconfigure'. Default is 'start'.",
                },
                "account_id": {
                    "type": "STRING",
                    "description": "Optional WhatsApp account ID (default 'default').",
                },
                "force": {
                    "type": "BOOLEAN",
                    "description": "Treat an existing link as needing a fresh pairing / new QR code.",
                },
                "phone": {
                    "type": "STRING",
                    "description": "Optional phone number to receive an 8-digit pairing code instead of scanning a QR code.",
                },
            },
        },
    }


def create_whatsapp_login_tool(live_host: Any = None) -> dict[str, Any]:
    """Factory creating the whatsapp_login AgentTool."""
    definition = create_whatsapp_login_definition()

    async def _execute(
        tool_call_id: str,
        params: dict[str, Any],
        signal: Any = None,
        on_update: Any = None,
    ) -> dict[str, Any]:
        action = str(params.get("action") or "start").strip().lower()
        account_id = str(params.get("account_id") or "default").strip()
        force = bool(params.get("force", False)) or action in ("reconfigure", "relink")
        phone = str(params.get("phone") or "").strip() or None

        async def _ensure_listener() -> None:
            try:
                from src.channels.channel_manager import ChannelManager

                cm = ChannelManager.get_instance()
                loop = cm._ensure_event_loop()
                if loop.is_running():
                    loop.call_soon_threadsafe(
                        lambda: loop.create_task(cm.start_channel_listener("whatsapp"))
                    )
                else:
                    loop.run_until_complete(cm.start_channel_listener("whatsapp"))
            except Exception:
                pass

        try:
            from src.channels.channel_manager import ChannelManager

            manager = ChannelManager.get_instance()

            if action in ("start", "login", "pair", "qr", "reconfigure", "relink"):
                res = await manager.login_whatsapp(
                    action="start",
                    account_id=account_id,
                    force=force,
                    phone=phone,
                )
                if res.get("qr_data_url"):
                    qr_url = res["qr_data_url"]
                    ascii_qr = res.get("ascii_qr", "")
                    res_msg = (
                        "### WhatsApp Pairing QR Code\n\n"
                        f"![WhatsApp QR]({qr_url})\n\n"
                        "Open WhatsApp on your mobile phone > Settings > Linked Devices > Link a Device, and scan the QR code above.\n\n"
                        f"```\n{ascii_qr}\n```"
                    )
                    return {
                        "content": [{"type": "text", "text": res_msg}],
                        "result": res_msg,
                        "data": res,
                        "connected": False,
                        "account_id": account_id,
                    }
                elif res.get("already_linked") or res.get("who"):
                    who = res.get("who", "linked")
                    await _ensure_listener()
                    res_msg = f"WhatsApp is already linked as {who} for account '{account_id}'. Live listener is active."
                    return {
                        "content": [{"type": "text", "text": res_msg}],
                        "result": res_msg,
                        "data": res,
                        "connected": True,
                        "account_id": account_id,
                    }
                else:
                    msg = res.get("message") or res.get("error") or "WhatsApp login initiated."
                    return {
                        "content": [{"type": "text", "text": msg}],
                        "result": msg,
                        "data": res,
                        "connected": False,
                        "account_id": account_id,
                    }

            if action in ("wait", "check", "status"):
                res = await manager.login_whatsapp(
                    action="wait",
                    account_id=account_id,
                    timeout_sec=float(params.get("timeout_sec") or 30.0),
                )
                is_conn = bool(res.get("ok") and res.get("linked"))
                who = res.get("who", "")
                if is_conn:
                    await _ensure_listener()
                    res_msg = f"WhatsApp is linked as {who} for account '{account_id}'."
                else:
                    err = res.get("error") or "WhatsApp is not linked."
                    res_msg = f"WhatsApp status: {err}"
                return {
                    "content": [{"type": "text", "text": res_msg}],
                    "result": res_msg,
                    "data": res,
                    "connected": is_conn,
                    "account_id": account_id,
                }

            return {
                "content": [{"type": "text", "text": f"Unknown action: {action}"}],
                "result": f"Unknown action: {action}",
            }
        except Exception as e:
            err = f"WhatsApp channel check failed: {e}"
            return {"content": [{"type": "text", "text": err}], "result": err}

    return {
        "name": definition["name"],
        "label": "WhatsApp Login",
        "description": definition["description"],
        "parameters": definition["parameters"],
        "execute": _execute,
    }


CHANNEL_TOOL_DECLARATIONS: list[dict[str, Any]] = [
    create_channels_definition(),
    create_channel_doctor_definition(),
    create_configure_channel_definition(),
    create_channel_status_definition(),
    create_whatsapp_login_definition(),
]

__all__ = [
    "CHANNEL_TOOL_DECLARATIONS",
    "create_channel_doctor_definition",
    "create_channel_doctor_tool",
    "create_channel_status_definition",
    "create_channel_status_tool",
    "create_channels_definition",
    "create_channels_tool",
    "create_configure_channel_definition",
    "create_configure_channel_tool",
    "create_whatsapp_login_definition",
    "create_whatsapp_login_tool",
]

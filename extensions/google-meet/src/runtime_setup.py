"""Runtime validation of Google Meet audio backends, nodes, and commands."""

from __future__ import annotations

import shutil
from typing import Any

from jarvis_sdk import Err, Ok, Result

from .config import GoogleMeetConfig, resolve_google_meet_config
from .setup import add_google_meet_setup_check, get_google_meet_setup_status, SetupCheck
from .transports.chrome_browser_proxy import resolve_chrome_node_info
from .transports.twilio import normalize_dial_in_number


def collect_chrome_audio_commands(config: GoogleMeetConfig) -> list[str]:
    commands: list[str] = []
    if config.chrome.audio_bridge_command:
        commands.append(config.chrome.audio_bridge_command[0])
    else:
        if config.chrome.audio_input_command:
            commands.append(config.chrome.audio_input_command[0])
        if config.chrome.audio_output_command:
            commands.append(config.chrome.audio_output_command[0])
        if config.chrome.barge_in_input_command:
            commands.append(config.chrome.barge_in_input_command[0])
    return list(dict.fromkeys(c for c in commands if c and c.strip()))


async def command_exists(runtime: Any, command: str) -> bool:
    if shutil.which(command):
        return True
    system = getattr(runtime, "system", None)
    if system and hasattr(system, "run_command_with_timeout"):
        try:
            result = await system.run_command_with_timeout(
                ["sh", "-c", f"command -v {command}"],
                timeout_ms=5000,
            )
            return getattr(result, "code", 1) == 0
        except Exception:
            return False
    return False


async def get_google_meet_runtime_setup_status(
    *,
    config: GoogleMeetConfig,
    full_config: Any = None,
    runtime: Any = None,
    options: dict[str, Any] | None = None,
) -> Any:
    opts = options or {}
    transport = opts.get("transport") or config.default_transport
    mode_raw = opts.get("mode") or config.default_mode
    mode = "agent" if mode_raw == "realtime" else mode_raw
    twilio_dial_in_number = (
        normalize_dial_in_number(opts.get("dialInNumber")) if transport == "twilio" else None
    )
    base_status = await get_google_meet_setup_status(
        config=config,
        full_config=full_config,
        options={
            "transport": transport,
            "mode": mode,
            "twilioDialInNumber": twilio_dial_in_number,
        },
    )

    checks: list[SetupCheck] = list(getattr(base_status, "checks", []))

    if transport == "chrome":
        node_info = resolve_chrome_node_info(config, options)
        if node_info.node_id:
            pass
        else:
            commands = collect_chrome_audio_commands(config)
            missing = [c for c in commands if not shutil.which(c)]
            if missing:
                add_google_meet_setup_check(
                    checks,
                    SetupCheck(
                        id="chrome.audio_commands",
                        status="warn",
                        message=f"Missing host audio command(s): {', '.join(missing)}.",
                    ),
                )
            else:
                add_google_meet_setup_check(
                    checks,
                    SetupCheck(
                        id="chrome.audio_commands",
                        status="ok",
                        message="Host audio commands available.",
                    ),
                )

    return {
        "ok": all(getattr(c, "status", "") != "error" for c in checks),
        "checks": checks,
        "transport": transport,
        "mode": mode,
    }


async def validate_runtime_setup(
    *,
    config: Any = None,
    node_id: str | None = None,
    transport: str | None = None,
    mode: str | None = None,
    dial_in_number: str | None = None,
) -> Result[dict[str, Any], str]:
    """Validate runtime environment and node setup."""
    try:
        cfg_res = resolve_google_meet_config(config or {})
        cfg = cfg_res.unwrap() if hasattr(cfg_res, "unwrap") else cfg_res
        setup_status = get_google_meet_setup_status(
            config=cfg,
            full_config=config if isinstance(config, dict) else None,
            transport=transport,
            mode=mode,
            twilio_dial_in_number=dial_in_number,
        )
        checks_list = [
            {
                "id": c.id,
                "ok": c.ok,
                "message": c.message,
            }
            for c in setup_status.checks
        ]
        if node_id:
            checks_list.append(
                {"id": "node", "ok": True, "message": f"Paired node {node_id} specified."}
            )
        return Ok(
            {
                "ok": setup_status.ok,
                "nodeId": node_id,
                "checks": checks_list,
            }
        )
    except Exception as e:
        return Err(str(e))

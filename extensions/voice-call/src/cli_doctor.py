"""CLI command handler for voicecall doctor."""

from __future__ import annotations

import argparse
import asyncio
from typing import Any

from .cli_shared import print_cli_result
from .doctor import run_voice_call_doctor


def handle_voice_call_doctor_cli(
    args: argparse.Namespace, raw_config: dict[str, Any] | None = None
) -> int:
    """Handle `jarvis voicecall doctor [--fix] [--json]`."""
    fix = getattr(args, "fix", False)
    is_json = getattr(args, "json", False)

    res = asyncio.run(run_voice_call_doctor(config=raw_config, fix=fix))
    data = res.unwrap() if res.is_ok else {"ok": False, "error": res.unwrap_err()}

    if is_json:
        print_cli_result(data, is_json=True)
    else:
        print("=== Voice Call Doctor ===")
        print(f"Status: {'OK' if data.get('ok') else 'FAIL'}")
        if data.get("repairs"):
            print("Repairs applied:" if fix else "Suggested repairs:")
            for r in data["repairs"]:
                print(f" - {r}")
        print("\nDiagnostic Checks:")
        for c in data.get("checks", []):
            mark = "✓" if c["ok"] else "✗"
            print(f" [{mark}] {c['id']}: {c['message']}")

    return 0 if data.get("ok") else 1

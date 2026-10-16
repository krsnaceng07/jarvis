"""CLI command handlers for 1Password plugin.

OpenClaw parity: mirrors @openclaw/onepassword CLI commands:
- `openclaw onepassword status`
- `openclaw onepassword audit [--limit <n>]`
- `openclaw onepassword secretref status [--json]`
- `openclaw onepassword secretref setup`
"""

from __future__ import annotations

import argparse
import datetime
import json
import sys
from pathlib import Path

from .config import OnepasswordConfig
from .op_cli import resolve_op_binary
from .secretref import build_secrets_setup_plan
from .storage import OnepasswordStorage
from .token import get_token_file_path, verify_token_prerequisites


def handle_status_command(
    config: OnepasswordConfig,
    state_dir: Path | None = None,
    storage: OnepasswordStorage | None = None,
) -> int:
    """Print readiness, binary path, and item registry statistics."""
    token_ready, token_err = verify_token_prerequisites(state_dir)
    token_path = get_token_file_path(state_dir)

    op_path, op_err = resolve_op_binary(config.op_bin)

    policy_counts: dict[str, int] = {"auto": 0, "approve": 0, "deny": 0}
    for slug in config.items:
        eff = config.get_effective_policy(slug)
        policy_counts[eff] = policy_counts.get(eff, 0) + 1

    print("1Password Plugin Status:")
    print(f"  Token file exists:     {'yes' if token_ready else 'no'}")
    print(f"  Token file path:       {token_path}")
    if token_err and not token_ready:
        print(f"  Token warning:         {token_err}")

    print(f"  op executable:         {'yes' if op_path else 'no'}")
    print(f"  op binary path:        {op_path or op_err or 'not found'}")

    print(f"  Default vault:         {config.vault}")
    print(f"  Default policy:        {config.default_policy}")
    print(f"  Registered items:      {len(config.items)}")
    print(
        f"  Policy breakdown:      auto={policy_counts['auto']}, "
        f"approve={policy_counts['approve']}, deny={policy_counts['deny']}"
    )

    if storage:
        active_grants = storage.list_standing_grants()
        print(f"  Active standing grants: {len(active_grants)}")

    return 0 if (token_ready and op_path) else 1


def handle_audit_command(
    storage: OnepasswordStorage,
    limit: int = 50,
    slug: str | None = None,
) -> int:
    """Print the newest-first audit log table."""
    rows = storage.get_audit_log(limit=limit, slug=slug)

    if not rows:
        print("No 1Password audit records found.")
        return 0

    print(
        f"{'TIMESTAMP':<20} | {'AGENT':<12} | {'SLUG':<20} | {'OUTCOME':<8} | {'ERR_CODE':<16} | {'CACHED':<6} | {'REASON'}"
    )
    print("-" * 110)

    for r in rows:
        dt_str = datetime.datetime.fromtimestamp(r.timestamp, tz=datetime.timezone.utc).strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        err_str = r.error_code or "-"
        cached_str = "yes" if r.cached else "no"
        agent_str = (r.agent_id[:10] + "..") if len(r.agent_id) > 12 else (r.agent_id or "-")
        reason_str = (r.reason[:30] + "..") if len(r.reason) > 32 else r.reason
        print(
            f"{dt_str:<20} | {agent_str:<12} | {r.slug:<20} | {r.outcome:<8} | {err_str:<16} | {cached_str:<6} | {reason_str}"
        )

    return 0


def handle_secretref_status_command(
    config: OnepasswordConfig,
    state_dir: Path | None = None,
    is_provider_configured: bool = True,
    as_json: bool = False,
) -> int:
    """Check SecretRef provider prerequisites and configuration readiness."""
    token_ready, token_err = verify_token_prerequisites(state_dir)
    token_path = get_token_file_path(state_dir)
    op_path, op_err = resolve_op_binary(config.op_bin)

    prerequisites_ready = token_ready and bool(op_path)
    overall_ready = prerequisites_ready and is_provider_configured

    data = {
        "provider": "onepassword",
        "configured": is_provider_configured,
        "prerequisitesReady": prerequisites_ready,
        "ready": overall_ready,
        "opPath": op_path,
        "opError": op_err if not op_path else None,
        "tokenPath": str(token_path),
        "tokenReady": token_ready,
        "tokenError": token_err if not token_ready else None,
    }

    if as_json:
        print(json.dumps(data, indent=2))
        return 0 if overall_ready else 1

    print("1Password SecretRef Status:")
    print(f"  prerequisites ready: {'yes' if prerequisites_ready else 'no'}")
    print(f"  provider configured: {'yes' if is_provider_configured else 'no'}")
    print(f"  ready:               {'yes' if overall_ready else 'no'}")
    print(f"  op binary:           {op_path or op_err or 'not found'}")
    print(f"  token file:          {token_path} ({'ready' if token_ready else token_err})")

    return 0 if overall_ready else 1


def handle_secretref_setup_command(
    args: list[str],
    state_dir: Path | None = None,
) -> int:
    """Build and write a secrets apply plan JSON."""
    parser = argparse.ArgumentParser(
        prog="onepassword secretref setup",
        description="Generate a secrets apply plan for 1Password SecretRefs.",
    )
    parser.add_argument(
        "--anthropic-id", dest="anthropic_id", help="1Password URI for Anthropic API key"
    )
    parser.add_argument(
        "--openrouter-id", dest="openrouter_id", help="1Password URI for OpenRouter API key"
    )
    parser.add_argument(
        "--provider-key",
        dest="provider_keys",
        action="append",
        help="Provider key target mapping in format provider=op://...",
    )
    parser.add_argument(
        "--target",
        dest="targets",
        action="append",
        help="Arbitrary credential target mapping in format config.path=op://...",
    )
    parser.add_argument(
        "--plan-out",
        dest="plan_out",
        default="./openclaw-1password-secrets-plan.json",
        help="Path where the secrets plan JSON file will be written",
    )

    parsed = parser.parse_args(args)

    try:
        plan = build_secrets_setup_plan(
            anthropic_id=parsed.anthropic_id,
            openrouter_id=parsed.openrouter_id,
            provider_keys=parsed.provider_keys,
            targets=parsed.targets,
        )
        plan.save(parsed.plan_out)
        print(
            f"Successfully generated secrets apply plan with {len(plan.targets)} target(s) -> {parsed.plan_out}"
        )
        return 0
    except Exception as exc:
        print(f"Error generating secrets setup plan: {exc}", file=sys.stderr)
        return 1

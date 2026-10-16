"""CLI command handlers for HashiCorp Vault plugin.

OpenClaw parity: mirrors @openclaw/vault CLI commands:
- `openclaw vault status [--provider-alias <alias>]`
- `openclaw vault setup`
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .config import VaultConfig, resolve_vault_config
from .secretref import build_vault_setup_plan


def handle_vault_status_command(
    config: VaultConfig | None = None,
    provider_alias: str | None = None,
    as_json: bool = False,
) -> int:
    """Check and display Vault connection and authentication status."""
    cfg = config or resolve_vault_config()

    token_present = bool(cfg.token)
    token_file_present = bool(cfg.token_file and Path(cfg.token_file).expanduser().exists())
    jwt_file_present = bool(
        cfg.get_effective_jwt_file() and Path(cfg.get_effective_jwt_file()).expanduser().exists()
    )

    auth_ready = False
    if cfg.auth_method == "token":
        auth_ready = token_present
    elif cfg.auth_method == "token_file":
        auth_ready = token_file_present
    elif cfg.auth_method in ("jwt", "kubernetes"):
        auth_ready = bool(cfg.auth_role and jwt_file_present)

    ready = bool(cfg.vault_addr and auth_ready)

    status_data: dict[str, Any] = {
        "provider": "vault",
        "providerAlias": provider_alias or "vault",
        "vaultAddr": cfg.vault_addr or None,
        "authMethod": cfg.auth_method,
        "authReady": auth_ready,
        "ready": ready,
        "tokenSet": token_present,
        "tokenFile": cfg.token_file,
        "tokenFileExists": token_file_present,
        "authMount": cfg.get_effective_auth_mount()
        if cfg.auth_method in ("jwt", "kubernetes")
        else None,
        "authRole": cfg.auth_role,
        "jwtFile": cfg.get_effective_jwt_file()
        if cfg.auth_method in ("jwt", "kubernetes")
        else None,
        "jwtFileExists": jwt_file_present if cfg.auth_method in ("jwt", "kubernetes") else None,
        "namespace": cfg.namespace,
        "kvMount": cfg.kv_mount,
        "kvVersion": cfg.kv_version,
    }

    if as_json:
        print(json.dumps(status_data, indent=2))
        return 0 if ready else 1

    print("HashiCorp Vault Plugin Status:")
    if provider_alias:
        print(f"  Provider alias:        {provider_alias}")
    print(f"  VAULT_ADDR:            {cfg.vault_addr or 'not set'}")
    print(f"  Auth method:           {cfg.auth_method}")
    print(f"  Token configured:      {'yes' if token_present else 'no'}")
    if cfg.token_file:
        print(
            f"  Token file:            {cfg.token_file} ({'exists' if token_file_present else 'not found'})"
        )
    if cfg.auth_method in ("jwt", "kubernetes"):
        print(f"  Auth mount:            {cfg.get_effective_auth_mount()}")
        print(f"  Auth role:             {cfg.auth_role or 'not set'}")
        jwt_f = cfg.get_effective_jwt_file()
        print(
            f"  JWT file:              {jwt_f or 'not set'} ({'exists' if jwt_file_present else 'not found'})"
        )
    if cfg.namespace:
        print(f"  Namespace:             {cfg.namespace}")
    print(f"  KV Mount:              {cfg.kv_mount}")
    print(f"  KV Version:            {cfg.kv_version}")
    print(f"  Ready for SecretRefs:  {'yes' if ready else 'no'}")

    return 0 if ready else 1


def handle_vault_setup_command(
    args: list[str],
) -> int:
    """Generate a secrets apply plan for Vault SecretRefs."""
    parser = argparse.ArgumentParser(
        prog="vault setup",
        description="Generate a secrets apply plan for HashiCorp Vault SecretRefs.",
    )
    parser.add_argument(
        "--openai-id", dest="openai_id", help="Vault SecretRef ID for OpenAI API key"
    )
    parser.add_argument(
        "--anthropic-id", dest="anthropic_id", help="Vault SecretRef ID for Anthropic API key"
    )
    parser.add_argument(
        "--openrouter-id", dest="openrouter_id", help="Vault SecretRef ID for OpenRouter API key"
    )
    parser.add_argument(
        "--provider-key",
        dest="provider_keys",
        action="append",
        help="Provider key target mapping in format provider=path/field",
    )
    parser.add_argument(
        "--target",
        dest="targets",
        action="append",
        help="Arbitrary credential target mapping in format config.path=path/field",
    )
    parser.add_argument(
        "--plan-out",
        dest="plan_out",
        default="./vault-secrets-plan.json",
        help="Output path for the secrets apply plan JSON",
    )

    parsed = parser.parse_args(args)

    try:
        plan = build_vault_setup_plan(
            openai_id=parsed.openai_id,
            anthropic_id=parsed.anthropic_id,
            openrouter_id=parsed.openrouter_id,
            provider_keys=parsed.provider_keys,
            targets=parsed.targets,
        )
        plan.save(parsed.plan_out)
        print(
            f"Successfully generated Vault secrets apply plan with {len(plan.targets)} target(s) -> {parsed.plan_out}"
        )
        return 0
    except Exception as exc:
        print(f"Error generating Vault setup plan: {exc}", file=sys.stderr)
        return 1

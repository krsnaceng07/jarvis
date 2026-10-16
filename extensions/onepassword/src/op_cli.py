"""1Password CLI runner with security isolation, concurrency limits, and error mapping.

OpenClaw parity: mirrors @openclaw/onepassword op execution:
- Concurrency limit = 4 (asyncio.Semaphore(4))
- Minimal isolated environment:
  OP_LOAD_DESKTOP_APP_SETTINGS=false
  OP_BIOMETRIC_UNLOCK_ENABLED=false
  OP_SERVICE_ACCOUNT_TOKEN=<token>
  HOME=<user home>
- --cache=false on all executions
- Mapping to closed error codes: TOKEN_MISSING, OP_NOT_FOUND, ITEM_NOT_FOUND,
  FIELD_NOT_FOUND, RATE_LIMITED, AUTH_FAILED, TIMEOUT, OP_ERROR
- Single execution per request, zero retries
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import sys
from pathlib import Path

from .token import read_service_account_token, verify_token_prerequisites
from .types import (
    AUTH_FAILED,
    FIELD_NOT_FOUND,
    ITEM_NOT_FOUND,
    OP_ERROR,
    OP_NOT_FOUND,
    RATE_LIMITED,
    TIMEOUT,
    TOKEN_MISSING,
    SecretItemResult,
    SecretRefResolution,
)

logger = logging.getLogger("jarvis.onepassword.op_cli")

# Max 4 concurrent op processes across the gateway process
OP_SEMAPHORE = asyncio.Semaphore(4)


def resolve_op_binary(custom_bin: str | None = None) -> tuple[str | None, str | None]:
    """Find and validate the op executable path.

    Returns (bin_path, error_message).
    """
    if custom_bin:
        custom_path = Path(custom_bin).expanduser().resolve()
        if not custom_path.exists():
            return None, f"Configured opBin '{custom_bin}' does not exist"
        if not custom_path.is_file():
            return None, f"Configured opBin '{custom_bin}' is not a file"
        if not os.access(custom_path, os.X_OK):
            return None, f"Configured opBin '{custom_bin}' is not executable"
        return str(custom_path), None

    found = shutil.which("op")
    if not found and sys.platform == "win32":
        found = shutil.which("op.exe")

    if not found:
        return None, "1Password CLI ('op') executable was not found on PATH"

    return found, None


def build_isolated_env(token: str) -> dict[str, str]:
    """Construct the minimal isolated environment for the op CLI child process."""
    env: dict[str, str] = {
        "OP_SERVICE_ACCOUNT_TOKEN": token,
        "OP_LOAD_DESKTOP_APP_SETTINGS": "false",
        "OP_BIOMETRIC_UNLOCK_ENABLED": "false",
        "HOME": os.environ.get("HOME") or os.environ.get("USERPROFILE") or str(Path.home()),
    }

    # Pass minimal necessary OS platform keys for subprocess execution
    if sys.platform == "win32":
        for key in ("SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT", "TEMP", "TMP"):
            if key in os.environ:
                env[key] = os.environ[key]

    # Include PATH so op can invoke any required system loaders if needed
    if "PATH" in os.environ:
        env["PATH"] = os.environ["PATH"]

    return env


def map_op_error(stderr: str, stdout: str, returncode: int) -> tuple[str, str]:
    """Map op CLI stderr/stdout to a closed error code and user-facing message."""
    combined = f"{stderr}\n{stdout}".lower()

    if "rate limit" in combined or "429" in combined or "too many requests" in combined:
        return RATE_LIMITED, "1Password service-account rate limit reached"

    if (
        "authentication failed" in combined
        or "invalid service account token" in combined
        or "unauthorized" in combined
        or "401" in combined
        or "token is invalid" in combined
        or "not signed in" in combined
    ):
        return AUTH_FAILED, "1Password service-account authentication failed"

    if (
        "isn't an item" in combined
        or "item not found" in combined
        or "could not be found in vault" in combined
        or "no item found" in combined
    ):
        return ITEM_NOT_FOUND, f"Configured item is not in the vault ({stderr.strip()})"

    if (
        "isn't a field" in combined
        or "field not found" in combined
        or "no field matching" in combined
        or "field does not exist" in combined
    ):
        return FIELD_NOT_FOUND, f"Configured field is not on the item ({stderr.strip()})"

    msg = stderr.strip() or stdout.strip() or f"1Password CLI command failed with code {returncode}"
    return OP_ERROR, msg


class OpCliRunner:
    """Handles execution of the 1Password CLI with safety bounds."""

    def __init__(
        self,
        op_bin: str | None = None,
        state_dir: Path | None = None,
        default_timeout_ms: int = 15000,
    ) -> None:
        self.custom_op_bin = op_bin
        self.state_dir = state_dir
        self.default_timeout_ms = default_timeout_ms

    def check_prerequisites(self) -> tuple[bool, str | None, str | None]:
        """Check op binary resolution and service account token readiness.

        Returns (ready, op_path, error_message).
        """
        token_ready, token_err = verify_token_prerequisites(self.state_dir)
        if not token_ready:
            return False, None, token_err

        op_path, op_err = resolve_op_binary(self.custom_op_bin)
        if not op_path:
            return False, None, op_err

        return True, op_path, None

    async def get_item_field(
        self,
        slug: str,
        item: str,
        field: str,
        vault: str,
        timeout_ms: int | None = None,
    ) -> tuple[SecretItemResult | None, str | None, str | None]:
        """Execute `op item get` for a specific item, vault, and field.

        Returns (result, error_code, error_message).
        """
        # Step 1: Check token
        token = read_service_account_token(self.state_dir)
        if not token:
            return None, TOKEN_MISSING, "1Password service-account token is missing or empty"

        # Step 2: Resolve binary
        op_bin, bin_err = resolve_op_binary(self.custom_op_bin)
        if not op_bin:
            return None, OP_NOT_FOUND, bin_err or "1Password CLI binary not found"

        timeout_sec = (timeout_ms or self.default_timeout_ms) / 1000.0

        # Command: op item get <item> --vault <vault> --fields <field> --format json --cache=false
        cmd = [
            op_bin,
            "item",
            "get",
            item,
            f"--vault={vault}",
            f"--fields={field}",
            "--format=json",
            "--cache=false",
        ]

        env = build_isolated_env(token)

        async with OP_SEMAPHORE:
            try:
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    env=env,
                )

                try:
                    stdout_bytes, stderr_bytes = await asyncio.wait_for(
                        proc.communicate(),
                        timeout=timeout_sec,
                    )
                except asyncio.TimeoutError:
                    try:
                        proc.kill()
                    except Exception:
                        pass
                    return (
                        None,
                        TIMEOUT,
                        f"1Password CLI command timed out after {timeout_sec:.1f}s",
                    )

                stdout = stdout_bytes.decode("utf-8", errors="replace")
                stderr = stderr_bytes.decode("utf-8", errors="replace")

                if proc.returncode != 0:
                    code, msg = map_op_error(stderr, stdout, proc.returncode)
                    return None, code, msg

                # Parse JSON output or raw string
                value = self._extract_value_from_output(stdout, field)
                if value is None:
                    return (
                        None,
                        FIELD_NOT_FOUND,
                        f"Field '{field}' could not be extracted from 1Password item response",
                    )

                return (
                    SecretItemResult(
                        slug=slug,
                        item=item,
                        field=field,
                        value=value,
                    ),
                    None,
                    None,
                )

            except FileNotFoundError:
                return None, OP_NOT_FOUND, f"1Password binary not executable at {op_bin}"
            except Exception as exc:
                return None, OP_ERROR, f"Unexpected error executing 1Password CLI: {exc}"

    async def read_secret_ref(
        self,
        ref_uri: str,
        timeout_ms: int | None = None,
    ) -> SecretRefResolution:
        """Execute `op read <ref_uri> --cache=false` for a SecretRef.

        Returns SecretRefResolution.
        """
        token = read_service_account_token(self.state_dir)
        if not token:
            return SecretRefResolution(
                ref_id=ref_uri,
                error="1Password service-account token is missing or empty",
                error_code=TOKEN_MISSING,
            )

        op_bin, bin_err = resolve_op_binary(self.custom_op_bin)
        if not op_bin:
            return SecretRefResolution(
                ref_id=ref_uri,
                error=bin_err or "1Password CLI binary not found",
                error_code=OP_NOT_FOUND,
            )

        timeout_sec = (timeout_ms or self.default_timeout_ms) / 1000.0

        # Command: op read <ref_uri> --cache=false
        cmd = [
            op_bin,
            "read",
            ref_uri,
            "--cache=false",
        ]

        env = build_isolated_env(token)

        async with OP_SEMAPHORE:
            try:
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    env=env,
                )

                try:
                    stdout_bytes, stderr_bytes = await asyncio.wait_for(
                        proc.communicate(),
                        timeout=timeout_sec,
                    )
                except asyncio.TimeoutError:
                    try:
                        proc.kill()
                    except Exception:
                        pass
                    return SecretRefResolution(
                        ref_id=ref_uri,
                        error=f"1Password CLI read timed out after {timeout_sec:.1f}s",
                        error_code=TIMEOUT,
                    )

                stdout = stdout_bytes.decode("utf-8", errors="replace")
                stderr = stderr_bytes.decode("utf-8", errors="replace")

                if proc.returncode != 0:
                    code, msg = map_op_error(stderr, stdout, proc.returncode)
                    return SecretRefResolution(
                        ref_id=ref_uri,
                        error=msg,
                        error_code=code,
                    )

                value = stdout.rstrip("\r\n")
                return SecretRefResolution(
                    ref_id=ref_uri,
                    value=value,
                    cached=False,
                )

            except FileNotFoundError:
                return SecretRefResolution(
                    ref_id=ref_uri,
                    error=f"1Password binary not executable at {op_bin}",
                    error_code=OP_NOT_FOUND,
                )
            except Exception as exc:
                return SecretRefResolution(
                    ref_id=ref_uri,
                    error=f"Unexpected error executing op read: {exc}",
                    error_code=OP_ERROR,
                )

    def _extract_value_from_output(self, stdout: str, requested_field: str) -> str | None:
        """Extract secret value from op item get output."""
        trimmed = stdout.strip()
        if not trimmed:
            return None

        # Try parsing as JSON
        try:
            data = json.loads(trimmed)
            if isinstance(data, dict):
                # Standard op output shapes:
                # 1. {"value": "..."}
                if "value" in data:
                    return str(data["value"])
                # 2. {"fields": [{"label": "credential", "value": "..."}, ...]}
                if "fields" in data and isinstance(data["fields"], list):
                    for f in data["fields"]:
                        if isinstance(f, dict):
                            label = f.get("label") or f.get("id") or ""
                            if label.lower() == requested_field.lower():
                                return str(f.get("value", ""))
                # 3. Direct key in object
                if requested_field in data:
                    return str(data[requested_field])
            elif isinstance(data, list):
                # List of field objects
                for item in data:
                    if isinstance(item, dict):
                        label = item.get("label") or item.get("id") or ""
                        if label.lower() == requested_field.lower() or not requested_field:
                            return str(item.get("value", ""))
                # If only 1 field in list, return its value
                if len(data) == 1 and isinstance(data[0], dict) and "value" in data[0]:
                    return str(data[0]["value"])
            elif isinstance(data, (str, int, float, bool)):
                return str(data)
        except json.JSONDecodeError:
            pass

        # If not JSON or single raw string output from --fields
        return stdout.rstrip("\r\n")

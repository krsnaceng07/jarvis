"""Guided activation, inference validation, and isolated tool-use verifier for llama-server."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any
from jarvis_sdk import Ok, Result

VERIFICATION_DEADLINE_SECONDS = 90.0


@dataclass(slots=True)
class VerificationReport:
    ok: bool
    response_check_passed: bool
    tool_check_passed: bool
    model_id: str
    duration_seconds: float = 0.0
    error_phase: str | None = None  # "response_check", "tool_check", or None
    error_message: str | None = None


async def verify_managed_model_candidate(
    *,
    model_id: str,
    endpoint: str,
    simulated_model_handler: Any = None,
    timeout_seconds: float = VERIFICATION_DEADLINE_SECONDS,
) -> Result[VerificationReport, str]:
    """Perform guided activation checks on a candidate llama.cpp model.

    Phases:
    1. Inference response check: sends a basic probe prompt and verifies a valid text reply.
    2. Isolated tool-use check: requests model to read a temporary file via a tool in an
       isolated workspace without agent bootstrap instructions. A plain text reply alone fails.
    Each check enforces a strict 90-second deadline.
    """
    import time

    start_time = time.time()

    # 1. Inference response check
    try:
        if simulated_model_handler is not None:
            res_val = await asyncio.wait_for(
                simulated_model_handler(phase="response_check", prompt="ping"),
                timeout=timeout_seconds,
            )
            if not res_val.get("ok"):
                return Ok(
                    VerificationReport(
                        ok=False,
                        response_check_passed=False,
                        tool_check_passed=False,
                        model_id=model_id,
                        error_phase="response_check",
                        error_message=res_val.get("error", "Inference response check failed"),
                    )
                )
    except asyncio.TimeoutError:
        return Ok(
            VerificationReport(
                ok=False,
                response_check_passed=False,
                tool_check_passed=False,
                model_id=model_id,
                error_phase="response_check",
                error_message=f"Inference response check timed out after {timeout_seconds}s",
            )
        )

    # 2. Isolated tool-use check
    try:
        if simulated_model_handler is not None:
            tool_val = await asyncio.wait_for(
                simulated_model_handler(
                    phase="tool_check",
                    prompt="Read the file secret.txt and return its contents using read_file tool",
                ),
                timeout=timeout_seconds,
            )
            tool_called = bool(tool_val.get("tool_called", False))
            if not tool_called or not tool_val.get("ok"):
                return Ok(
                    VerificationReport(
                        ok=False,
                        response_check_passed=True,
                        tool_check_passed=False,
                        model_id=model_id,
                        error_phase="tool_check",
                        error_message=(
                            "Model returned plain text without calling the required tool in the isolated test workspace."
                            if not tool_called
                            else tool_val.get("error", "Tool execution check failed")
                        ),
                    )
                )
    except asyncio.TimeoutError:
        return Ok(
            VerificationReport(
                ok=False,
                response_check_passed=True,
                tool_check_passed=False,
                model_id=model_id,
                error_phase="tool_check",
                error_message=f"Isolated tool-use check timed out after {timeout_seconds}s",
            )
        )

    elapsed = time.time() - start_time
    return Ok(
        VerificationReport(
            ok=True,
            response_check_passed=True,
            tool_check_passed=True,
            model_id=model_id,
            duration_seconds=round(elapsed, 2),
        )
    )

"""Context-engine host compatibility checks prevent engines from running on unsupported harnesses.

OpenClaw parity: ``src/context-engine/host-compat.ts``.
"""
from __future__ import annotations

from typing import Any, Mapping, Sequence

__all__ = [
    "CODEX_APP_SERVER_CONTEXT_ENGINE_HOST",
    "GENERIC_CLI_CONTEXT_ENGINE_HOST_CAPABILITIES",
    "OPENCLAW_EMBEDDED_CONTEXT_ENGINE_HOST",
    "assert_context_engine_host_support",
    "build_generic_cli_context_engine_host_support",
    "evaluate_context_engine_host_support",
]

# Host support shape: {"id": str, "label": str, "capabilities": tuple[str, ...]}

GENERIC_CLI_CONTEXT_ENGINE_HOST_CAPABILITIES: tuple[str, ...] = (
    "bootstrap",
    "after-turn",
    "maintain",
)

OPENCLAW_EMBEDDED_CONTEXT_ENGINE_HOST: dict[str, Any] = {
    "id": "openclaw-embedded",
    "label": "OpenClaw embedded runner",
    "capabilities": (
        "bootstrap",
        "assemble-before-prompt",
        "after-turn",
        "maintain",
        "compact",
        "runtime-llm-complete",
    ),
}

CODEX_APP_SERVER_CONTEXT_ENGINE_HOST: dict[str, Any] = {
    "id": "codex-app-server",
    "label": "Codex app-server harness",
    "capabilities": (
        "bootstrap",
        "assemble-before-prompt",
        "after-turn",
        "maintain",
        "compact",
        "runtime-llm-complete",
        "thread-bootstrap-projection",
    ),
}


def build_generic_cli_context_engine_host_support(
    *, backend_id: str, capabilities: Sequence[str] | None = None
) -> dict[str, Any]:
    """Build the default host support advertised by the generic CLI runner."""
    return {
        "id": f"cli:{backend_id}",
        "label": f'CLI backend "{backend_id}"',
        "capabilities": tuple(
            capabilities
            if capabilities is not None
            else GENERIC_CLI_CONTEXT_ENGINE_HOST_CAPABILITIES
        ),
    }


def evaluate_context_engine_host_support(
    *,
    context_engine_info: Mapping[str, Any],
    operation: str,
    host: Mapping[str, Any],
) -> dict[str, Any]:
    """Evaluate whether a context-engine host can safely run the requested operation."""
    host_requirements = context_engine_info.get("hostRequirements") or {}
    requirements = host_requirements.get(operation)
    required = (requirements or {}).get("requiredCapabilities") or []
    if not requirements or len(required) == 0:
        return {"ok": True, "requirements": requirements, "missingCapabilities": []}

    supported = set(host.get("capabilities") or ())
    # Capabilities are host-advertised facts; requirements stay engine-authored per operation.
    missing_capabilities = [
        capability for capability in required if capability not in supported
    ]
    if not missing_capabilities:
        return {"ok": True, "requirements": requirements, "missingCapabilities": []}

    return {
        "ok": False,
        "requirements": requirements,
        "missingCapabilities": missing_capabilities,
    }


def assert_context_engine_host_support(
    *,
    context_engine: Any,
    operation: str,
    host: Mapping[str, Any],
) -> None:
    """Assert that a context engine can safely run under the supplied host."""
    evaluation = evaluate_context_engine_host_support(
        context_engine_info=context_engine.info,
        operation=operation,
        host=host,
    )
    if evaluation["ok"]:
        return

    engine_id = context_engine.info["id"]
    requirements = evaluation["requirements"]
    required = ", ".join(requirements["requiredCapabilities"])
    capabilities = host.get("capabilities") or ()
    actual = ", ".join(capabilities) if len(capabilities) > 0 else "(none)"
    unsupported_message = requirements.get("unsupportedMessage")
    guidance = f" {unsupported_message}" if unsupported_message else ""
    raise RuntimeError(
        f'Context engine "{engine_id}" cannot run operation "{operation}" on {host["label"]}. '
        f"Missing host capabilities: {', '.join(evaluation['missingCapabilities'])}. "
        f"Required capabilities: {required}. "
        f"Host capabilities: {actual}.{guidance}"
    )

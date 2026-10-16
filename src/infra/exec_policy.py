"""src.infra.exec_policy - exec policy layer merging.

OpenClaw parity: mirrors ``openclaw-main/src/infra/exec-policy.ts``.
"""

from typing import Any, Dict, TypeVar

from src.infra.exec_approvals import (
    ExecMode,
    resolve_exec_policy_for_mode,
)

TBase = TypeVar("TBase", bound=Dict[str, Any])


def apply_exec_policy_layer(base: TBase, layer: Dict[str, Any] | None) -> TBase:
    """Merges an override layer into a base exec policy.
    
    If `mode` is provided in the layer, it overrides `security` and `ask`
    via the canonical mode resolution mapping.
    Otherwise, if raw `security` or `ask` are provided, it strips `mode`
    from the base to avoid returning an inconsistent snapshot.
    """
    if not layer:
        return base

    mode_val: ExecMode | None = layer.get("mode")
    if mode_val:
        resolved = resolve_exec_policy_for_mode(mode_val)
        result = dict(base)
        result["mode"] = mode_val
        result["security"] = resolved["security"]
        result["ask"] = resolved["ask"]
        # In OpenClaw, autoReview isn't spread into the policy layer if the type
        # doesn't define it, but for TS it was just returning the intersection.
        # We ensure standard keys are updated.
        return result  # type: ignore

    layer_security = layer.get("security")
    layer_ask = layer.get("ask")
    
    if layer_security is not None or layer_ask is not None:
        result = dict(base)
        # Strip mode since raw security/ask overrides are applied
        result.pop("mode", None)
        result["security"] = layer_security if layer_security is not None else base.get("security")
        result["ask"] = layer_ask if layer_ask is not None else base.get("ask")
        return result  # type: ignore

    return base

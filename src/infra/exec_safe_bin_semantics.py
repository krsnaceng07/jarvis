"""src.infra.exec_safe_bin_semantics - semantic validations for safe bins.

OpenClaw parity: mirrors ``openclaw-main/src/infra/exec-safe-bin-semantics.ts``
"""

from typing import Callable, Dict, TypedDict

class SafeBinSemanticValidationParams(TypedDict, total=False):
    binName: str
    positional: list[str]


class SafeBinSemanticRule(TypedDict, total=False):
    validate: Callable[[SafeBinSemanticValidationParams], bool]
    configWarning: str


def _always_deny_safe_bin_semantics(params: SafeBinSemanticValidationParams) -> bool:
    return False


UNSAFE_SAFE_BIN_WARNINGS = {
    "awk": "awk-family interpreters can execute commands, access ENVIRON, and write files, so prefer explicit allowlist entries or approval-gated runs instead of safeBins.",
    "jq": "jq can read environment data and load jq code from modules or startup files, so prefer explicit allowlist entries or approval-gated runs instead of safeBins.",
    "sed": "sed scripts can execute commands and write files, so prefer explicit allowlist entries or approval-gated runs instead of safeBins.",
}

SAFE_BIN_SEMANTIC_RULES: Dict[str, SafeBinSemanticRule] = {
    "jq": {
        "validate": _always_deny_safe_bin_semantics,
        "configWarning": UNSAFE_SAFE_BIN_WARNINGS["jq"],
    },
    "awk": {
        "validate": _always_deny_safe_bin_semantics,
        "configWarning": UNSAFE_SAFE_BIN_WARNINGS["awk"],
    },
    "gawk": {
        "validate": _always_deny_safe_bin_semantics,
        "configWarning": UNSAFE_SAFE_BIN_WARNINGS["awk"],
    },
    "mawk": {
        "validate": _always_deny_safe_bin_semantics,
        "configWarning": UNSAFE_SAFE_BIN_WARNINGS["awk"],
    },
    "nawk": {
        "validate": _always_deny_safe_bin_semantics,
        "configWarning": UNSAFE_SAFE_BIN_WARNINGS["awk"],
    },
    "sed": {
        "validate": _always_deny_safe_bin_semantics,
        "configWarning": UNSAFE_SAFE_BIN_WARNINGS["sed"],
    },
    "gsed": {
        "validate": _always_deny_safe_bin_semantics,
        "configWarning": UNSAFE_SAFE_BIN_WARNINGS["sed"],
    },
}


def normalize_safe_bin_name(raw: str) -> str:
    trimmed = raw.strip().lower()
    if not trimmed:
        return ""
    # Normalize path separators
    trimmed = trimmed.replace("\\", "/")
    tail = trimmed.split("/")[-1]
    
    # Remove Windows executable extensions
    for ext in (".exe", ".cmd", ".bat", ".com"):
        if tail.endswith(ext):
            tail = tail[:-len(ext)]
            break
            
    return tail


def _get_safe_bin_semantic_rule(bin_name: str | None) -> SafeBinSemanticRule | None:
    if not isinstance(bin_name, str):
        return None
    normalized = normalize_safe_bin_name(bin_name)
    return SAFE_BIN_SEMANTIC_RULES.get(normalized)


def validate_safe_bin_semantics(params: SafeBinSemanticValidationParams) -> bool:
    rule = _get_safe_bin_semantic_rule(params.get("binName"))
    if rule and "validate" in rule:
        return rule["validate"](params)
    return True


def list_risky_configured_safe_bins(entries: list[str]) -> list[dict[str, str]]:
    hits: Dict[str, str] = {}
    for entry in entries:
        normalized = normalize_safe_bin_name(entry)
        if not normalized or normalized in hits:
            continue
        rule = _get_safe_bin_semantic_rule(normalized)
        if rule and "configWarning" in rule:
            hits[normalized] = rule["configWarning"]
            
    return [{"bin": b, "warning": w} for b, w in sorted(hits.items())]

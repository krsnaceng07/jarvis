"""src.infra.exec_safe_bin_policy_validator - argv validation.

OpenClaw parity: mirrors ``openclaw-main/src/infra/exec-safe-bin-policy-validator.ts``
"""

import re
from typing import Mapping, FrozenSet

from src.infra.exec_command_resolution import parse_exec_argv_token
from src.infra.exec_safe_bin_policy_profiles import (
    SafeBinProfile,
    _build_long_flag_prefix_map,
    _collect_known_long_flags,
)
from src.infra.exec_safe_bin_semantics import validate_safe_bin_semantics


def _is_path_like_token(value: str) -> bool:
    trimmed = value.strip()
    if not trimmed:
        return False
    if trimmed == "-":
        return False
    if trimmed.startswith("./") or trimmed.startswith("../") or trimmed.startswith("~"):
        return True
    if trimmed.startswith("/"):
        return True
    return bool(re.match(r"^[A-Za-z]:[\\/]", trimmed))


def _has_glob_token(value: str) -> bool:
    return bool(re.search(r"[*?[\]]", value))


def _has_shell_expansion_token(value: str) -> bool:
    return bool(re.search(r"\$(?:[A-Za-z0-9_@*?!$#-]|\{|\(|\[)", value))


def _is_safe_literal_token(value: str) -> bool:
    if not value or value == "-":
        return True
    return (
        not _has_glob_token(value)
        and not _has_shell_expansion_token(value)
        and not _is_path_like_token(value)
    )


def _is_invalid_value_token(value: str | None) -> bool:
    return value is None or not _is_safe_literal_token(value)


def _resolve_canonical_long_flag(
    flag: str,
    known_long_flags_set: FrozenSet[str],
    long_flag_prefix_map: Mapping[str, str | None],
) -> str | None:
    if not flag.startswith("--") or len(flag) <= 2:
        return None
    if flag in known_long_flags_set:
        return flag
    return long_flag_prefix_map.get(flag)


def _consume_long_option_token(
    args: list[str],
    index: int,
    flag: str,
    inline_value: str | None,
    allowed_value_flags: FrozenSet[str],
    denied_flags: FrozenSet[str],
    known_long_flags_set: FrozenSet[str],
    long_flag_prefix_map: Mapping[str, str | None],
) -> int:
    canonical_flag = _resolve_canonical_long_flag(
        flag, known_long_flags_set, long_flag_prefix_map
    )
    if not canonical_flag:
        return -1
    if canonical_flag in denied_flags:
        return -1
        
    expects_value = canonical_flag in allowed_value_flags
    if inline_value is not None:
        if not expects_value:
            return -1
        return index + 1 if _is_safe_literal_token(inline_value) else -1
        
    if not expects_value:
        return index + 1
        
    next_token = args[index + 1] if index + 1 < len(args) else None
    return -1 if _is_invalid_value_token(next_token) else index + 2


def _consume_short_option_cluster_token(
    args: list[str],
    index: int,
    cluster: str,
    flags: list[str],
    allowed_value_flags: FrozenSet[str],
    allowed_boolean_flags: FrozenSet[str],
    denied_flags: FrozenSet[str],
) -> int:
    for j, flag in enumerate(flags):
        if flag in denied_flags:
            return -1
        if flag in allowed_value_flags:
            inline_value = cluster[j + 1 :]
            if inline_value:
                return index + 1 if _is_safe_literal_token(inline_value) else -1
            next_token = args[index + 1] if index + 1 < len(args) else None
            return -1 if _is_invalid_value_token(next_token) else index + 2
        if flag in allowed_boolean_flags:
            continue
        return -1
    return index + 1


def _consume_positional_token(token: str, positional: list[str]) -> bool:
    if not _is_safe_literal_token(token):
        return False
    positional.append(token)
    return True


def _validate_positional_count(positional: list[str], profile: SafeBinProfile) -> bool:
    min_positional = profile.min_positional or 0
    if len(positional) < min_positional:
        return False
    if profile.max_positional is not None and len(positional) > profile.max_positional:
        return False
    return True


def _collect_positional_tokens(args: list[str], profile: SafeBinProfile) -> list[str] | None:
    allowed_value_flags = profile.allowed_value_flags
    allowed_boolean_flags = profile.allowed_boolean_flags
    denied_flags = profile.denied_flags
    
    known_long_flags = profile.known_long_flags
    if not known_long_flags:
        known_long_flags = _collect_known_long_flags(
            allowed_value_flags, denied_flags, allowed_boolean_flags
        )
        
    known_long_flags_set = profile.known_long_flags_set or frozenset(known_long_flags)
    long_flag_prefix_map = profile.long_flag_prefix_map or _build_long_flag_prefix_map(known_long_flags)

    positional: list[str] = []
    i = 0
    while i < len(args):
        raw_token = args[i] if args[i] is not None else ""
        token = parse_exec_argv_token(raw_token)

        if token["kind"] in ("empty", "stdin"):
            i += 1
            continue

        if token["kind"] == "terminator":
            for j in range(i + 1, len(args)):
                rest = args[j]
                if not rest or rest == "-":
                    continue
                if not _consume_positional_token(rest, positional):
                    return None
            break

        if token["kind"] == "positional":
            if not _consume_positional_token(token["raw"], positional):
                return None
            i += 1
            continue

        if token["style"] == "long":
            next_index = _consume_long_option_token(
                args,
                i,
                token["flag"],
                token["inlineValue"],
                allowed_value_flags,
                denied_flags,
                known_long_flags_set,
                long_flag_prefix_map,
            )
            if next_index < 0:
                return None
            i = next_index
            continue

        next_index = _consume_short_option_cluster_token(
            args,
            i,
            token["cluster"], # type: ignore
            token["flags"], # type: ignore
            allowed_value_flags,
            allowed_boolean_flags,
            denied_flags,
        )
        if next_index < 0:
            return None
        i = next_index

    return positional


def validate_safe_bin_argv(
    args: list[str],
    profile: SafeBinProfile,
    bin_name: str | None = None,
) -> bool:
    positional = _collect_positional_tokens(args, profile)
    if positional is None:
        return False
    if not _validate_positional_count(positional, profile):
        return False
        
    params = {"positional": positional}
    if bin_name is not None:
        params["binName"] = bin_name
        
    return validate_safe_bin_semantics(params) # type: ignore

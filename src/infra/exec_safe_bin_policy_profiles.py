"""src.infra.exec_safe_bin_policy_profiles - safe bin configurations.

OpenClaw parity: mirrors ``openclaw-main/src/infra/exec-safe-bin-policy-profiles.ts``
"""

from dataclasses import dataclass
from typing import Dict, FrozenSet, Mapping, Set

# Reusing the dict type from types_tools
from src.config.types_tools import SafeBinProfileFixture

DEFAULT_SAFE_BINS = ("cut", "uniq", "head", "tail", "tr", "wc")
NO_FLAGS: FrozenSet[str] = frozenset()


@dataclass(frozen=True)
class SafeBinProfile:
    min_positional: int | None = None
    max_positional: int | None = None
    allowed_value_flags: FrozenSet[str] = NO_FLAGS
    allowed_boolean_flags: FrozenSet[str] = NO_FLAGS
    denied_flags: FrozenSet[str] = NO_FLAGS
    known_long_flags: tuple[str, ...] = ()
    known_long_flags_set: FrozenSet[str] = NO_FLAGS
    long_flag_prefix_map: Mapping[str, str | None] = frozenset()


def _to_flag_set(flags: list[str] | None) -> FrozenSet[str]:
    if not flags:
        return NO_FLAGS
    return frozenset(flags)


def _collect_known_long_flags(
    allowed_value_flags: FrozenSet[str],
    denied_flags: FrozenSet[str],
    allowed_boolean_flags: FrozenSet[str] = NO_FLAGS,
) -> tuple[str, ...]:
    known: Set[str] = set()
    for flag in allowed_value_flags:
        if flag.startswith("--"):
            known.add(flag)
    for flag in allowed_boolean_flags:
        if flag.startswith("--"):
            known.add(flag)
    for flag in denied_flags:
        if flag.startswith("--"):
            known.add(flag)
    return tuple(sorted(known))


def _build_long_flag_prefix_map(known_long_flags: tuple[str, ...]) -> Mapping[str, str | None]:
    prefix_map: Dict[str, str | None] = {}
    for flag in known_long_flags:
        if not flag.startswith("--") or len(flag) <= 2:
            continue
        for length in range(3, len(flag) + 1):
            prefix = flag[:length]
            if prefix not in prefix_map:
                prefix_map[prefix] = flag
                continue
            if prefix_map[prefix] != flag:
                prefix_map[prefix] = None
    return prefix_map


def _compile_safe_bin_profile(fixture: dict) -> SafeBinProfile:
    allowed_value_flags = _to_flag_set(fixture.get("allowedValueFlags"))
    allowed_boolean_flags = _to_flag_set(fixture.get("allowedBooleanFlags"))
    denied_flags = _to_flag_set(fixture.get("deniedFlags"))
    
    known_long_flags = _collect_known_long_flags(
        allowed_value_flags, denied_flags, allowed_boolean_flags
    )
    
    return SafeBinProfile(
        min_positional=fixture.get("minPositional"),
        max_positional=fixture.get("maxPositional"),
        allowed_value_flags=allowed_value_flags,
        allowed_boolean_flags=allowed_boolean_flags,
        denied_flags=denied_flags,
        known_long_flags=known_long_flags,
        known_long_flags_set=frozenset(known_long_flags),
        long_flag_prefix_map=_build_long_flag_prefix_map(known_long_flags),
    )


def _compile_safe_bin_profiles(fixtures: dict[str, dict]) -> dict[str, SafeBinProfile]:
    return {name: _compile_safe_bin_profile(fixture) for name, fixture in fixtures.items()}


SAFE_BIN_PROFILE_FIXTURES: dict[str, dict] = {
    "jq": {
        "maxPositional": 1,
        "allowedValueFlags": ["--arg", "--argjson", "--argstr"],
        "deniedFlags": [
            "--argfile",
            "--rawfile",
            "--slurpfile",
            "--from-file",
            "--library-path",
            "-L",
            "-f",
        ],
    },
    "grep": {
        "maxPositional": 0,
        "allowedValueFlags": [
            "--regexp",
            "--max-count",
            "--after-context",
            "--before-context",
            "--context",
            "--devices",
            "--binary-files",
            "--exclude",
            "--include",
            "--label",
            "-e",
            "-m",
            "-A",
            "-B",
            "-C",
            "-D",
        ],
        "deniedFlags": [
            "--file",
            "--exclude-from",
            "--dereference-recursive",
            "--directories",
            "--recursive",
            "-f",
            "-d",
            "-r",
            "-R",
        ],
    },
    "cut": {
        "maxPositional": 0,
        "allowedValueFlags": [
            "--bytes",
            "--characters",
            "--fields",
            "--delimiter",
            "--output-delimiter",
            "-b",
            "-c",
            "-f",
            "-d",
        ],
        "allowedBooleanFlags": [
            "--complement",
            "--only-delimited",
            "--zero-terminated",
            "-n",
            "-s",
            "-z",
        ],
    },
    "sort": {
        "maxPositional": 0,
        "allowedValueFlags": [
            "--key",
            "--field-separator",
            "--buffer-size",
            "--parallel",
            "--batch-size",
            "-k",
            "-t",
            "-S",
        ],
        "deniedFlags": [
            "--compress-program",
            "--files0-from",
            "--output",
            "--random-source",
            "--temporary-directory",
            "-T",
            "-o",
        ],
    },
    "uniq": {
        "maxPositional": 0,
        "allowedValueFlags": [
            "--skip-fields",
            "--skip-chars",
            "--check-chars",
            "--group",
            "-f",
            "-s",
            "-w",
        ],
        "allowedBooleanFlags": [
            "--count",
            "--repeated",
            "--unique",
            "--ignore-case",
            "--zero-terminated",
            "-c",
            "-d",
            "-u",
            "-i",
            "-z",
        ],
    },
    "head": {
        "maxPositional": 0,
        "allowedValueFlags": ["--lines", "--bytes", "-n", "-c"],
        "allowedBooleanFlags": [
            "--quiet",
            "--silent",
            "--verbose",
            "--zero-terminated",
            "-q",
            "-v",
            "-z",
        ],
    },
    "tail": {
        "maxPositional": 0,
        "allowedValueFlags": [
            "--lines",
            "--bytes",
            "--sleep-interval",
            "--max-unchanged-stats",
            "--pid",
            "-n",
            "-c",
        ],
        "allowedBooleanFlags": [
            "--quiet",
            "--silent",
            "--verbose",
            "--zero-terminated",
            "-q",
            "-v",
            "-z",
        ],
        "deniedFlags": ["--follow", "--retry", "-F", "-f"],
    },
    "tr": {
        "minPositional": 1,
        "maxPositional": 2,
        "allowedBooleanFlags": [
            "--complement",
            "--delete",
            "--squeeze-repeats",
            "--truncate-set1",
            "-C",
            "-c",
            "-d",
            "-s",
            "-t",
        ],
    },
    "wc": {
        "maxPositional": 0,
        "allowedBooleanFlags": [
            "--bytes",
            "--chars",
            "--lines",
            "--max-line-length",
            "--words",
            "-L",
            "-c",
            "-l",
            "-m",
            "-w",
        ],
        "deniedFlags": ["--files0-from"],
    },
}

SAFE_BIN_PROFILES: dict[str, SafeBinProfile] = _compile_safe_bin_profiles(SAFE_BIN_PROFILE_FIXTURES)


def normalize_safe_bin_profile_name(raw: str) -> str | None:
    trimmed = raw.strip().lower()
    return trimmed if trimmed else None


def normalize_fixture_limit(raw: int | None) -> int | None:
    if raw is None or not isinstance(raw, int) or raw < 0:
        return None
    return raw


def normalize_fixture_flags(flags: list[str] | None) -> list[str] | None:
    if not flags or not isinstance(flags, list):
        return None
    normalized = sorted(list(set(f.strip() for f in flags if f.strip())))
    return normalized if normalized else None


def normalize_safe_bin_profile_fixture(fixture: SafeBinProfileFixture) -> SafeBinProfileFixture:
    min_pos = normalize_fixture_limit(fixture.get("minPositional"))
    max_pos_raw = normalize_fixture_limit(fixture.get("maxPositional"))
    max_pos = min_pos if (min_pos is not None and max_pos_raw is not None and max_pos_raw < min_pos) else max_pos_raw
    
    return {
        "minPositional": min_pos,
        "maxPositional": max_pos,
        "allowedValueFlags": normalize_fixture_flags(fixture.get("allowedValueFlags")),
        "deniedFlags": normalize_fixture_flags(fixture.get("deniedFlags")),
    }


def normalize_safe_bin_profile_fixtures(
    fixtures: dict[str, SafeBinProfileFixture] | None,
) -> dict[str, SafeBinProfileFixture]:
    normalized: dict[str, SafeBinProfileFixture] = {}
    if not fixtures:
        return normalized
    for raw_name, fixture in fixtures.items():
        name = normalize_safe_bin_profile_name(raw_name)
        if name:
            normalized[name] = normalize_safe_bin_profile_fixture(fixture)
    return normalized


def resolve_safe_bin_profiles(
    fixtures: dict[str, SafeBinProfileFixture] | None,
) -> dict[str, SafeBinProfile]:
    normalized_fixtures = normalize_safe_bin_profile_fixtures(fixtures)
    if not normalized_fixtures:
        return SAFE_BIN_PROFILES
    
    merged = dict(SAFE_BIN_PROFILES)
    merged.update(_compile_safe_bin_profiles(normalized_fixtures))
    return merged

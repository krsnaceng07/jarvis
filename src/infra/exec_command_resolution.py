"""src.infra.exec_command_resolution - parsing utility for command tokens.

OpenClaw parity: mirrors ``openclaw-main/src/infra/exec-command-resolution.ts``
"""

from typing import Literal, TypedDict


class ExecArgvTokenEmpty(TypedDict):
    kind: Literal["empty"]
    raw: str


class ExecArgvTokenTerminator(TypedDict):
    kind: Literal["terminator"]
    raw: str


class ExecArgvTokenStdin(TypedDict):
    kind: Literal["stdin"]
    raw: str


class ExecArgvTokenPositional(TypedDict):
    kind: Literal["positional"]
    raw: str


class ExecArgvTokenOptionLong(TypedDict):
    kind: Literal["option"]
    raw: str
    style: Literal["long"]
    flag: str
    inlineValue: str | None


class ExecArgvTokenOptionShortCluster(TypedDict):
    kind: Literal["option"]
    raw: str
    style: Literal["short-cluster"]
    cluster: str
    flags: list[str]


ExecArgvToken = (
    ExecArgvTokenEmpty
    | ExecArgvTokenTerminator
    | ExecArgvTokenStdin
    | ExecArgvTokenPositional
    | ExecArgvTokenOptionLong
    | ExecArgvTokenOptionShortCluster
)


def parse_exec_argv_token(raw: str) -> ExecArgvToken:
    if not raw:
        return {"kind": "empty", "raw": raw}
    if raw == "--":
        return {"kind": "terminator", "raw": raw}
    if raw == "-":
        return {"kind": "stdin", "raw": raw}
    if not raw.startswith("-"):
        return {"kind": "positional", "raw": raw}
    if raw.startswith("--"):
        eq_index = raw.find("=")
        if eq_index > 0:
            return {
                "kind": "option",
                "raw": raw,
                "style": "long",
                "flag": raw[:eq_index],
                "inlineValue": raw[eq_index + 1 :],
            }
        return {
            "kind": "option",
            "raw": raw,
            "style": "long",
            "flag": raw,
            "inlineValue": None,
        }
    
    cluster = raw[1:]
    return {
        "kind": "option",
        "raw": raw,
        "style": "short-cluster",
        "cluster": cluster,
        "flags": [f"-{c}" for c in cluster],
    }

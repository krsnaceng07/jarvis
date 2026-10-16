"""src.infra.exec_approvals_analysis - Command analysis types for approvals.

OpenClaw parity: mirrors ``openclaw-main/src/infra/exec-command-analysis-types.ts``
"""

from typing import TypedDict


class ExecutableResolution(TypedDict, total=False):
    rawExecutable: str
    resolvedPath: str
    resolvedRealPath: str
    executableName: str


class CommandResolution(TypedDict, total=False):
    execution: ExecutableResolution
    policy: ExecutableResolution
    effectiveArgv: list[str]
    wrapperChain: list[str]
    policyBlocked: bool
    blockedWrapper: str


class ExecCommandSegment(TypedDict, total=False):
    raw: str
    argv: list[str]
    sourceArgv: list[str]
    resolution: CommandResolution | None

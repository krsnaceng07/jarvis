"""Ciao process-error classifier.

Mirrors OpenClaw's ``extensions/bonjour/src/ciao.ts``:
recognizes known noisy ciao failures so the Bonjour plugin
can suppress or repair expected mDNS lifecycle issues.

Two known error categories:

1. **netmask-assertion** — ciao's netmask vs IP version
   assertion (``IP ADDRESS VERSION MUST MATCH. NETMASK
   CANNOT HAVE A VERSION DIFFERENT FROM THE ADDRESS!``).
   Known harmless during transient interface reconfigure.
2. **interface-enumeration-failure** — restricted
   sandboxes (NemoClaw, Docker-in-Docker, k3s with
   locked-down policy) can refuse ``os.networkInterfaces()``
   which ciao calls during NetworkManager init. The Node
   runtime surfaces this as a SystemError mentioning the
   libuv syscall ``UV_INTERFACE_ADDRESSES``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable, Iterator

from .errors import format_bonjour_error

# Case-insensitive matches. The TS source uses the /u flag +
# explicit uppercase comparison to match regardless of case;
# the Python port uses ``re.IGNORECASE`` for the same effect.
CIAO_NETMASK_ASSERTION_MESSAGE_RE = re.compile(
    r"IP ADDRESS VERSION MUST MATCH\.\s+NETMASK CANNOT HAVE A VERSION DIFFERENT FROM THE ADDRESS!?",
    re.IGNORECASE,
)
CIAO_INTERFACE_ENUMERATION_FAILURE_RE = re.compile(
    r"\bUV_INTERFACE_ADDRESSES\b",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class NetmaskAssertion:
    """Classified ciao netmask-vs-IP-version assertion."""

    kind: str = "netmask-assertion"
    formatted: str = ""


@dataclass(frozen=True, slots=True)
class InterfaceEnumerationFailure:
    """Classified ``os.networkInterfaces()`` failure (restricted sandbox)."""

    kind: str = "interface-enumeration-failure"
    formatted: str = ""


CiaoProcessErrorClassification = NetmaskAssertion | InterfaceEnumerationFailure


def _collect_error_graph_candidates(
    reason: Any, walker: Callable[[Any], list[Any]]
) -> Iterator[Any]:
    """Walk an error graph and yield each node.

    Mirrors OpenClaw's ``collectErrorGraphCandidates`` from
    ``openclaw/plugin-sdk/error-runtime``: starts at ``reason``
    and visits each node returned by ``walker(current)``,
    tracking visited nodes to avoid cycles.

    The Python port handles Python's exception chaining
    (``__cause__``, ``__context__``) plus the dict-style
    ``args[0]`` + ``errors``/``original`` patterns the
    OpenClaw JS code walks.
    """
    visited: set[int] = set()
    current: Any = reason
    while current is not None and id(current) not in visited:
        visited.add(id(current))
        yield current
        next_nodes = walker(current)
        if not next_nodes:
            break
        # Prefer the first non-None candidate (matches the TS chain)
        next_node: Any = None
        for n in next_nodes:
            if n is not None:
                next_node = n
                break
        current = next_node


def _python_walker(current: Any) -> list[Any]:
    """Walker for Python exception graphs.

    Returns a list of candidate nodes from the given
    exception's chains + attributes. Mirrors the TS
    walker's traversal of ``cause``, ``reason``,
    ``original``, ``error``, ``data``, and ``errors``.
    """
    out: list[Any] = []
    # Python exception chains
    cause = getattr(current, "__cause__", None)
    if cause is not None:
        out.append(cause)
    context = getattr(current, "__context__", None)
    if context is not None and context is not cause:
        out.append(context)
    # JS-style attrs (dicts / opaque error wrappers)
    if isinstance(current, dict):
        for key in ("cause", "reason", "original", "error", "data"):
            if key in current and current[key] is not None:
                out.append(current[key])
        if isinstance(current.get("errors"), list):
            out.extend(e for e in current["errors"] if e is not None)
    else:
        for key in ("reason", "original", "error", "data"):
            v = getattr(current, key, None)
            if v is not None:
                out.append(v)
        errors = getattr(current, "errors", None)
        if isinstance(errors, list):
            out.extend(e for e in errors if e is not None)
    return out


def classify_ciao_process_error(reason: Any) -> CiaoProcessErrorClassification | None:
    """Classify a ciao error/rejection chain into a known category.

    Returns ``None`` if the reason is not a known ciao
    noise pattern (i.e. should be surfaced to the user
    normally). Returns a frozen dataclass instance with
    ``kind`` + ``formatted`` for known patterns.

    Mirrors ``classifyCiaoProcessError`` in OpenClaw's
    ``extensions/bonjour/src/ciao.ts``.
    """
    for candidate in _collect_error_graph_candidates(reason, _python_walker):
        formatted = format_bonjour_error(candidate)
        message = formatted.upper()
        if CIAO_NETMASK_ASSERTION_MESSAGE_RE.search(message):
            return NetmaskAssertion(formatted=formatted)
        if CIAO_INTERFACE_ENUMERATION_FAILURE_RE.search(message):
            return InterfaceEnumerationFailure(formatted=formatted)
    return None

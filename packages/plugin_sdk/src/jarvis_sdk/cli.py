"""Plugin CLI registration types.

Mirrors OpenClaw's ``OpenClawPluginCliRegistrar`` and
``OpenClawPluginCliContext`` from
``src/plugins/plugin-registration.types.ts``.

A plugin registers CLI subcommands with::

    api.register_cli(register, descriptors=[...])

where ``register(ctx)`` mutates ``ctx.program`` (an
``argparse.ArgumentParser``-like object) to add the plugin's subcommands.
``descriptors`` advertises the top-level commands for the global
``--help`` output.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class CliDescriptor:
    """Metadata for a CLI subcommand (advertised in global help)."""

    name: str
    description: str
    has_subcommands: bool = False


@dataclass
class CliContext:
    """Context given to a plugin's CLI registrar.

    Attributes
    ----------
    program : argparse.ArgumentParser
        The argparse subparser the plugin should attach to. For root
        registrations this is the host's root ``jarvis`` program. For
        nested registrations it is the resolved parent.
    parent_path : list[str]
        The command path leading to ``program`` (e.g. ``["nodes"]``).
    config : dict
        The host's config view (read-only).
    workspace_dir : str | None
        Workspace root (if any).
    logger : Any
        Logger handle.
    """

    program: Any  # argparse.ArgumentParser (or compatible)
    parent_path: list[str] = field(default_factory=list)
    config: dict = field(default_factory=dict)
    workspace_dir: str | None = None
    logger: Any = None


@runtime_checkable
class CliRegistrar(Protocol):
    """A plugin's CLI registrar — mutates ``ctx.program`` to add subcommands.

    Mirrors OpenClaw's ``OpenClawPluginCliRegistrar`` signature::

        async (ctx: CliContext) -> None
    """

    def __call__(self, ctx: CliContext) -> Any: ...  # None or Awaitable[None]


__all__ = ["CliContext", "CliDescriptor", "CliRegistrar"]

"""Lobster commands registry.

Mirrors `src/commands/registry.ts`.
"""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any, AsyncIterable


class CommandRegistry:
    """Registry for Lobster commands."""

    def __init__(self):
        self._commands = {}

    def register(self, name: str, command: Any):
        self._commands[name] = command

    def get(self, name: str) -> Any:
        return self._commands.get(name)


class ExecCommand:
    """The 'exec' command - runs a local subprocess."""

    meta = {"resumeSafeBeforeInput": True}

    async def run(
        self, input_iter: AsyncIterable[Any], args: dict[str, Any], ctx: dict[str, Any]
    ) -> dict[str, Any]:
        """Run a subprocess and yield its stdout as JSON or strings."""
        command = args.get("shell") or args.get("_", [])
        if isinstance(command, list):
            command_str = " ".join(command)
        else:
            command_str = command

        if not command_str:
            raise ValueError("exec requires a command")

        # Collect stdin
        input_data = []
        async for item in input_iter:
            input_data.append(item)

        stdin_bytes = None
        if input_data:
            stdin_str = "\n".join(
                json.dumps(x) if not isinstance(x, str) else x for x in input_data
            )
            stdin_bytes = stdin_str.encode("utf-8")

        env = dict(ctx.get("env", os.environ))

        process = await asyncio.create_subprocess_shell(
            command_str,
            stdin=asyncio.subprocess.PIPE if stdin_bytes else None,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
            cwd=ctx.get("cwd"),
        )

        stdout, stderr = await process.communicate(input=stdin_bytes)

        if process.returncode != 0:
            err = stderr.decode("utf-8")
            raise RuntimeError(f"Command failed with code {process.returncode}: {err}")

        out_str = stdout.decode("utf-8").strip()

        is_json = args.get("json", False)

        async def output_generator():
            if not out_str:
                return
            if is_json:
                # Try to parse as a single JSON array or objects separated by newlines
                try:
                    parsed = json.loads(out_str)
                    if isinstance(parsed, list):
                        for item in parsed:
                            yield item
                    else:
                        yield parsed
                except json.JSONDecodeError:
                    # Fallback to lines
                    for line in out_str.split("\n"):
                        if not line.strip():
                            continue
                        try:
                            yield json.loads(line)
                        except json.JSONDecodeError:
                            yield line
            else:
                for line in out_str.split("\n"):
                    yield line

        return {"output": output_generator()}


class ApproveCommand:
    """The 'approve' command - suspends execution for user approval."""

    meta = {"resumeSafeBeforeInput": True}

    async def run(
        self, input_iter: AsyncIterable[Any], args: dict[str, Any], ctx: dict[str, Any]
    ) -> dict[str, Any]:
        """Suspend execution and ask for approval."""
        prompt = args.get("prompt", "Approval required to continue")

        items = []
        async for item in input_iter:
            items.append(item)

        limit = args.get("limit")
        preview_items = items
        if limit is not None:
            limit_val = int(limit)
            preview_items = items[:limit_val]

        # Call requestInput which throws InputRequestSuspension
        if "requestInput" in ctx:
            await ctx["requestInput"](prompt=prompt, items=preview_items)

        # If we reach here, it means we resumed and were approved!
        async def output_generator():
            for item in items:
                yield item

        return {"output": output_generator()}


registry = CommandRegistry()
registry.register("exec", ExecCommand())
registry.register("approve", ApproveCommand())

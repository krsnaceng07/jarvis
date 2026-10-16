import asyncio
import logging
from pathlib import Path
from typing import Any

_log = logging.getLogger("jarvis.hooks.boot_md")

async def handle(event: Any) -> None:
    """Runs BOOT.md if present in the workspace on gateway startup."""
    if event.type != "gateway" or event.action != "startup":
        return

    # In Jarvis, gateway:startup usually includes the workspace config or we can resolve it.
    # We will assume event.context has 'workspaces' (a list of active workspaces)
    workspaces = event.context.get("workspaces", [])
    if not workspaces:
        _log.debug("no workspaces in gateway:startup context")
        return

    # For each workspace, try to execute BOOT.md
    for ws_dir_str in workspaces:
        ws_dir = Path(ws_dir_str)
        boot_file = ws_dir / "BOOT.md"
        if not boot_file.exists():
            continue

        _log.info("running %s", boot_file)
        
        try:
            # We use the openclaw/jarvis system event CLI to execute the file
            # jarvis system event --file BOOT.md
            proc = await asyncio.create_subprocess_exec(
                "jarvis", "system", "event", "--file", str(boot_file),
                cwd=str(ws_dir),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
            if proc.returncode != 0:
                _log.warning("BOOT.md in %s failed (code %d):\n%s", ws_dir, proc.returncode, stderr.decode(errors="replace"))
            else:
                _log.debug("BOOT.md in %s finished successfully", ws_dir)
        except Exception as e:
            _log.error("failed to run BOOT.md in %s: %s", ws_dir, e)

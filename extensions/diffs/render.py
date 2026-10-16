import asyncio
import json
from typing import Any, Dict
from pathlib import Path

WORKER_SCRIPT = Path(__file__).parent / "render_worker.js"


class DiffRenderInputError(Exception):
    pass


async def _invoke_worker(command: str, args: Dict[str, Any]) -> Any:
    payload = json.dumps({"command": command, "args": args})
    process = await asyncio.create_subprocess_exec(
        "node",
        str(WORKER_SCRIPT),
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    stdout, stderr = await process.communicate(input=payload.encode("utf-8"))

    if process.returncode != 0:
        err = stderr.decode("utf-8").strip()
        raise RuntimeError(f"Node worker failed: {err}")

    out_str = stdout.decode("utf-8").strip()
    if not out_str:
        raise RuntimeError("Node worker returned no output")

    try:
        resp = json.loads(out_str)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Failed to parse worker output: {out_str}") from e

    if not resp.get("success"):
        raise DiffRenderInputError(resp.get("error", "Unknown worker error"))

    return resp


async def preload_diff_html_before_after(
    old_file: str, new_file: str, options: Dict[str, Any]
) -> str:
    resp = await _invoke_worker(
        "preloadDiffHTML_before_after",
        {
            "oldFile": old_file,
            "newFile": new_file,
            "options": options,
        },
    )
    return resp["html"]


async def preload_diff_html_patch(file_diff: Any, options: Dict[str, Any]) -> str:
    resp = await _invoke_worker(
        "preloadDiffHTML_patch",
        {
            "fileDiff": file_diff,
            "options": options,
        },
    )
    return resp["html"]


async def parse_patch_files(patch: str) -> list[Any]:
    resp = await _invoke_worker("parsePatchFiles", {"patch": patch})
    return resp["files"]

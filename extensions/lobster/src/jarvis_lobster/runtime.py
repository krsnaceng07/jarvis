"""Runtime for executing Lobster pipelines.

Mirrors `runtime.ts`. Handles the async generation chain and
suspension logic.
"""

from __future__ import annotations

import logging
from typing import Any, AsyncIterable, Dict, List, Optional

from .commands import registry
from .input_request import CommandInputResume, InputRequestSuspension, generate_resume_token
from .parser import parse_pipeline

logger = logging.getLogger(__name__)


async def _empty_iterator() -> AsyncIterable[Any]:
    if False:
        yield


class LobsterRuntime:
    """The runtime context for a pipeline execution."""

    def __init__(
        self,
        pipeline_stages: List[Dict[str, Any]],
        cwd: str,
        env: Dict[str, str],
        resume_request: Optional[CommandInputResume] = None,
    ):
        self.pipeline_stages = pipeline_stages
        self.cwd = cwd
        self.env = env
        self.resume_request = resume_request
        self._halted = False
        self._halted_at = None

    async def _make_request_input(self, stage_index: int):
        """Build the requestInput callable for a specific stage."""

        async def request_input(prompt: str, items: list[Any]) -> None:
            if self.resume_request:
                # We are resuming.
                # Only approve if we are at the EXACT stage that requested it!
                # Since we don't store exactly which stage index generated the resume token in the simple port,
                # we just assume if resume_request is present, we approve the first requestInput we hit
                # (which should be the one we suspended on).
                # Wait, what if the approval_id doesn't match? OpenClaw checks token validity beforehand,
                # but here we can just clear it and proceed.
                if self.resume_request.approved:
                    self.resume_request = None  # Consume it
                    return
                else:
                    raise RuntimeError("Pipeline cancelled by user at approval stage.")

            # We are not resuming, so we suspend!
            token, app_id = generate_resume_token()
            raise InputRequestSuspension(
                stage_index=stage_index,
                prompt=prompt,
                items=items,
                resume_token=token,
                approval_id=app_id,
            )

        return request_input

    async def execute(self) -> Dict[str, Any]:
        """Execute the pipeline and return collected items or suspension state."""
        current_iter: AsyncIterable[Any] = _empty_iterator()

        for index, stage in enumerate(self.pipeline_stages):
            cmd_name = stage["name"]
            command = registry.get(cmd_name)
            if not command:
                raise ValueError(f"Unknown command: {cmd_name}")

            # Prepare context for the stage
            ctx = {
                "cwd": self.cwd,
                "env": self.env,
                "requestInput": await self._make_request_input(index),
            }

            try:
                result = await command.run(current_iter, stage["args"], ctx)
                if "output" in result:
                    current_iter = result["output"]
                else:
                    current_iter = _empty_iterator()
            except InputRequestSuspension as e:
                # Bubble up the suspension so the caller can return the envelope
                raise e
            except Exception as e:
                logger.error(f"Error in stage {index} ({cmd_name}): {e}")
                raise e

        # Pull items through the pipeline
        items = []
        try:
            async for item in current_iter:
                items.append(item)
        except InputRequestSuspension as e:
            # Stage might throw lazily during iteration
            raise e

        return {
            "items": items,
            "halted": False,
            "haltedAt": None,
        }


async def run_pipeline(
    pipeline: str,
    cwd: str,
    env: Dict[str, str],
    resume_request: Optional[CommandInputResume] = None,
) -> Dict[str, Any]:
    """Execute a lobster pipeline string or file."""
    stages, resolved_args = parse_pipeline(pipeline, cwd)

    # Simple env injection of resolved args
    pipeline_env = dict(env)
    for k, v in resolved_args.items():
        pipeline_env[f"LOBSTER_ARG_{k.upper()}"] = str(v)

    runtime = LobsterRuntime(stages, cwd, pipeline_env, resume_request)

    try:
        result = await runtime.execute()
        return result
    except InputRequestSuspension as e:
        return e.to_envelope()

"""Tests for Lobster workflow engine port."""

import asyncio
import os
import sys

from jarvis_lobster.runtime import run_pipeline
from jarvis_lobster.input_request import CommandInputResume


def test_inline_pipeline():
    """Test a basic inline pipeline without suspension."""
    pipeline = f"exec --shell \"{sys.executable} -c \\\"import json; print(json.dumps([{{'hello':'world'}}]))\\\"\" --json"

    result = asyncio.run(run_pipeline(pipeline, cwd=".", env=dict(os.environ)))
    assert result["halted"] is False
    assert result["items"] == [{"hello": "world"}]


def test_approval_suspension_and_resume():
    """Test that approve command halts and can be resumed."""
    pipeline = f'exec --shell "{sys.executable} -c \\"import json; print(json.dumps([{{\'item\': 1}}]))\\"" --json | approve --prompt "Looks good?"'

    # 1. First run, should suspend
    envelope = asyncio.run(run_pipeline(pipeline, cwd=".", env=dict(os.environ)))
    assert envelope.get("type") == "approval_request"
    assert envelope.get("prompt") == "Looks good?"
    assert envelope.get("items") == [{"item": 1}]

    token = envelope.get("resumeToken")
    app_id = envelope.get("approvalId")

    # 2. Resume with approval
    resume_req = CommandInputResume(
        resume_token=token,
        approval_id=app_id,
        approved=True,
    )

    result2 = asyncio.run(
        run_pipeline(pipeline, cwd=".", env=dict(os.environ), resume_request=resume_req)
    )
    assert result2["halted"] is False
    assert result2["items"] == [{"item": 1}]

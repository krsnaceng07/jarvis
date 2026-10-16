"""Pytest configuration and fixtures for Webhooks plugin tests."""

from __future__ import annotations

import importlib.abc
import importlib.util
import sys
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock
import pytest

from extensions.webhooks.src.types import FlowView, TaskView

# Ensure `extensions.webhooks` can be imported by tests
PLUGIN_ROOT = Path(__file__).resolve().parent.parent
EXTENSIONS_ROOT = PLUGIN_ROOT.parent

if str(EXTENSIONS_ROOT) not in sys.path:
    sys.path.insert(0, str(EXTENSIONS_ROOT))


class WebhooksImportFinder(importlib.abc.MetaPathFinder):
    """Bridge import finder for extensions.webhooks modules."""

    def find_spec(self, fullname: str, path: Any, target: Any = None) -> Any:
        if fullname == "extensions.webhooks":
            init_py = PLUGIN_ROOT / "__init__.py"
            return importlib.util.spec_from_file_location(
                fullname,
                str(init_py),
                submodule_search_locations=[str(PLUGIN_ROOT)],
            )
        if fullname.startswith("extensions.webhooks."):
            sub = fullname[len("extensions.webhooks.") :]
            if (PLUGIN_ROOT / "src" / f"{sub}.py").exists():
                return importlib.util.spec_from_file_location(
                    fullname,
                    str(PLUGIN_ROOT / "src" / f"{sub}.py"),
                )
            if (PLUGIN_ROOT / f"{sub}.py").exists():
                return importlib.util.spec_from_file_location(
                    fullname,
                    str(PLUGIN_ROOT / f"{sub}.py"),
                )
        return None


if not any(isinstance(f, WebhooksImportFinder) for f in sys.meta_path):
    sys.meta_path.insert(0, WebhooksImportFinder())


@pytest.fixture
def mock_task_flow() -> MagicMock:
    """Fixture providing a mock TaskFlow session runtime."""
    flow = MagicMock()
    flow.create_flow = AsyncMock(
        return_value=FlowView(
            flow_id="flow-123",
            goal="Test Goal",
            status="queued",
            revision=1,
            created_at=1000.0,
            updated_at=1000.0,
        )
    )
    flow.get_flow = AsyncMock(
        return_value=FlowView(
            flow_id="flow-123",
            goal="Test Goal",
            status="running",
            revision=2,
            created_at=1000.0,
            updated_at=1050.0,
        )
    )
    flow.list_flows = AsyncMock(
        return_value=[
            FlowView(flow_id="flow-1", goal="Goal 1", status="running", revision=1),
            FlowView(flow_id="flow-2", goal="Goal 2", status="finished", revision=3),
        ]
    )
    flow.find_latest_flow = AsyncMock(
        return_value=FlowView(
            flow_id="flow-latest", goal="Latest Goal", status="running", revision=5
        )
    )
    flow.resolve_flow = AsyncMock(
        return_value=FlowView(
            flow_id="flow-resolved", goal="Resolved Goal", status="running", revision=2
        )
    )
    flow.get_task_summary = AsyncMock(return_value={"total": 5, "running": 1, "completed": 4})
    flow.set_waiting = AsyncMock(
        return_value=FlowView(flow_id="flow-123", goal="Test Goal", status="waiting", revision=3)
    )
    flow.resume_flow = AsyncMock(
        return_value=FlowView(flow_id="flow-123", goal="Test Goal", status="running", revision=4)
    )
    flow.finish_flow = AsyncMock(
        return_value=FlowView(flow_id="flow-123", goal="Test Goal", status="finished", revision=5)
    )
    flow.fail_flow = AsyncMock(
        return_value=FlowView(flow_id="flow-123", goal="Test Goal", status="failed", revision=5)
    )
    flow.request_cancel = AsyncMock(
        return_value=FlowView(
            flow_id="flow-123",
            goal="Test Goal",
            status="running",
            revision=3,
            cancel_requested_at=1200.0,
        )
    )
    flow.cancel_flow = AsyncMock(
        return_value=FlowView(flow_id="flow-123", goal="Test Goal", status="cancelled", revision=4)
    )
    flow.run_task = AsyncMock(
        return_value=TaskView(
            task_id="task-999",
            runtime="subagent",
            task="Perform subtask",
            status="queued",
            created_at=1000.0,
        )
    )
    return flow

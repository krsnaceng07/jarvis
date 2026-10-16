"""Visitor access runtime registry."""

from __future__ import annotations

from typing import Callable

from .visitors import VisitorAccessService


class VisitorRuntime:
    def __init__(
        self, service: VisitorAccessService, error_text_fn: Callable[[Exception | str], str]
    ):
        self.service = service
        self.error_text_fn = error_text_fn

    def error_text(self, error: Exception | str) -> str:
        return self.error_text_fn(error)


class VisitorRuntimeStore:
    def __init__(self):
        self._runtime: VisitorRuntime | None = None

    def set_runtime(self, runtime: VisitorRuntime) -> None:
        self._runtime = runtime

    def try_get_runtime(self) -> VisitorRuntime | None:
        return self._runtime

    def clear_runtime(self) -> None:
        self._runtime = None


visitor_runtime_store = VisitorRuntimeStore()

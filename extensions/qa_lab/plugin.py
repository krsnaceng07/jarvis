"""Compatibility shim for ``extensions.qa_lab.plugin``."""

from __future__ import annotations

from importlib import import_module

_module = import_module("extensions.qa-lab.plugin")

QALabPlugin = _module.QALabPlugin
QALabRunResult = _module.QALabRunResult
qa_lab_plugin = _module.qa_lab_plugin
entry = _module.entry

__all__ = ["QALabPlugin", "QALabRunResult", "qa_lab_plugin", "entry"]

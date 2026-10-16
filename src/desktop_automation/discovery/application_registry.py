"""jarvis.desktop_automation.discovery.application_registry — Catalog of desktop applications."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass(slots=True)
class ApplicationMetadata:
    app_id: str
    display_name: str
    process_names: List[str]
    title_patterns: List[str]
    launch_command: Optional[str] = None
    uri_protocol: Optional[str] = None
    default_category: str = "general"


class ApplicationRegistry:
    """Registry of known desktop applications and their identification facts."""

    _apps: Dict[str, ApplicationMetadata] = {}

    @classmethod
    def register(cls, meta: ApplicationMetadata) -> None:
        cls._apps[meta.app_id.lower()] = meta

    @classmethod
    def get(cls, app_id: str) -> Optional[ApplicationMetadata]:
        return cls._apps.get(app_id.lower())

    @classmethod
    def find_by_process_or_title(cls, process_name: str, title: str) -> Optional[ApplicationMetadata]:
        p_clean = process_name.lower()
        t_clean = title.lower()
        for meta in cls._apps.values():
            if any(p.lower() in p_clean for p in meta.process_names):
                return meta
            if any(t.lower() in t_clean for t in meta.title_patterns):
                return meta
        return None


# Built-in registrations
ApplicationRegistry.register(ApplicationMetadata(
    app_id="whatsapp",
    display_name="WhatsApp Desktop",
    process_names=["WhatsApp.Root.exe", "WhatsApp.exe"],
    title_patterns=["WhatsApp"],
    uri_protocol="whatsapp:",
    default_category="messaging",
))
ApplicationRegistry.register(ApplicationMetadata(
    app_id="vscode",
    display_name="Visual Studio Code",
    process_names=["Code.exe"],
    title_patterns=["Visual Studio Code"],
    launch_command="code",
    default_category="editor",
))
ApplicationRegistry.register(ApplicationMetadata(
    app_id="antigravity",
    display_name="Antigravity IDE",
    process_names=["Antigravity IDE.exe", "Antigravity.exe"],
    title_patterns=["Antigravity"],
    default_category="editor",
))
ApplicationRegistry.register(ApplicationMetadata(
    app_id="calculator",
    display_name="Windows Calculator",
    process_names=["CalculatorApp.exe", "calc.exe"],
    title_patterns=["Calculator"],
    launch_command="calc",
    default_category="utility",
))
ApplicationRegistry.register(ApplicationMetadata(
    app_id="word",
    display_name="Microsoft Word",
    process_names=["WINWORD.EXE"],
    title_patterns=["Word", "Document"],
    launch_command="winword",
    default_category="office",
))
ApplicationRegistry.register(ApplicationMetadata(
    app_id="powerpoint",
    display_name="Microsoft PowerPoint",
    process_names=["POWERPNT.EXE"],
    title_patterns=["PowerPoint", "Presentation"],
    launch_command="powerpnt",
    default_category="office",
))
ApplicationRegistry.register(ApplicationMetadata(
    app_id="excel",
    display_name="Microsoft Excel",
    process_names=["EXCEL.EXE"],
    title_patterns=["Excel", "Book"],
    launch_command="excel",
    default_category="office",
))
ApplicationRegistry.register(ApplicationMetadata(
    app_id="settings",
    display_name="Windows Settings",
    process_names=["SystemSettings.exe"],
    title_patterns=["Settings"],
    uri_protocol="ms-settings:",
    default_category="system",
))
ApplicationRegistry.register(ApplicationMetadata(
    app_id="notepad",
    display_name="Notepad",
    process_names=["Notepad.exe"],
    title_patterns=["Notepad"],
    launch_command="notepad",
    default_category="utility",
))
ApplicationRegistry.register(ApplicationMetadata(
    app_id="explorer",
    display_name="File Explorer",
    process_names=["explorer.exe"],
    title_patterns=["File Explorer"],
    launch_command="explorer",
    default_category="system",
))

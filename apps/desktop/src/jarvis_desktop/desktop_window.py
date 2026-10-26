"""JARVIS Native Desktop Window (PyQt6 + QWebEngineView).

Embeds the modern React + TypeScript + Three.js holographic interface
directly into a native Windows desktop shell, sharing the exact same
process lifecycle with the Python voice engine and FastAPI bridge.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import Callable

from PyQt6.QtCore import QCoreApplication, Qt, QUrl
from PyQt6.QtGui import QColor, QIcon
from PyQt6.QtWebEngineCore import QWebEnginePage, QWebEngineSettings
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWidgets import QApplication, QMainWindow

if sys.platform == "win32":
    os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = (
        "--disable-gpu-watchdog --enable-gpu-rasterization --enable-zero-copy --ignore-gpu-blocklist"
    )

try:
    QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
except Exception:
    pass

_log = logging.getLogger("jarvis.desktop.window")

BASE_DIR = Path(__file__).resolve().parents[4]


class JarvisWebPage(QWebEnginePage):
    def javaScriptConsoleMessage(self, level, message, lineNumber, sourceID):
        _log.debug("[JS %s:%s] %s", sourceID, lineNumber, message)


class JarvisDesktopWebWindow(QMainWindow):
    """Native PyQt6 Desktop Window embedding the React + TypeScript Holographic HUD."""

    def __init__(
        self,
        url: str = "http://127.0.0.1:7433/",
        title: str = "JARVIS — Holographic AI Desktop",
        width: int = 1656,
        height: int = 936,
        on_close_callback: Callable[[], None] | None = None,
    ):
        super().__init__()
        self.url = url
        self.on_close_callback = on_close_callback

        self.setWindowTitle(title)
        self.resize(width, height)
        self.setMinimumSize(1024, 600)

        # Dark theme background matching HUD
        palette = self.palette()
        palette.setColor(self.backgroundRole(), QColor("#03060c"))
        self.setPalette(palette)

        # Set window icon if available
        icon_path = BASE_DIR / "face.png"
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))

        # Create WebEngineView
        self.browser = QWebEngineView(self)
        self.browser.setPage(JarvisWebPage(self.browser))
        self.setCentralWidget(self.browser)

        # Configure High-Performance WebGL & Chromium Settings
        settings = self.browser.settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.WebGLEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.Accelerated2dCanvasEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.ScrollAnimatorEnabled, True)

        # Transparent/Dark page background
        self.browser.page().setBackgroundColor(QColor("#03060c"))

        # Load UI
        _log.info("Loading JARVIS Desktop UI from %s", self.url)
        self.browser.load(QUrl(self.url))

    def closeEvent(self, event):
        """Handle window close event and propagate to backend shutdown."""
        _log.info("JARVIS Desktop window closing...")
        try:
            self.browser.stop()
            self.browser.setPage(None)
        except Exception:
            pass
        event.accept()
        qapp = QApplication.instance()
        if qapp:
            qapp.quit()


def run_desktop_window(
    url: str = "http://127.0.0.1:7433/",
    on_close: Callable[[], None] | None = None,
) -> int:
    """Run native PyQt6 application event loop hosting QWebEngineView."""
    # Ensure High-DPI scaling
    os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "1"
    os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "1"

    # Chromium flags for zero-stutter WebGL and robust DirectX swapchain shutdown
    if sys.platform == "win32":
        chrome_flags = [
            "--enable-gpu-rasterization",
            "--enable-zero-copy",
            "--ignore-gpu-blocklist",
            "--disable-gpu-watchdog",
        ]
        for flag in chrome_flags:
            if flag not in sys.argv:
                sys.argv.append(flag)

    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("JARVIS AI")
    app.setStyle("Fusion")

    window = JarvisDesktopWebWindow(url=url, on_close_callback=on_close)
    screen = app.primaryScreen()
    if screen is not None:
        work_area = screen.availableGeometry()
        # Keep the restored window inside the taskbar-aware work area too.
        window.resize(
            min(window.width(), max(1024, work_area.width() - 48)),
            min(window.height(), max(600, work_area.height() - 48)),
        )
        frame = window.frameGeometry()
        frame.moveCenter(work_area.center())
        window.move(frame.topLeft())

    # The default normal geometry is larger than common laptop work areas. Start
    # maximized so the dashboard lays out against the actual, taskbar-free viewport.
    window.showMaximized()

    ret = app.exec()
    if on_close:
        try:
            on_close()
        except Exception as e:
            _log.debug("Close callback exception: %s", e)
    return ret

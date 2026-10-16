"""Manager for Browser Extension native host installation and status."""

import os


class ExtensionManager:
    """Handles the installation, verification, and paths for the Browser extension native host."""

    def __init__(self):
        self.host_name = "ai.openclaw.browser_bootstrap"

    def install_host(self) -> dict:
        """Pre-register the native host for Chrome/Chromium."""
        if os.name == "nt":
            # Windows keeps manual pairing because Chromium only directly launches
            # native hosts if they are Windows executables, and we don't install a wrapper script yet.
            print("Notice: Windows requires manual setup. Use 'jarvis browser extension pair'.")
            return {"installed": False, "reason": "Windows manual pairing required."}

        # On Linux/macOS, we would normally write the JSON manifest to the browser's config dir
        return {"installed": False, "reason": "Not implemented for this OS yet in JARVIS."}

    def get_status(self) -> dict:
        """Get the status of the native host registration."""
        if os.name == "nt":
            return {"status": "manual_required", "message": "Windows keeps manual pairing."}

        return {"status": "unknown"}

    def uninstall_host(self) -> None:
        """Remove the native host manifest."""
        pass

    def get_extension_path(self) -> str:
        """Return the path to the extension source."""
        # For now, return a placeholder bundled path inside the extension
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        ext_dir = os.path.join(base_dir, "extension_bundle")
        return ext_dir

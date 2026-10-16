"""Pairing token storage for the Browser extension."""

import json
import os
import secrets
from typing import Optional


def get_pairing_store_path() -> str:
    """Get the path to the pairing store."""
    base_dir = os.path.join(os.path.expanduser("~"), ".jarvis", "browser")
    os.makedirs(base_dir, exist_ok=True)
    return os.path.join(base_dir, "pairing.json")


class PairingStore:
    """Manages the securely generated pairing token for browser automation."""

    def __init__(self, path: Optional[str] = None):
        self.path = path or get_pairing_store_path()

    def generate_and_save(self) -> str:
        """Generate a new pairing token and save it to the store."""
        token = secrets.token_hex(32)
        data = {"token": token}

        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(data, f)

        if os.name != "nt":
            os.chmod(self.path, 0o600)

        return token

    def load(self) -> Optional[str]:
        """Load the stored pairing token."""
        if not os.path.exists(self.path):
            return None
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("token")
        except Exception:
            return None

    def clear(self) -> None:
        """Remove the stored token."""
        if os.path.exists(self.path):
            try:
                os.remove(self.path)
            except OSError:
                pass

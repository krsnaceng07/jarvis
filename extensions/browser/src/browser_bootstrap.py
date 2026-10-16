"""Native messaging host payload for browser extension bootstrap.

Reads length-prefixed JSON from Chrome on stdin, returns pairing token on stdout.
"""

import sys
import json
import struct
from .pairing_store import PairingStore


def _send_message(msg: dict) -> None:
    """Send length-prefixed JSON message to stdout."""
    encoded_msg = json.dumps(msg).encode("utf-8")
    sys.stdout.buffer.write(struct.pack("@I", len(encoded_msg)))
    sys.stdout.buffer.write(encoded_msg)
    sys.stdout.buffer.flush()


def _read_message() -> dict:
    """Read length-prefixed JSON message from stdin."""
    text_length_bytes = sys.stdin.buffer.read(4)
    if len(text_length_bytes) == 0:
        sys.exit(0)

    text_length = struct.unpack("@I", text_length_bytes)[0]
    if text_length > 4096:
        # Cap input at 4 KiB
        sys.exit(1)

    text = sys.stdin.buffer.read(text_length).decode("utf-8")
    return json.loads(text)


def main() -> None:
    """Main native host entry point."""
    try:
        _ = _read_message()
        # Expecting something like {"nonce": "..."}

        store = PairingStore()
        token = store.generate_and_save()

        # Chrome native messaging expects a JSON response
        _send_message({"pairingToken": token, "success": True})

    except Exception as e:
        _send_message({"error": str(e), "success": False})
        sys.exit(1)


if __name__ == "__main__":
    main()

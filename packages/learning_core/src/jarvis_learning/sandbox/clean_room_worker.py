"""Clean-room worker process script executed under restricted token and Job Object constraints.

Operates as an isolated child worker to provide empirical proof of:
- Process token privileges and integrity level from INSIDE the sandbox
- Sanitized environment variables (absence of host secrets)
- Restricted filesystem and network access from child context
"""

from __future__ import annotations

import argparse
import json
import sys

from jarvis_learning.sandbox.credential_guard import CredentialGuard
from jarvis_learning.sandbox.win32_token import Win32TokenEngine


def main() -> int:
    parser = argparse.ArgumentParser(description="JARVIS Sandbox Clean-Room Worker")
    parser.add_argument(
        "--mode", choices=["snapshot", "probe-creds", "probe-env"], default="snapshot"
    )
    args = parser.parse_args()

    if args.mode == "snapshot":
        snap = Win32TokenEngine.snapshot_current_process()
        payload = snap.to_dict()
        print(json.dumps(payload))
        return 0

    if args.mode == "probe-creds":
        probe = CredentialGuard.probe_windows_credential_manager()
        print(json.dumps(probe.to_dict()))
        return 0

    if args.mode == "probe-env":
        probe = CredentialGuard.probe_environment_secrets()
        print(json.dumps(probe.to_dict()))
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())

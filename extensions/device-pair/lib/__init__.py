"""Device Pair plugin internal module.

Mirrors OpenClaw's ``extensions/device-pair/`` package.
The Python port ships the foundational subset
(pairing QR channel data, pair-command auth, pair-command
approve, notify state). The full entrypoint
(``index.ts``), notify flow, and SDK surface land in
follow-up commits.

The directory is named ``lib/`` (not ``src/``) to avoid
the namespace collision with the JARVIS root
``src/`` package.
"""

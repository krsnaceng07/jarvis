# JARVIS deployment

Deployment configurations. JARVIS is primarily a local desktop app, so deployment
configs are minimal — a Docker image for headless gateway mode, a systemd / launchd
service file for the daemon, and a `fly.toml` for the optional cloud relay.

## Layout

```
deploy/
├── README.md
├── Dockerfile             # headless gateway image (Phase 12)
├── docker-compose.yml     # gateway + companion services (Phase 12)
├── fly.toml               # optional cloud relay (Phase 12)
└── systemd/
    └── jarvis.service     # Linux daemon (Phase 12)
```

## Phasing

- **Phase 0.3 (now):** empty placeholder.
- **Phase 12:** Docker + systemd + fly.toml land.

## Rules

- Deployment configs are part of the release artifact, not the runtime.
- Docker images must be reproducible (pinned `uv.lock` + Python version).
- Systemd / launchd service files must respect the same env vars as
  `apps/desktop/` and `apps/cli/`.

# JARVIS web UI (optional)

Optional web frontend. FastAPI + htmx/lit, served alongside the gateway for
headless mode or remote clients.

Mirrors OpenClaw's `ui/` (Lit components, web app).

## Layout

```
ui/
├── README.md
├── pyproject.toml
├── src/jarvis_ui/
│   ├── __init__.py
│   ├── app.py            # FastAPI app
│   ├── api.py            # REST + WebSocket endpoints
│   ├── static/
│   ├── templates/
│   └── pages/
└── tests/
```

## Phasing

- **Phase 0.3 (now):** empty placeholder.
- **Phase 12:** web UI lands as a thin client over `packages/gateway_protocol/`.

## Rules

- Web UI is a thin client; the gateway is the source of truth.
- No business logic in `ui/`; it calls the gateway's JSON-RPC API.
- Static assets (CSS, JS) are served by FastAPI; no separate CDN.

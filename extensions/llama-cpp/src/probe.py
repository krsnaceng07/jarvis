"""Server probing, health inspection, and live model discovery for llama-server."""

from __future__ import annotations

import json
import urllib.parse
from dataclasses import dataclass, field
from typing import Any

from jarvis_sdk import Err, Ok, Result


@dataclass(slots=True)
class ServerProbeResult:
    is_healthy: bool
    status_code: int
    is_loading: bool = False  # True if HTTP 503
    models: list[dict[str, Any]] = field(default_factory=list)
    server_props: dict[str, Any] = field(default_factory=dict)
    error_message: str | None = None


def validate_endpoint_url(url: str | None) -> Result[str, str]:
    """Validate server base URL. Rejects URLs with embedded user credentials."""
    if not url or not str(url).strip():
        return Err("Server endpoint URL is required")

    clean_url = str(url).strip()
    if not clean_url.startswith("http://") and not clean_url.startswith("https://"):
        clean_url = f"http://{clean_url}"

    try:
        parsed = urllib.parse.urlparse(clean_url)
    except Exception as ex:
        return Err(f"Invalid server endpoint URL: {ex}")

    if parsed.username or parsed.password:
        return Err(
            "Endpoint URLs containing username or password credentials in the authority are rejected"
        )

    # Normalize trailing slash
    return Ok(clean_url.rstrip("/"))


def resolve_auth_headers(
    *,
    api_key: str | None = None,
    explicit_auth_header: str | None = None,
    extra_headers: dict[str, str] | None = None,
) -> dict[str, str]:
    """Construct request headers with authentication precedence."""
    headers = dict(extra_headers or {})

    # Explicit Authorization header wins
    if explicit_auth_header:
        headers["Authorization"] = explicit_auth_header.strip()
    elif api_key and api_key.strip():
        headers["Authorization"] = f"Bearer {api_key.strip()}"

    return headers


async def probe_llama_server(
    base_url: str,
    *,
    api_key: str | None = None,
    explicit_headers: dict[str, str] | None = None,
    client: Any = None,
    mock_responses: dict[str, Any] | None = None,
) -> Result[ServerProbeResult, str]:
    """Probe /health, /models (fallback /v1/models), and /props with autoload=false."""
    val_res = validate_endpoint_url(base_url)
    if not val_res.is_ok:
        return Err(str(val_res.error))

    endpoint = val_res.unwrap()
    headers = resolve_auth_headers(api_key=api_key, extra_headers=explicit_headers)

    # Use mock responses if provided (for offline testing and verification)
    if mock_responses is not None:
        health_resp = mock_responses.get("/health", {"status": 200})
        status_code = int(health_resp.get("status", 200))
        if status_code == 503:
            return Ok(
                ServerProbeResult(
                    is_healthy=False,
                    status_code=503,
                    is_loading=True,
                    error_message="llama-server model is still loading (HTTP 503)",
                )
            )

        if status_code != 200:
            return Ok(
                ServerProbeResult(
                    is_healthy=False,
                    status_code=status_code,
                    error_message=f"Server returned unhealthy status HTTP {status_code}",
                )
            )

        models_resp = (
            mock_responses.get("/models") or mock_responses.get("/v1/models") or {"data": []}
        )
        models_data = models_resp.get("data", []) if isinstance(models_resp, dict) else []
        props_data = mock_responses.get("/props", {})

        return Ok(
            ServerProbeResult(
                is_healthy=True,
                status_code=200,
                is_loading=False,
                models=models_data,
                server_props=props_data,
            )
        )

    # Live network probe via standard urllib/aiohttp if available
    try:
        import urllib.request

        health_url = f"{endpoint}/health"
        req = urllib.request.Request(health_url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=5.0) as resp:
                status_code = resp.getcode()
        except urllib.error.HTTPError as http_err:
            if http_err.code == 503:
                return Ok(
                    ServerProbeResult(
                        is_healthy=False,
                        status_code=503,
                        is_loading=True,
                        error_message="Model is still loading (HTTP 503)",
                    )
                )
            return Ok(
                ServerProbeResult(
                    is_healthy=False,
                    status_code=http_err.code,
                    error_message=f"Health probe failed: HTTP {http_err.code}",
                )
            )

        # Query models
        models_url = f"{endpoint}/models"
        models_list: list[dict[str, Any]] = []
        try:
            req_m = urllib.request.Request(models_url, headers=headers)
            with urllib.request.urlopen(req_m, timeout=5.0) as resp_m:
                data = json.loads(resp_m.read().decode("utf-8"))
                models_list = data.get("data", []) if isinstance(data, dict) else []
        except Exception:
            # Fallback to /v1/models
            v1_url = f"{endpoint}/v1/models"
            try:
                req_v1 = urllib.request.Request(v1_url, headers=headers)
                with urllib.request.urlopen(req_v1, timeout=5.0) as resp_v1:
                    data = json.loads(resp_v1.read().decode("utf-8"))
                    models_list = data.get("data", []) if isinstance(data, dict) else []
            except Exception:
                pass

        # Query /props with autoload=false
        props_url = f"{endpoint}/props?autoload=false"
        props_data: dict[str, Any] = {}
        try:
            req_p = urllib.request.Request(props_url, headers=headers)
            with urllib.request.urlopen(req_p, timeout=5.0) as resp_p:
                props_data = json.loads(resp_p.read().decode("utf-8"))
        except Exception:
            pass

        return Ok(
            ServerProbeResult(
                is_healthy=status_code == 200,
                status_code=status_code,
                models=models_list,
                server_props=props_data,
            )
        )
    except Exception as ex:
        return Err(f"Failed to connect to llama-server at {endpoint}: {ex}")

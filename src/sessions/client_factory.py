"""Small SDK client factory that constructs common provider clients
using registry-resolved credentials (best-effort). This centralizes
credential wiring so callers can rely on `resolve_credentials(...)`.

Only attempts to import provider SDKs if available and returns a
ready-to-use client or raises ImportError if the SDK is missing.
"""
from __future__ import annotations

from typing import Any, Optional

from src.sessions.credentials import resolve_credentials


def _extract_api_key(cred: Any) -> Optional[str]:
    if cred is None:
        return None
    if isinstance(cred, str):
        return cred
    if isinstance(cred, dict):
        return cred.get("api_key") or cred.get("key") or cred.get("token")
    return None


def create_google_client(model: str, provider: str = "google") -> Any:
    """Return a configured `google.generativeai` client wrapper.

    Returns the `GenerativeModel` instance for the requested model.
    """
    try:
        import google.generativeai as genai  # type: ignore
    except Exception as e:  # pragma: no cover - depends on env
        raise ImportError("google.generativeai is not installed") from e

    cred = resolve_credentials(provider=provider, model=model)
    api_key = _extract_api_key(cred)
    if api_key:
        genai.configure(api_key=api_key)
    # genai will still work if application-default creds are present
    return genai.GenerativeModel(model)


def create_openai_client(model: Optional[str] = None, provider: str = "openai") -> Any:
    try:
        import openai  # type: ignore
    except Exception as e:  # pragma: no cover
        raise ImportError("openai SDK not installed") from e

    cred = resolve_credentials(provider=provider, model=model)
    api_key = _extract_api_key(cred)
    if api_key:
        # OpenAI Python SDK accepts `api_key` via OpenAI class or env
        return openai.OpenAI(api_key=api_key)
    return openai.OpenAI()


def create_anthropic_client(model: Optional[str] = None, provider: str = "anthropic") -> Any:
    try:
        import anthropic  # type: ignore
    except Exception as e:  # pragma: no cover
        raise ImportError("anthropic SDK not installed") from e

    cred = resolve_credentials(provider=provider, model=model)
    api_key = _extract_api_key(cred)
    if api_key:
        return anthropic.Client(api_key=api_key)
    return anthropic.Client()


def create_cohere_client(model: Optional[str] = None, provider: str = "cohere") -> Any:
    try:
        import cohere  # type: ignore
    except Exception as e:  # pragma: no cover
        raise ImportError("cohere SDK not installed") from e

    cred = resolve_credentials(provider=provider, model=model)
    api_key = _extract_api_key(cred)
    if api_key:
        return cohere.Client(api_key)
    return cohere.Client()


def _extract_aws_keys(cred: Any) -> dict[str, Optional[str]]:
    """Normalize common AWS credential shapes from the registry entry.

    Accepts strings (token), dicts with common keys, and returns a dict
    with the keys boto3.Session expects.
    """
    out = {
        "aws_access_key_id": None,
        "aws_secret_access_key": None,
        "aws_session_token": None,
    }
    if cred is None:
        return out
    if isinstance(cred, str):
        # Token-like credentials are not directly usable for boto3 session
        return out
    if isinstance(cred, dict):
        # common shapes
        out["aws_access_key_id"] = (
            cred.get("aws_access_key_id")
            or cred.get("access_key")
            or cred.get("accessKey")
            or cred.get("key")
        )
        out["aws_secret_access_key"] = (
            cred.get("aws_secret_access_key")
            or cred.get("secret_key")
            or cred.get("secret")
            or cred.get("secretKey")
        )
        out["aws_session_token"] = cred.get("aws_session_token") or cred.get("session_token") or cred.get("token")
    return out


def create_aws_session(region: Optional[str] = None, provider: str = "amazon-bedrock") -> Any:
    """Create a `boto3.Session` using registry-resolved credentials when available.

    Returns a boto3.Session instance. If no registry credentials found,
    returns a default session (which uses environment or instance role).
    """
    try:
        import boto3  # type: ignore
    except Exception as e:  # pragma: no cover
        raise ImportError("boto3 not installed") from e

    cred = resolve_credentials(provider=provider, model=None)
    keys = _extract_aws_keys(cred)
    if keys["aws_access_key_id"] and keys["aws_secret_access_key"]:
        return boto3.Session(
            aws_access_key_id=keys["aws_access_key_id"],
            aws_secret_access_key=keys["aws_secret_access_key"],
            aws_session_token=keys.get("aws_session_token"),
            region_name=region,
        )
    # Fallback to default session (env / instance profile)
    return boto3.Session(region_name=region)


def create_aws_client(
    service: str,
    region: Optional[str] = None,
    provider: str = "amazon-bedrock",
    **_kwargs: Any,
) -> Any:
    """Create a boto3 client for `service`, wiring registry credentials when available."""
    session = create_aws_session(region=region, provider=provider)
    return session.client(service)

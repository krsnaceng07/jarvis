"""Google Meet plugin module implements oauth behavior."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import http.server
import secrets
import threading
import time
import urllib.parse
from dataclasses import dataclass, field
from typing import Any, Callable
import httpx

from jarvis_sdk import Err, Ok, Result

from .google_api_errors import read_google_api_error_detail

GOOGLE_MEET_REDIRECT_URI = "http://localhost:8085/oauth2callback"
GOOGLE_MEET_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_MEET_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_MEET_DEFAULT_TOKEN_LIFETIME_SECONDS = 3600
GOOGLE_OAUTH_REQUEST_TIMEOUT_MS = 30000
GOOGLE_MEET_SCOPES = [
    "https://www.googleapis.com/auth/meetings.space.created",
    "https://www.googleapis.com/auth/meetings.space.readonly",
    "https://www.googleapis.com/auth/meetings.space.settings",
    "https://www.googleapis.com/auth/meetings.conference.media.readonly",
    "https://www.googleapis.com/auth/calendar.events.readonly",
    "https://www.googleapis.com/auth/drive.meet.readonly",
]


def generate_pkce_challenge() -> dict[str, str]:
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode("utf-8")).digest()
    challenge = base64.urlsafe_b64encode(digest).decode("utf-8").rstrip("=")
    return {"verifier": verifier, "challenge": challenge}


def generate_pkce_state() -> str:
    return secrets.token_urlsafe(32)


def resolve_google_meet_token_expires_at(value: Any, now_ms: int | None = None) -> int:
    now = int(time.time() * 1000) if now_ms is None else now_ms
    if isinstance(value, (int, float)) and value <= 0:
        return now
    duration_s = (
        int(value)
        if isinstance(value, (int, float))
        else GOOGLE_MEET_DEFAULT_TOKEN_LIFETIME_SECONDS
    )
    return now + (duration_s * 1000)


@dataclass(slots=True)
class GoogleMeetOAuthTokens:
    access_token: str
    expires_at: int
    refresh_token: str | None = None
    scope: str | None = None
    token_type: str | None = None


def build_google_meet_auth_url(
    *,
    client_id: str,
    challenge: str,
    state: str,
    redirect_uri: str | None = None,
    scopes: list[str] | None = None,
) -> str:
    params = {
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": redirect_uri or GOOGLE_MEET_REDIRECT_URI,
        "scope": " ".join(scopes or GOOGLE_MEET_SCOPES),
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
    }
    return f"{GOOGLE_MEET_AUTH_URL}?{urllib.parse.urlencode(params)}"


async def execute_google_token_request(
    body: dict[str, str],
) -> GoogleMeetOAuthTokens:
    headers = {
        "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
        "Accept": "application/json",
    }
    async with httpx.AsyncClient(timeout=GOOGLE_OAUTH_REQUEST_TIMEOUT_MS / 1000.0) as client:
        response = await client.post(GOOGLE_MEET_TOKEN_URL, data=body, headers=headers)
        if response.status_code >= 400:
            detail = await read_google_api_error_detail(response)
            raise RuntimeError(
                f"Google OAuth token request failed ({response.status_code}): {detail}"
            )
        try:
            payload = response.json()
        except Exception as err:
            raise RuntimeError(f"Failed to parse Google OAuth token response: {err}") from err

        access_token = str(payload.get("access_token", "")).strip()
        if not access_token:
            raise RuntimeError("Google OAuth token response was missing access_token")

        expires_in = payload.get("expires_in")
        expires_at = resolve_google_meet_token_expires_at(expires_in)
        refresh_token = (
            str(payload["refresh_token"]).strip() if payload.get("refresh_token") else None
        )
        scope = str(payload["scope"]).strip() if payload.get("scope") else None
        token_type = str(payload["token_type"]).strip() if payload.get("token_type") else None

        return GoogleMeetOAuthTokens(
            access_token=access_token,
            expires_at=expires_at,
            refresh_token=refresh_token,
            scope=scope,
            token_type=token_type,
        )


async def exchange_google_meet_auth_code(
    *,
    client_id: str,
    client_secret: str | None = None,
    code: str,
    verifier: str,
    redirect_uri: str | None = None,
) -> GoogleMeetOAuthTokens:
    body = {
        "client_id": client_id,
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": redirect_uri or GOOGLE_MEET_REDIRECT_URI,
        "code_verifier": verifier,
    }
    if client_secret and client_secret.strip():
        body["client_secret"] = client_secret.strip()
    return await execute_google_token_request(body)


async def refresh_google_meet_access_token(
    *,
    client_id: str,
    client_secret: str | None = None,
    refresh_token: str,
) -> GoogleMeetOAuthTokens:
    body = {
        "client_id": client_id,
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
    }
    if client_secret and client_secret.strip():
        body["client_secret"] = client_secret.strip()
    return await execute_google_token_request(body)


def should_use_cached_google_meet_access_token(
    *,
    access_token: str | None = None,
    expires_at: int | None = None,
    now: int | None = None,
    safety_window_ms: int = 60000,
) -> bool:
    now_ms = int(time.time() * 1000) if now is None else now
    return bool(
        access_token
        and access_token.strip()
        and isinstance(expires_at, (int, float))
        and expires_at > (now_ms + safety_window_ms)
    )


@dataclass(slots=True)
class ResolvedGoogleMeetAccessToken:
    access_token: str
    expires_at: int | None
    refreshed: bool


async def resolve_google_meet_access_token(
    *,
    client_id: str | None = None,
    client_secret: str | None = None,
    refresh_token: str | None = None,
    access_token: str | None = None,
    expires_at: int | None = None,
) -> ResolvedGoogleMeetAccessToken:
    if should_use_cached_google_meet_access_token(access_token=access_token, expires_at=expires_at):
        return ResolvedGoogleMeetAccessToken(
            access_token=access_token.strip(),  # type: ignore[union-attr]
            expires_at=expires_at,
            refreshed=False,
        )
    if not client_id or not client_id.strip() or not refresh_token or not refresh_token.strip():
        raise RuntimeError(
            "Missing Google Meet OAuth credentials. Configure oauth.clientId and oauth.refreshToken, or pass --client-id and --refresh-token."
        )
    refreshed = await refresh_google_meet_access_token(
        client_id=client_id.strip(),
        client_secret=client_secret.strip() if client_secret else None,
        refresh_token=refresh_token.strip(),
    )
    return ResolvedGoogleMeetAccessToken(
        access_token=refreshed.access_token,
        expires_at=refreshed.expires_at,
        refreshed=True,
    )


def parse_oauth_callback_input(
    raw_input: str,
    error_messages: dict[str, str] | None = None,
) -> dict[str, str]:
    msgs = error_messages or {}
    trimmed = raw_input.strip()
    if not trimmed:
        return {"error": msgs.get("invalidInput", "Invalid redirect URL input")}
    try:
        if "?" in trimmed:
            query_str = trimmed.split("?", 1)[1]
        else:
            query_str = trimmed
        params = urllib.parse.parse_qs(query_str)
        code = params.get("code", [""])[0]
        state = params.get("state", [""])[0]
        if not state:
            return {"error": msgs.get("missingState", "Missing state parameter")}
        if not code:
            return {"error": msgs.get("invalidInput", "Missing code parameter")}
        return {"code": code, "state": state}
    except Exception as err:
        return {"error": f"Failed to parse redirect URL: {err}"}


async def read_manual_google_meet_auth_code(
    *,
    state: str,
    prompt_input: Callable[[str], Any],
) -> str:
    res = prompt_input("Paste the full redirect URL here: ")
    input_str = await res if asyncio.iscoroutine(res) else res
    parsed = parse_oauth_callback_input(
        input_str,
        {
            "missingState": "Missing 'state' parameter. Paste the full redirect URL.",
            "invalidInput": "Paste the full redirect URL, not just the code.",
        },
    )
    if "error" in parsed:
        raise RuntimeError(parsed["error"])
    if parsed.get("state") != state:
        raise RuntimeError("OAuth state mismatch - please try again")
    return parsed["code"]


async def wait_for_google_meet_auth_code(
    *,
    state: str,
    manual: bool,
    timeout_ms: int,
    auth_url: str,
    prompt_input: Callable[[str], Any],
    write_line: Callable[[str], None],
) -> str:
    write_line(f"Open this URL in your browser:\n\n{auth_url}\n")
    if manual:
        return await read_manual_google_meet_auth_code(
            state=state,
            prompt_input=prompt_input,
        )

    callback_code: str | None = None
    callback_error: str | None = None
    loop = asyncio.get_running_loop()
    event = asyncio.Event()

    class OAuthCallbackHandler(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            nonlocal callback_code, callback_error
            try:
                parsed = urllib.parse.urlparse(self.path)
                params = urllib.parse.parse_qs(parsed.query)
                req_state = params.get("state", [""])[0]
                req_code = params.get("code", [""])[0]
                if req_state != state:
                    callback_error = "OAuth state mismatch"
                    self.send_response(400)
                    self.end_headers()
                    self.wfile.write(b"OAuth state mismatch")
                elif not req_code:
                    callback_error = "Missing code"
                    self.send_response(400)
                    self.end_headers()
                    self.wfile.write(b"Missing code")
                else:
                    callback_code = req_code
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html")
                    self.end_headers()
                    self.wfile.write(
                        b"<html><body><h1>Google Meet OAuth complete</h1><p>You can close this tab.</p></body></html>"
                    )
            except Exception as e:
                callback_error = str(e)
            finally:
                loop.call_soon_threadsafe(event.set)

        def log_message(self, format: str, *args: Any) -> None:
            pass

    server: http.server.HTTPServer | None = None
    try:
        server = http.server.HTTPServer(("127.0.0.1", 8085), OAuthCallbackHandler)
        server_thread = threading.Thread(target=server.handle_request, daemon=True)
        server_thread.start()
        try:
            await asyncio.wait_for(event.wait(), timeout=timeout_ms / 1000.0)
            if callback_error:
                raise RuntimeError(callback_error)
            if callback_code:
                return callback_code
        except asyncio.TimeoutError:
            write_line("Local callback server timed out. Switching to manual mode...")
        finally:
            server.server_close()
    except Exception as e:
        write_line(f"Local callback server failed: {e}. Switching to manual mode...")

    return await read_manual_google_meet_auth_code(
        state=state,
        prompt_input=prompt_input,
    )


@dataclass(slots=True)
class GoogleMeetOAuthCredentials:
    access_token: str
    refresh_token: str | None = None
    expires_at: int | None = None
    scopes: list[str] = field(default_factory=list)


async def perform_google_meet_oauth_flow(
    *,
    client_id: str,
    client_secret: str | None = None,
    manual_code_prompt: bool = False,
    redirect_uri: str | None = None,
    scopes: list[str] | None = None,
    prompt_input: Callable[[str], Any] | None = None,
    write_line: Callable[[str], None] | None = None,
) -> Result[GoogleMeetOAuthCredentials, str]:
    pkce = generate_pkce_challenge()
    state = generate_pkce_state()
    auth_url = build_google_meet_auth_url(
        client_id=client_id,
        challenge=pkce["challenge"],
        state=state,
        redirect_uri=redirect_uri,
        scopes=scopes,
    )
    p_input = prompt_input or (lambda prompt: input(prompt))
    w_line = write_line or (lambda msg: print(msg))

    try:
        code = await wait_for_google_meet_auth_code(
            state=state,
            manual=manual_code_prompt,
            timeout_ms=120000,
            auth_url=auth_url,
            prompt_input=p_input,
            write_line=w_line,
        )
        tokens = await exchange_google_meet_auth_code(
            client_id=client_id,
            client_secret=client_secret,
            code=code,
            code_verifier=pkce["verifier"],
            redirect_uri=redirect_uri or GOOGLE_MEET_REDIRECT_URI,
        )
        return Ok(
            GoogleMeetOAuthCredentials(
                access_token=tokens.access_token,
                refresh_token=tokens.refresh_token,
                expires_at=tokens.expires_at,
                scopes=tokens.scope.split() if tokens.scope else GOOGLE_MEET_SCOPES,
            )
        )
    except Exception as e:
        return Err(str(e))


async def refresh_google_meet_oauth_token(
    *,
    client_id: str,
    client_secret: str | None = None,
    refresh_token: str,
) -> Result[GoogleMeetOAuthCredentials, str]:
    try:
        tokens = await refresh_google_meet_access_token(
            client_id=client_id,
            client_secret=client_secret,
            refresh_token=refresh_token,
        )
        return Ok(
            GoogleMeetOAuthCredentials(
                access_token=tokens.access_token,
                refresh_token=tokens.refresh_token or refresh_token,
                expires_at=tokens.expires_at,
                scopes=tokens.scope.split() if tokens.scope else GOOGLE_MEET_SCOPES,
            )
        )
    except Exception as e:
        return Err(str(e))

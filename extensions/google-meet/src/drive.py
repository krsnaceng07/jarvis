"""Google Drive API export helpers for meeting transcripts and notes."""

from __future__ import annotations

import re
import urllib.parse
from typing import Any
import httpx

from jarvis_sdk import Err, Ok, Result

from .google_api_errors import GoogleApiError, google_api_error

GOOGLE_DRIVE_API_BASE_URL = "https://www.googleapis.com/drive/v3"
GOOGLE_DRIVE_API_HOST = "www.googleapis.com"
GOOGLE_DRIVE_MEET_SCOPE = "https://www.googleapis.com/auth/drive.meet.readonly"
GOOGLE_DRIVE_REQUEST_TIMEOUT_MS = 30000
TEXT_PLAIN_MIME = "text/plain"


def extract_google_drive_document_id(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    trimmed = value.strip()
    if not trimmed:
        return None
    if trimmed.lower().startswith(("http://", "https://")):
        try:
            parsed = urllib.parse.urlparse(trimmed)
            match = re.search(r"/document/d/([^/]+)", parsed.path)
            if match:
                return match.group(1)
            return None
        except Exception:
            return None
    segments = [s for s in trimmed.split("/") if s]
    return segments[-1] if segments else None


async def export_google_drive_document_text(
    *,
    access_token: str,
    document_id: str,
) -> str:
    encoded_id = urllib.parse.quote(document_id, safe="")
    url = f"{GOOGLE_DRIVE_API_BASE_URL}/files/{encoded_id}/export?mimeType=text%2Fplain"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": TEXT_PLAIN_MIME,
    }
    async with httpx.AsyncClient(timeout=GOOGLE_DRIVE_REQUEST_TIMEOUT_MS / 1000.0) as client:
        response = await client.get(url, headers=headers)
        if response.status_code >= 400:
            raise await google_api_error(
                response=response,
                prefix="Google Drive files.export",
                scopes=[GOOGLE_DRIVE_MEET_SCOPE],
            )
        return response.text


async def export_drive_file_text(
    *,
    token: str,
    file_id: str,
) -> Result[str, GoogleApiError]:
    """Result-wrapped export helper for Google Drive text documents."""
    try:
        text = await export_google_drive_document_text(access_token=token, document_id=file_id)
        return Ok(text)
    except GoogleApiError as e:
        return Err(e)
    except Exception as e:
        return Err(GoogleApiError(message=str(e), status_code=500))

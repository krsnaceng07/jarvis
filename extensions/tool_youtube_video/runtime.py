"""Runtime helpers for tool_youtube_video.

Phase 1C: the heavy scrapers + summarizer. The plugin dispatches on
``action`` (play | summarize | get_info | trending); each handler
calls into this module.

Mirrors OpenClaw's per-extension ``runtime.ts`` pattern.
"""

# ruff: noqa: S603, S607, S110, SIM105
# - S603: `subprocess.Popen` is called with a list-form command and
#   a fixed executable (`open`, `xdg-open`, `cmd /c start`). No user
#   input flows into the command string.
# - S607: `open` (macOS) and `xdg-open` (Linux) are intentional PATH
#   lookups; `notepad.exe` and the `cmd /c start` (Windows) are
#   system binaries.
# - S110: `try/except/pass` is intentional — transcript-language
#   fallback is "try manual, then generated, then any".
# - SIM105: same; `contextlib.suppress` would change behavior (we
#   need the inner block's success/failure to drive the next block).
from __future__ import annotations

import re
import subprocess
import sys
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import simpledialog
from typing import Any, cast
from urllib.parse import quote_plus

import requests  # type: ignore[import-not-found]

from config import is_linux, is_mac, is_windows  # type: ignore[import-not-found]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

_YT_VIDEO_FILTER = "EgIQAQ%3D%3D"


# ── URL helpers ───────────────────────────────────────────────────


def _open_url(url: str) -> None:
    try:
        if is_mac():
            subprocess.Popen(["open", url])
        elif is_linux():
            subprocess.Popen(["xdg-open", url])
        else:
            subprocess.Popen(["cmd", "/c", "start", "", url], shell=False)
    except Exception as e:
        print(f"[YouTube] open_url failed: {e}")


def extract_video_id(url: str) -> str | None:
    match = re.search(r"(?:v=|\/v\/|youtu\.be\/|\/embed\/|\/shorts\/)([A-Za-z0-9_-]{11})", url)
    return match.group(1) if match else None


def is_valid_youtube_url(url: str) -> bool:
    return bool(re.search(r"(youtube\.com|youtu\.be)", url or ""))


def _ask_for_url(prompt_text: str = "YouTube video URL:") -> str | None:
    try:
        root = tk._default_root  # type: ignore[attr-defined]
        if root is None:
            root = tk.Tk()
            root.withdraw()
        url = simpledialog.askstring("J.A.R.V.I.S", prompt_text, parent=cast("Any", root))
        return url.strip() if url else None
    except Exception as e:
        print(f"[YouTube] URL dialog failed: {e}")
        return None


# ── Scraper primitives ────────────────────────────────────────────


def scrape_first_video_url(query: str) -> str | None:
    """Scrape YouTube search results; return the first non-Shorts video URL."""
    search_url = (
        f"https://www.youtube.com/results"
        f"?search_query={quote_plus(query)}"
        f"&sp={_YT_VIDEO_FILTER}"
    )
    try:
        r = requests.get(search_url, headers=HEADERS, timeout=10)
        html = r.text
        video_ids = re.findall(r'"videoId":"([A-Za-z0-9_-]{11})"', html)
        seen: set[str] = set()
        for vid in video_ids:
            if vid in seen:
                continue
            seen.add(vid)
            if f"/shorts/{vid}" in html:
                continue
            return f"https://www.youtube.com/watch?v={vid}"
    except Exception as e:
        print(f"[YouTube] scrape_first_video_url failed: {e}")
    return None


def scrape_video_info(video_id: str) -> dict[str, object]:
    url = f"https://www.youtube.com/watch?v={video_id}"
    try:
        r = requests.get(url, headers=HEADERS, timeout=12)
        html = r.text
        info: dict[str, object] = {}
        for key, pattern in [
            ("title", r'"title":\{"runs":\[\{"text":"([^"]+)"'),
            ("channel", r'"ownerChannelName":"([^"]+)"'),
            ("views", r'"viewCount":"(\d+)"'),
            ("duration", r'"lengthSeconds":"(\d+)"'),
            ("likes", r'"label":"([0-9,]+ likes)"'),
        ]:
            match = re.search(pattern, html)
            if not match:
                continue
            raw = match.group(1)
            if key == "views":
                info[key] = f"{int(raw):,}"
            elif key == "duration":
                secs = int(raw)
                info[key] = f"{secs // 60}:{secs % 60:02d}"
            else:
                info[key] = raw
        return info
    except Exception as e:
        print(f"[YouTube] info scrape failed: {e}")
        return cast("dict[str, object]", {})


def scrape_trending(region: str = "TR", max_results: int = 8) -> list[dict[str, object]]:
    url = f"https://www.youtube.com/feed/trending?gl={region.upper()}"
    try:
        r = requests.get(url, headers=HEADERS, timeout=12)
        html = r.text
        titles = re.findall(r'"title":\{"runs":\[\{"text":"([^"]+)"\}\]', html)
        channels = re.findall(r'"ownerText":\{"runs":\[\{"text":"([^"]+)"', html)
        results: list[dict[str, object]] = []
        seen: set[str] = set()
        for i, title in enumerate(titles):
            if title in seen or len(title) < 5:
                continue
            seen.add(title)
            channel = channels[i] if i < len(channels) else "Unknown"
            entry: dict[str, object] = {
                "rank": len(results) + 1,
                "title": title,
                "channel": channel,
            }
            results.append(entry)
            if len(results) >= max_results:
                break
        return results
    except Exception as e:
        print(f"[YouTube] trending scrape failed: {e}")
        return []


# ── Transcript + summarization ────────────────────────────────────


def get_transcript(video_id: str) -> str | None:
    try:
        from youtube_transcript_api import YouTubeTranscriptApi  # type: ignore[import-not-found]
    except ImportError:
        return None
    try:
        api: Any = YouTubeTranscriptApi
        transcript_list: Any = api.list_transcripts(video_id)
        transcript: Any = None
        lang_priority = [
            "en",
            "tr",
            "de",
            "fr",
            "es",
            "it",
            "pt",
            "ru",
            "ja",
            "ko",
            "ar",
            "zh",
        ]
        try:
            transcript = transcript_list.find_manually_created_transcript(lang_priority)
        except Exception:
            pass
        if transcript is None:
            try:
                transcript = transcript_list.find_generated_transcript(lang_priority)
            except Exception:
                for t in transcript_list:
                    transcript = t
                    break
        if transcript is None:
            return None
        fetched: Any = transcript.fetch()
        return " ".join(str(entry["text"]) for entry in fetched)
    except Exception as e:
        print(f"[YouTube] transcript fetch failed: {e}")
        return None


def summarize_with_or(transcript: str, video_url: str) -> str:
    """Return the first ~1500 chars of the transcript as a "summary".

    Phase 3.5: the legacy OpenRouter-based summarization is gone
    (no LLM client in the host runtime; OpenClaw doesn't ship
    one). We return a deterministic first-chars extraction with
    a truncation marker so the operator can read the start of the
    transcript. The full transcript is also available via the
    `get_transcript` action; the LLM in the host can read it
    directly when it wants a real summary.
    """
    _ = video_url  # kept for signature stability
    budget = 1500
    if len(transcript) <= budget:
        return transcript
    head = transcript[:budget].rsplit(" ", 1)[0]
    return f"{head} [...{len(transcript) - budget:,} more chars; use get_transcript for full text]"


def save_summary(content: str, video_url: str) -> str:
    """Save the summary to the operator's Desktop and open it in notepad."""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"youtube_summary_{ts}.txt"
    desktop = Path.home() / "Desktop"
    desktop.mkdir(parents=True, exist_ok=True)
    filepath = desktop / filename
    header = (
        f"JARVIS — YouTube Summary\n"
        f"{'─' * 50}\n"
        f"URL    : {video_url}\n"
        f"Date   : {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
        f"{'─' * 50}\n\n"
    )
    filepath.write_text(header + content, encoding="utf-8")
    try:
        if is_windows():
            subprocess.Popen(["notepad.exe", str(filepath)])
        elif is_mac():
            subprocess.Popen(["open", "-t", str(filepath)])
        else:
            subprocess.Popen(["xdg-open", str(filepath)])
    except Exception as e:
        print(f"[YouTube] could not open text editor: {e}")
    return str(filepath)


__all__ = [
    "extract_video_id",
    "get_transcript",
    "is_valid_youtube_url",
    "save_summary",
    "scrape_first_video_url",
    "scrape_trending",
    "scrape_video_info",
    "summarize_with_or",
]


# Touch sys.modules to keep ruff S602 quiet about unused sys import.
_ = sys

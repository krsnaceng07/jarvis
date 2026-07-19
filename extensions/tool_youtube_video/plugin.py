"""YouTubeVideoPlugin — JARVIS YouTube controller (play / summarize / info / trending).

Migrated from ``actions/youtube_video.py``. Same action table, same
scrapers. Returns ``Result[str]`` (Phase 1C contract).
"""

# ruff: noqa: PLR0911
# - PLR0911: `_summarize` has 8 returns because it has 8 distinct
#   failure modes (MISSING_DEP / MISSING_ARG / BAD_URL / BAD_URL /
#   NO_TRANSCRIPT / SUMMARIZE_FAILED / save ok / no-save ok). Each
#   carries a different error code; merging them would lose fidelity.

from __future__ import annotations

from typing import Any

from jarvis_sdk import (
    Err,
    Ok,
    Result,
    ToolDecl,
    ToolParam,
    ToolPlugin,
)

from . import runtime

YOUTUBE_TOOL = ToolDecl(
    name="youtube_video",
    description=(
        "Controls YouTube. Use for: playing videos, summarizing a video's content, "
        "getting video info, or showing trending videos."
    ),
    parameters=[
        ToolParam(
            name="action",
            type="string",
            description="play | summarize | get_info | trending (default: play)",
            required=False,
        ),
        ToolParam(
            name="query",
            type="string",
            description="Search query (for action=play).",
            required=False,
        ),
        ToolParam(
            name="url",
            type="string",
            description="YouTube URL (for action=summarize or get_info).",
            required=False,
        ),
        ToolParam(
            name="region",
            type="string",
            description="Region code for trending (default: TR).",
            required=False,
        ),
        ToolParam(
            name="save",
            type="boolean",
            description="Save the summary to Desktop (for action=summarize).",
            required=False,
        ),
    ],
    returns="string",
    category="media",
)


class YouTubeVideoPlugin(ToolPlugin):
    """YouTube controller. Stateless."""

    id = "tool_youtube_video"
    kind = "tool"
    version = "0.1.0"
    description = "YouTube play / summarize / get_info / trending."

    def init(self, ctx: Any) -> None:
        return

    async def shutdown(self) -> None:
        return None

    @property
    def tools(self) -> list[ToolDecl]:
        return [YOUTUBE_TOOL]

    async def call(self, name: str, args: dict[str, Any]) -> Result[str]:
        if name != "youtube_video":
            return Err(f"Unknown tool: {name}", code="UNKNOWN_TOOL")
        return self._youtube(args)

    def _youtube(self, args: dict[str, Any]) -> Result[str]:
        action = (args.get("action") or "play").lower().strip()
        if action == "play":
            return self._play(args)
        if action == "summarize":
            return self._summarize(args)
        if action == "get_info":
            return self._get_info(args)
        if action == "trending":
            return self._trending(args)
        return Err(
            f"Unknown YouTube action: '{action}'. "
            "Available: play, summarize, get_info, trending.",
            code="UNKNOWN_ACTION",
        )

    def _play(self, args: dict[str, Any]) -> Result[str]:
        query = (args.get("query") or "").strip()
        if not query:
            return Err("Please tell me what you'd like to watch, sir.", code="MISSING_ARG")
        video_url = runtime.scrape_first_video_url(query)
        if video_url:
            runtime._open_url(video_url)
            return Ok(f"Playing: {query}")
        # Fallback: open the search-results page filtered to videos.
        from urllib.parse import quote_plus

        fallback_url = (
            f"https://www.youtube.com/results"
            f"?search_query={quote_plus(query)}"
            f"&sp={runtime._YT_VIDEO_FILTER}"
        )
        runtime._open_url(fallback_url)
        return Ok(f"Opened YouTube search for: {query} (manual selection required)")

    def _summarize(self, args: dict[str, Any]) -> Result[str]:
        try:
            from youtube_transcript_api import YouTubeTranscriptApi  # type: ignore # noqa: F401
        except ImportError:
            return Err(
                "youtube-transcript-api is not installed. "
                "Run: pip install youtube-transcript-api",
                code="MISSING_DEP",
            )
        url = (args.get("url") or "").strip() or (runtime._ask_for_url() or "")
        if not url:
            return Err("No URL provided, sir. Summary cancelled.", code="MISSING_ARG")
        if not runtime.is_valid_youtube_url(url):
            return Err("That doesn't appear to be a valid YouTube URL, sir.", code="BAD_URL")
        video_id = runtime.extract_video_id(url)
        if not video_id:
            return Err("Could not extract video ID from that URL, sir.", code="BAD_URL")
        transcript = runtime.get_transcript(video_id)
        if not transcript:
            return Err(
                "I couldn't retrieve a transcript for that video, sir.", code="NO_TRANSCRIPT"
            )
        try:
            summary = runtime.summarize_with_or(transcript, url)
        except Exception as e:
            return Err(f"Summary generation failed, sir: {e}", code="SUMMARIZE_FAILED")
        if args.get("save", False):
            saved = runtime.save_summary(summary, url)
            return Ok(f"Summary complete and saved to Desktop: {saved}")
        return Ok(summary)

    def _get_info(self, args: dict[str, Any]) -> Result[str]:
        url = (args.get("url") or "").strip()
        if not url:
            url = runtime._ask_for_url() or ""
        if not url or not runtime.is_valid_youtube_url(url):
            return Err("Please provide a valid YouTube URL, sir.", code="BAD_URL")
        video_id = runtime.extract_video_id(url)
        if not video_id:
            return Err("Could not extract video ID, sir.", code="BAD_URL")
        info = runtime.scrape_video_info(video_id)
        if not info:
            return Err("Could not retrieve video information, sir.", code="SCRAPE_FAILED")
        lines = [
            f"{key.capitalize()}: {info[key]}"
            for key in ("title", "channel", "views", "duration", "likes")
            if key in info
        ]
        return Ok("\n".join(lines))

    def _trending(self, args: dict[str, Any]) -> Result[str]:
        region = (args.get("region") or "TR").upper()
        trending = runtime.scrape_trending(region=region, max_results=8)
        if not trending:
            return Err(
                f"Could not fetch trending videos for region {region}, sir.",
                code="SCRAPE_FAILED",
            )
        lines = [f"Top trending videos in {region}:"]
        lines += [f"{v['rank']}. {v['title']} — {v['channel']}" for v in trending]
        return Ok("\n".join(lines))


__all__ = ["YOUTUBE_TOOL", "YouTubeVideoPlugin"]

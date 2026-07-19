---
name: summarize
description: "Summarize or transcribe URLs, YouTube/videos, podcasts, articles, transcripts, PDFs, and local files."
metadata:
  {
    "openclaw":
      {
        "emoji": "🧾"
      }
  }
---

# Summarize

Use this skill when the user wants a quick summary of a URL, YouTube
video, podcast, article, transcript, PDF, or local file. JARVIS has
two built-in ways to satisfy this — pick the right one based on the
content type.

## When to use (trigger phrases)

- "summarize this URL"
- "what's this link about?"
- "summarize this YouTube video"
- "give me the transcript of <url>"
- "tldr this article"

## How to invoke

### Web URLs and articles

Call `web_search` with the URL as the query (Google will return a
snippet + key points), OR call `youtube_video` with `action=summarize`
and the URL when it's a YouTube link.

### YouTube videos specifically

Use the `youtube_video` tool:

- `action="summarize"`, `url="<youtube-url>"`, `save=true` to write
  the summary to `~/Desktop/youtube_summary_<ts>.txt`.
- `action="play"`, `query="<search>"` to open the top non-Shorts
  result.
- `action="get_info"`, `url="<youtube-url>"` for title/channel/views/duration.
- `action="trending"`, `region="US"` (or any 2-letter code) for the
  top trending list.

### Local files

For PDFs / text files / etc., the file_processor extension can ingest
the file (`current_file` is set in the UI; the tool reads from there
when no `file_path` is passed).

## Quick examples

- "Summarize this: https://example.com/article"
  → `web_search(query="https://example.com/article")`
- "What's this YouTube video about? https://youtu.be/abc"
  → `youtube_video(action="summarize", url="https://youtu.be/abc", save=false)`
- "Show me the latest trending videos on YouTube"
  → `youtube_video(action="trending", region="US")`

## Notes

- For long transcripts (>80k chars), `youtube_video` truncates before
  sending to the LLM; the summary stays in the LLM's context window.
- For paywalled / blocked sites, the user must provide the content
  manually (Phase 3 will add `FIRECRAWL_API_KEY` support).

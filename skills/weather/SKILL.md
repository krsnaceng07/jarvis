---
name: weather
description: "Get current weather and forecasts (no API key needed)."
metadata:
  {
    "openclaw":
      {
        "emoji": "🌤️"
      }
  }
---

# Weather

Use this skill when the user asks about weather, temperature, rain, or
forecasts for any city. No API key required — the JARVIS
`tool_web_search` extension already opens a Google weather search
in the default browser.

## When to use (trigger phrases)

- "what's the weather in <city>?"
- "will it rain tomorrow in <city>?"
- "temperature in <city> right now"
- "forecast for <city> this weekend"

## How to invoke

Call the `web_search` tool with `query="weather in <city> <time>"` and
`time="today" | "tomorrow" | "this weekend" | "<YYYY-MM-DD>"`. The
browser opens the top Google result.

## Quick examples

- `query="weather in London"`, `time="today"`
- `query="weather in Tokyo"`, `time="tomorrow"`
- `query="weather in Kathmandu"`, `time="this weekend"`

## Notes

- If the user is in a hurry, just say "Showing the weather for
  <city>, sir" once the browser opens.
- For "compare weather in X vs Y" use `mode="compare"` with `items`
  and `aspect="weather"`.

"""Capture the hologram at fixed timeline phases for reference comparison.

Usage: python tools/capture_hologram_phases.py [base_url] [male|female]
Writes phase PNGs plus a 5-up contact sheet into the temp preview folder.
"""

import asyncio
import sys
from pathlib import Path

from playwright.async_api import async_playwright

OUT = Path(r"C:\Users\kcs23\AppData\Local\Temp\opencode\ui")
BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:5199/?holo=debug"
CHARACTER = sys.argv[2] if len(sys.argv) > 2 else "female"
PHASES = [
    ("scattered", 0.2),
    ("scan_low", 1.2),
    ("scan_mid", 1.9),
    ("scan_high", 2.7),
    ("settle", 3.2),
    ("stable", 3.4),
]


async def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1536, "height": 831}, device_scale_factor=2)
        page.on("pageerror", lambda e: print("pageerror:", str(e)[:300]))
        await page.goto(BASE, wait_until="networkidle")
        await asyncio.sleep(2.0)

        picker = page.get_by_role("button", name=f"Use {CHARACTER} hologram character")
        if await picker.count():
            await picker.first.click()
            await asyncio.sleep(2.0)

        canvas = page.locator('[aria-label*="holographic assistant avatar"] canvas').first
        await canvas.wait_for(state="visible")
        box = await canvas.bounding_box()
        if box is None:
            raise SystemExit("canvas not found")
        clip = {
            "x": box["x"],
            "y": box["y"],
            "width": box["width"],
            "height": box["height"],
        }

        for name, time in PHASES:
            await page.evaluate(
                """(t) => {
                    const d = window.__jarvisHologram;
                    if (!d) throw new Error('debug handle missing');
                    d.paused = true;
                    d.panel = false;
                    d.time = t;
                    d.dispersion = null;
                    d.turbulence = null;
                    d.brightness = null;
                }""",
                time,
            )
            await asyncio.sleep(0.45)
            path = OUT / f"holo_{name}.png"
            await page.screenshot(path=str(path), clip=clip)
            print("captured", path)

        await browser.close()


asyncio.run(main())

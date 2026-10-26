import asyncio
import sys
from pathlib import Path

from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parent
OUT = Path(r"C:\Users\kcs23\AppData\Local\Temp\opencode\ui")
BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:5199/"


async def shoot(page, name):
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"{name}.png"
    await page.screenshot(path=str(path))
    print("captured", path)


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1536, "height": 831})
        page.on("console", lambda m: print("console:", m.type, m.text[:200]) if m.type in ("error", "warning") else None)
        page.on("pageerror", lambda e: print("pageerror:", str(e)[:300]))
        await page.goto(BASE, wait_until="networkidle")
        await asyncio.sleep(4.5)
        await shoot(page, "dashboard_male_1536x831")

        # Female switch inside the hologram card.
        female = page.get_by_role("button", name="Use female hologram character")
        if await female.count():
            await female.first.click()
            await asyncio.sleep(3.0)
            await shoot(page, "dashboard_female_1536x831")

        # Onboarding modal.
        character = page.get_by_role("button", name="CHARACTER:", exact=False)
        if await character.count():
            await character.first.click()
            await asyncio.sleep(3.0)
            await shoot(page, "onboarding_female_1536x831")

        await page.set_viewport_size({"width": 1356, "height": 700})
        await asyncio.sleep(1.5)
        await shoot(page, "onboarding_female_1356x700")

        await asyncio.sleep(0.2)
        await browser.close()


asyncio.run(main())

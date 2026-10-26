import asyncio
from playwright.async_api import async_playwright

RESOLUTIONS = [
    {"name": "1536x864", "width": 1536, "height": 864},
    {"name": "1920x1080", "width": 1920, "height": 1080},
    {"name": "1366x768", "width": 1366, "height": 768},
    {"name": "1656x936", "width": 1656, "height": 936},
]

async def capture_all():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        
        for res in RESOLUTIONS:
            context = await browser.new_context(viewport={'width': res['width'], 'height': res['height']})
            page = await context.new_page()
            print(f"Navigating to http://localhost:5173/ at {res['name']}...")
            await page.goto("http://localhost:5173/", wait_until="networkidle")
            await asyncio.sleep(2)
            path = f"E:/jarvis/Jarvis_UI/screenshot_{res['name']}.png"
            await page.screenshot(path=path)
            print(f"Captured: {path}")
            await context.close()
            
        await browser.close()

if __name__ == '__main__':
    asyncio.run(capture_all())

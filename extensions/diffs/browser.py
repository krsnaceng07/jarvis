from playwright.async_api import async_playwright


class PlaywrightDiffScreenshotter:
    def __init__(self) -> None:
        pass

    async def screenshot_html(
        self, html: str, output_path: str, theme: str, image_format: str
    ) -> str:
        async with async_playwright() as p:
            # We use chromium
            browser = await p.chromium.launch(headless=True, args=["--disable-dev-shm-usage"])
            try:
                page = await browser.new_page(
                    viewport={"width": 1200, "height": 900},
                    color_scheme=theme,
                )

                # Intercept routes to prevent hanging on missing assets
                async def route_handler(route):
                    req_url = route.request.url
                    if req_url.startswith("data:") or req_url == "about:blank":
                        await route.continue_()
                    else:
                        await route.fulfill(status=200, body="")

                await page.route("**/*", route_handler)

                # Set HTML
                await page.set_content(html, wait_until="load")

                # Wait for fonts
                await page.evaluate("document.fonts.ready")

                # Attempt to find the diff frame and get its bounding box
                frame = page.locator(".oc-frame")
                try:
                    await frame.wait_for(timeout=5000)
                    box = await frame.bounding_box()
                except Exception:
                    # fallback to body
                    box = await page.locator("body").bounding_box()

                if not box:
                    raise RuntimeError("Diff frame did not render.")

                padding = 0 if image_format == "pdf" else 20
                clip_width = max(int(box["width"] + padding * 2), 900)
                clip_height = max(int(box["height"] + padding * 2), 320)

                await page.set_viewport_size({"width": clip_width, "height": clip_height})

                if image_format == "pdf":
                    await page.emulate_media(media="screen")
                    await page.evaluate("""() => {
                        document.documentElement.style.background = "transparent";
                        document.body.style.margin = "0";
                        document.body.style.padding = "0";
                        document.body.style.background = "transparent";
                        document.body.style.setProperty("-webkit-print-color-adjust", "exact");
                    }""")
                    await page.pdf(
                        path=output_path,
                        width=f"{clip_width}px",
                        height=f"{clip_height}px",
                        print_background=True,
                        margin={"top": "0", "right": "0", "bottom": "0", "left": "0"},
                    )
                else:
                    clip = {
                        "x": max(0, box["x"] - padding),
                        "y": max(0, box["y"] - padding),
                        "width": clip_width,
                        "height": clip_height,
                    }
                    await page.screenshot(path=output_path, type="png", clip=clip)
                return output_path
            finally:
                await browser.close()

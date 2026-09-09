from playwright.async_api import async_playwright

_browser = None
_context = None
_page = None
_playwright = None


async def start_browser():
    global _browser, _context, _page, _playwright
    if _browser is None:
        _playwright = await async_playwright().start()
        _browser = await _playwright.chromium.launch(
            headless=False, args=["--no-sandbox", "--disable-gpu"]
        )
        _context = await _browser.new_context()
        _page = await _context.new_page()
    return _browser, _context, _page


async def close_browser():
    global _browser, _context, _page, _playwright
    if _browser:
        await _browser.close()
        _browser = _context = _page = None
    if _playwright:
        await _playwright.stop()
        _playwright = None

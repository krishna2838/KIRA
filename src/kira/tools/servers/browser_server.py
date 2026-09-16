"""Browser automation MCP server via Playwright.

A single long-lived Chromium browser and one shared page context. Head is
hidden by default; pass `show=true` on `open_url` to pop the window.

Every tool that mutates page state (`click_element`, `fill_form`) is L2 —
the executor gates it. Read-only tools (`get_page_content`, `screenshot_page`,
`extract_data`) are L1.

Playwright must be installed AND `playwright install chromium` must have run.
When it hasn't, tools return an actionable error, not a crash.
"""
from __future__ import annotations

import asyncio
import base64
from typing import Any

from kira.core.logger import get_logger

from kira.tools.servers.base import InternalServer, InternalTool


logger = get_logger("tools.browser")


class _BrowserSingleton:
    """Owns the async Playwright instance and one persistent page."""

    def __init__(self):
        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None
        self._lock = asyncio.Lock()

    async def page(self, show: bool = False):
        async with self._lock:
            if self._page is not None and not self._page.is_closed():
                return self._page
            try:
                from playwright.async_api import async_playwright  # type: ignore
            except Exception as e:
                raise RuntimeError(
                    "playwright is required (pip install playwright && "
                    "playwright install chromium)"
                ) from e

            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(
                headless=not show
            )
            self._context = await self._browser.new_context(
                viewport={"width": 1280, "height": 800},
                user_agent=(
                    "Mozilla/5.0 (Macintosh; Apple Silicon Mac OS X 14_0) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) KIRA/0.1"
                ),
            )
            self._page = await self._context.new_page()
            return self._page

    async def close(self):
        async with self._lock:
            try:
                if self._context:
                    await self._context.close()
                if self._browser:
                    await self._browser.close()
                if self._playwright:
                    await self._playwright.stop()
            finally:
                self._playwright = self._browser = self._context = self._page = None


_browser = _BrowserSingleton()


# ---- tool handlers -------------------------------------------------------


async def _tool_open_url(args: dict) -> Any:
    show = bool(args.get("show", False))
    page = await _browser.page(show=show)
    resp = await page.goto(args["url"], wait_until="domcontentloaded")
    return {
        "url": page.url,
        "title": await page.title(),
        "status": resp.status if resp else None,
    }


async def _tool_get_page_content(args: dict) -> Any:
    page = await _browser.page()
    await page.goto(args["url"], wait_until="domcontentloaded")
    body = await page.evaluate(
        "() => document.body ? document.body.innerText : ''"
    )
    return {
        "url": page.url,
        "title": await page.title(),
        "text": (body or "")[:20000],
    }


async def _tool_screenshot_page(args: dict) -> Any:
    page = await _browser.page()
    if args.get("url"):
        await page.goto(args["url"], wait_until="domcontentloaded")
    png = await page.screenshot(
        full_page=bool(args.get("full_page", False)),
        type="png",
    )
    return {
        "url": page.url,
        "image_base64": base64.b64encode(png).decode("ascii"),
        "mime": "image/png",
    }


async def _tool_click_element(args: dict) -> Any:
    page = await _browser.page()
    selector = args["selector"]
    await page.wait_for_selector(selector, timeout=8000)
    await page.click(selector)
    return {"clicked": selector, "url_after": page.url}


async def _tool_fill_form(args: dict) -> Any:
    page = await _browser.page()
    selector = args["selector"]
    value = args["value"]
    await page.wait_for_selector(selector, timeout=8000)
    await page.fill(selector, value)
    return {"filled": selector}


async def _tool_extract_data(args: dict) -> Any:
    page = await _browser.page()
    if args.get("url"):
        await page.goto(args["url"], wait_until="domcontentloaded")
    selectors: dict[str, str] = args["selectors"]
    out: dict[str, list[str]] = {}
    for name, sel in selectors.items():
        try:
            values = await page.eval_on_selector_all(
                sel,
                "els => els.map(e => e.innerText || e.textContent || e.getAttribute('href') || '')",
            )
            out[name] = [v for v in values if v]
        except Exception as e:
            out[name] = [f"[error: {e}]"]
    return {"url": page.url, "data": out}


# ---- server definition ---------------------------------------------------


SERVER = InternalServer(
    name="browser",
    description=(
        "Automate a real Chromium browser via Playwright — open URLs, extract "
        "text and screenshots, click elements, fill forms, and pull structured "
        "data by CSS selector."
    ),
    tools=[
        InternalTool(
            name="open_url",
            description="Open a URL in a Playwright browser. Optionally show the window.",
            input_schema={
                "type": "object",
                "properties": {
                    "url": {"type": "string"},
                    "show": {"type": "boolean", "default": False},
                },
                "required": ["url"],
            },
            handler=_tool_open_url,
        ),
        InternalTool(
            name="get_page_content",
            description="Navigate to a URL and return its visible text content.",
            input_schema={
                "type": "object",
                "properties": {"url": {"type": "string"}},
                "required": ["url"],
            },
            handler=_tool_get_page_content,
        ),
        InternalTool(
            name="screenshot_page",
            description=(
                "Take a screenshot of the current page (or navigate first if "
                "`url` is given). Returns base64 PNG."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "url": {"type": "string"},
                    "full_page": {"type": "boolean", "default": False},
                },
            },
            handler=_tool_screenshot_page,
        ),
        InternalTool(
            name="click_element",
            description="Click an element on the current browser page by CSS selector.",
            input_schema={
                "type": "object",
                "properties": {"selector": {"type": "string"}},
                "required": ["selector"],
            },
            handler=_tool_click_element,
        ),
        InternalTool(
            name="fill_form",
            description="Fill a form field on the current page by CSS selector.",
            input_schema={
                "type": "object",
                "properties": {
                    "selector": {"type": "string"},
                    "value": {"type": "string"},
                },
                "required": ["selector", "value"],
            },
            handler=_tool_fill_form,
        ),
        InternalTool(
            name="extract_data",
            description=(
                "Pull structured data from a page: `selectors` maps field "
                "name → CSS selector; each match's innerText/href is returned."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "url": {"type": "string"},
                    "selectors": {
                        "type": "object",
                        "additionalProperties": {"type": "string"},
                    },
                },
                "required": ["selectors"],
            },
            handler=_tool_extract_data,
        ),
    ],
)


async def shutdown() -> None:
    """Called from bootstrap on server stop."""
    await _browser.close()

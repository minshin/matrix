from __future__ import annotations

from backend.crawl.httpx_crawler import fetch_with_httpx
from backend.crawl.jina_crawler import fetch_with_jina
from backend.crawl.playwright_crawler import fetch_with_playwright
from backend.utils.logger import get_logger

logger = get_logger(__name__)


async def fetch(url: str, source_config: dict) -> str:
    method = source_config.get("method", "auto")
    httpx_timeout_seconds = float(source_config.get("httpx_timeout_seconds", 20.0))
    jina_timeout_seconds = float(source_config.get("jina_timeout_seconds", 30.0))
    playwright_timeout_ms = int(source_config.get("playwright_timeout_ms", 30000))
    disable_playwright = bool(source_config.get("disable_playwright", False))

    if method == "httpx":
        return await fetch_with_httpx(url, timeout_seconds=httpx_timeout_seconds)
    if method == "jina":
        return await fetch_with_jina(url, timeout_seconds=jina_timeout_seconds)
    if method == "playwright":
        if disable_playwright:
            raise RuntimeError("playwright disabled by source_config")
        return await fetch_with_playwright(url, timeout_ms=playwright_timeout_ms)

    # auto mode:
    try:
        body = await fetch_with_httpx(url, timeout_seconds=httpx_timeout_seconds)
        if len(body.strip()) > 500:
            return body
        logger.warning("httpx content too short, fallback to jina: %s", url)
    except Exception as exc:
        logger.warning("httpx failed, fallback to jina: %s | %s", url, exc)

    try:
        body = await fetch_with_jina(url, timeout_seconds=jina_timeout_seconds)
        if body.strip():
            return body
        logger.warning("jina empty body, fallback to playwright: %s", url)
    except Exception as exc:
        logger.warning("jina failed, fallback to playwright: %s | %s", url, exc)

    if disable_playwright:
        raise RuntimeError("all fast crawlers failed and playwright is disabled")
    return await fetch_with_playwright(url, timeout_ms=playwright_timeout_ms)

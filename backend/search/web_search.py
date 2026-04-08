from __future__ import annotations

from dataclasses import dataclass
import html
import re
from urllib.parse import parse_qs, unquote, urlparse

import httpx

from backend.config import get_settings

DDG_RESULT_RE = re.compile(
    r'<a[^>]+class="[^"]*result__a[^"]*"[^>]+href="(?P<href>[^"]+)"[^>]*>(?P<title>.*?)</a>',
    flags=re.IGNORECASE,
)
BING_RESULT_RE = re.compile(r'<h2><a href="(?P<href>[^"]+)"[^>]*>(?P<title>.*?)</a></h2>', flags=re.IGNORECASE)
TAG_RE = re.compile(r"<[^>]+>")


@dataclass
class SearchResult:
    title: str
    url: str
    query: str
    engine: str
    published_at: str | None = None


def _normalize_title(raw: str) -> str:
    return html.unescape(TAG_RE.sub("", raw)).strip()


def _normalize_url(raw_href: str) -> str:
    href = html.unescape(raw_href)
    if href.startswith("//"):
        href = f"https:{href}"

    parsed = urlparse(href)
    if parsed.path.startswith("/l/"):
        params = parse_qs(parsed.query)
        uddg = params.get("uddg", [""])[0]
        if uddg:
            return unquote(uddg)

    return href


def _dedupe(results: list[SearchResult], max_results: int) -> list[SearchResult]:
    output: list[SearchResult] = []
    seen: set[str] = set()
    for item in results:
        if not item.url or item.url in seen:
            continue
        seen.add(item.url)
        output.append(item)
        if len(output) >= max_results:
            break
    return output


async def _search_duckduckgo(client: httpx.AsyncClient, query: str, max_results: int) -> list[SearchResult]:
    response = await client.get(
        "https://duckduckgo.com/html/",
        params={"q": query, "kl": "us-en"},
        headers={"User-Agent": "Mozilla/5.0 MatrixBot/1.0"},
        timeout=20,
    )
    response.raise_for_status()

    rows: list[SearchResult] = []
    for match in DDG_RESULT_RE.finditer(response.text):
        url = _normalize_url(match.group("href"))
        if not url.startswith("http"):
            continue
        title = _normalize_title(match.group("title")) or url
        rows.append(SearchResult(title=title, url=url, query=query, engine="duckduckgo", published_at=None))

    return _dedupe(rows, max_results)


async def _search_bing(client: httpx.AsyncClient, query: str, max_results: int) -> list[SearchResult]:
    response = await client.get(
        "https://www.bing.com/search",
        params={"q": query, "setlang": "en-us"},
        headers={"User-Agent": "Mozilla/5.0 MatrixBot/1.0"},
        timeout=20,
    )
    response.raise_for_status()

    rows: list[SearchResult] = []
    for match in BING_RESULT_RE.finditer(response.text):
        url = _normalize_url(match.group("href"))
        if not url.startswith("http"):
            continue
        title = _normalize_title(match.group("title")) or url
        rows.append(SearchResult(title=title, url=url, query=query, engine="bing", published_at=None))

    return _dedupe(rows, max_results)


async def _search_jina(client: httpx.AsyncClient, query: str, max_results: int) -> list[SearchResult]:
    settings = get_settings()
    if not settings.jina_api_key:
        return []

    response = await client.get(
        f"https://s.jina.ai/{query}",
        headers={
            "Authorization": f"Bearer {settings.jina_api_key}",
            "Accept": "application/json",
        },
        timeout=30,
    )
    response.raise_for_status()

    payload = response.json()
    items = payload.get("data", []) if isinstance(payload, dict) else []

    rows: list[SearchResult] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        url = str(item.get("url", "")).strip()
        if not url.startswith("http"):
            continue
        title = str(item.get("title", "")).strip() or url
        published_at = (
            item.get("publishedDate")
            or item.get("published_at")
            or item.get("date")
            or item.get("datetime")
            or item.get("time")
        )
        rows.append(
            SearchResult(
                title=title,
                url=url,
                query=query,
                engine="jina",
                published_at=str(published_at).strip() if published_at else None,
            )
        )

    return _dedupe(rows, max_results)


async def search_web(query: str, max_results: int = 5) -> list[SearchResult]:
    max_results = max(1, min(max_results, 50))
    async with httpx.AsyncClient(follow_redirects=True) as client:
        try:
            results = await _search_jina(client, query, max_results)
            if results:
                return results
        except Exception:
            pass

        try:
            results = await _search_duckduckgo(client, query, max_results)
            if results:
                return results
        except Exception:
            pass

        try:
            results = await _search_bing(client, query, max_results)
            if results:
                return results
        except Exception:
            pass

    return []

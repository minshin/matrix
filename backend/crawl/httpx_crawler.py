from __future__ import annotations

import httpx


async def fetch_with_httpx(url: str, timeout_seconds: float = 20.0) -> str:
    async with httpx.AsyncClient(follow_redirects=True, timeout=timeout_seconds) as client:
        response = await client.get(url)
        response.raise_for_status()
        return response.text

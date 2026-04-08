from __future__ import annotations

import httpx

from backend.config import get_settings


async def fetch_with_jina(url: str, timeout_seconds: float = 30.0) -> str:
    settings = get_settings()
    target = f"https://r.jina.ai/{url}"

    headers = {
        "Accept": "text/plain",
        "X-Return-Format": "markdown",
    }
    if settings.jina_api_key:
        headers["Authorization"] = f"Bearer {settings.jina_api_key}"

    async with httpx.AsyncClient(timeout=timeout_seconds) as client:
        response = await client.get(target, headers=headers)
        response.raise_for_status()
        return response.text

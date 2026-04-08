from __future__ import annotations

from typing import Any

import httpx

from backend.config import get_settings


class OpenRouterClient:
    def __init__(self) -> None:
        self.settings = get_settings()

    @property
    def enabled(self) -> bool:
        return bool(self.settings.openrouter_api_key)

    async def complete(
        self,
        prompt: str,
        *,
        model: str | None = None,
        system_prompt: str | None = None,
        max_tokens: int = 256,
        temperature: float = 0.0,
    ) -> str:
        if not self.enabled:
            raise RuntimeError("OPENROUTER_API_KEY is not configured")

        target_model = (model or self.settings.openrouter_model).strip()
        if not target_model:
            raise RuntimeError("openrouter model is empty")

        messages: list[dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        headers = {
            "Authorization": f"Bearer {self.settings.openrouter_api_key}",
            "Content-Type": "application/json",
        }
        if self.settings.openrouter_site_url:
            headers["HTTP-Referer"] = self.settings.openrouter_site_url
        if self.settings.openrouter_app_name:
            headers["X-Title"] = self.settings.openrouter_app_name

        payload = {
            "model": target_model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        async with httpx.AsyncClient(timeout=self.settings.llm_timeout_seconds) as client:
            response = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
            body = response.json()

        choices = body.get("choices", [])
        if not choices:
            raise RuntimeError("openrouter returned empty choices")

        message = choices[0].get("message", {})
        content = message.get("content", "")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, dict):
                    text = item.get("text")
                    if text:
                        parts.append(str(text))
            return "".join(parts).strip()
        return str(content)


def list_available_models() -> list[str]:
    settings = get_settings()
    values = [item.strip() for item in settings.openrouter_models_csv.split(",")]
    models = [item for item in values if item]
    if settings.openrouter_model and settings.openrouter_model not in models:
        models.insert(0, settings.openrouter_model)
    return models

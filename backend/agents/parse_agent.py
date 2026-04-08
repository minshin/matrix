from __future__ import annotations

import asyncio
import json
from typing import Any

from backend.config import get_settings
from backend.llm import OpenRouterClient
from backend.utils.llm_budget import LLMBudget
from backend.utils.logger import get_logger

logger = get_logger(__name__)

PARSE_PROMPT = """
你是一个信息抽取 agent。从以下文本中抽取与"{topic}"相关的关键事实陈述。

要求：
- 每条陈述必须是一个独立的客观事实或事件
- 不要推断，只陈述文本中明确提到的内容
- 每条陈述附一个置信度（0~1），反映文本对该陈述的支持程度
- 最多抽取 5 条最相关的陈述

文本内容：
{text}

仅输出以下 JSON，不要任何其他内容：
{{
  "observations": [
    {{"content": "<陈述>", "confidence": <float>, "tags": ["<tag1>", "<tag2>"]}}
  ]
}}
""".strip()


class ParseAgent:
    def __init__(self, budget: LLMBudget | None = None) -> None:
        self.settings = get_settings()
        self._budget = budget
        self._client = OpenRouterClient()

    async def parse(
        self,
        text: str,
        topic: str,
        default_tags: list[str] | None = None,
        model: str | None = None,
    ) -> list[dict[str, Any]]:
        default_tags = default_tags or []
        text = text[:8000]

        if not self._client.enabled:
            return self._fallback_parse(text, default_tags)

        prompt = PARSE_PROMPT.format(topic=topic, text=text)

        for attempt in range(3):
            try:
                if self._budget is not None and not await self._budget.try_consume():
                    logger.warning("LLM budget exhausted in ParseAgent")
                    return self._fallback_parse(text, default_tags)
                content = await asyncio.wait_for(
                    self._client.complete(
                        prompt,
                        model=model,
                        max_tokens=500,
                        temperature=0,
                    ),
                    timeout=self.settings.llm_timeout_seconds,
                )
                parsed = _parse_json(content)
                return _normalize_observations(parsed.get("observations", []), default_tags)
            except Exception as exc:
                logger.warning("Parse agent failed (attempt %s): %s", attempt + 1, exc)
                await asyncio.sleep(0.3)

        return self._fallback_parse(text, default_tags)

    def _fallback_parse(self, text: str, default_tags: list[str]) -> list[dict[str, Any]]:
        stripped = " ".join(text.split())
        if not stripped:
            return []
        return [{"content": stripped[:240], "confidence": 0.5, "tags": default_tags}]


def _parse_json(raw: str) -> dict[str, Any]:
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        start = raw.find("{")
        end = raw.rfind("}")
        if start >= 0 and end > start:
            return json.loads(raw[start : end + 1])
        raise


def _normalize_observations(items: list[dict[str, Any]], default_tags: list[str]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for item in items[:5]:
        content = str(item.get("content", "")).strip()
        if not content:
            continue

        confidence = float(item.get("confidence", 0.5))
        confidence = max(0.0, min(1.0, confidence))

        tags = item.get("tags") or default_tags
        if not isinstance(tags, list):
            tags = default_tags

        output.append(
            {
                "content": content,
                "confidence": round(confidence, 3),
                "tags": [str(tag) for tag in tags],
            }
        )
    return output

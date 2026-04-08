from __future__ import annotations

import asyncio
import json
from typing import Any

from backend.config import get_settings
from backend.engine.probability import clamp
from backend.llm import OpenRouterClient
from backend.utils.llm_budget import LLMBudget
from backend.utils.logger import get_logger

logger = get_logger(__name__)

REASONING_PROMPT = """
你是一个事件推理 agent。你的任务是对一个命题的发生概率做语义修正。

【当前命题】
{label}

【输入事件及其概率】
{inputs_text}

【结构公式估算的基础概率】
{formula_prob:.2f}

【你的任务】
判断该基础概率是否需要语义修正。
请考虑：输入事件之间是否存在协同或对冲关系？是否有未被公式捕捉的语义因素？

修正范围：严格限制在 -0.15 ~ +0.15 之间。

仅输出以下 JSON，不要任何其他内容：
{{"delta": <float>, "reason": "<一句中文说明>"}}
""".strip()


class ReasoningAgent:
    def __init__(self, budget: LLMBudget | None = None) -> None:
        self.settings = get_settings()
        self._budget = budget
        self._client = OpenRouterClient()

    async def infer_delta(
        self,
        label: str,
        inputs: list[dict[str, Any]],
        formula_prob: float,
        model: str | None = None,
    ) -> tuple[float, str]:
        if not self._client.enabled:
            return 0.0, "no_api_key"

        inputs_text = "\n".join(
            f"- {i.get('label', i.get('node_id', 'unknown'))}: p={i.get('probability', 0.5):.3f}, w={i.get('weight', 0.0):.3f}"
            for i in inputs
        )
        prompt = REASONING_PROMPT.format(
            label=label,
            inputs_text=inputs_text,
            formula_prob=formula_prob,
        )

        for attempt in range(3):
            try:
                if self._budget is not None and not await self._budget.try_consume():
                    logger.warning("LLM budget exhausted in ReasoningAgent")
                    return 0.0, "llm_budget_exhausted"
                text = await asyncio.wait_for(
                    self._client.complete(
                        prompt,
                        model=model,
                        max_tokens=200,
                        temperature=0,
                    ),
                    timeout=self.settings.llm_timeout_seconds,
                )
                payload = _parse_json(text)
                delta = float(payload.get("delta", 0.0))
                reason = str(payload.get("reason", "ok"))
                return round(clamp(delta, -0.15, 0.15), 3), reason
            except Exception as exc:
                logger.warning("Reasoning agent failed (attempt %s): %s", attempt + 1, exc)
                await asyncio.sleep(0.3)

        return 0.0, "parse_failed"


def _parse_json(raw: str) -> dict[str, Any]:
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        start = raw.find("{")
        end = raw.rfind("}")
        if start >= 0 and end > start:
            return json.loads(raw[start : end + 1])
        raise

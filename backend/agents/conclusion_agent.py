from __future__ import annotations

import asyncio

from backend.config import get_settings
from backend.llm import OpenRouterClient
from backend.utils.llm_budget import LLMBudget
from backend.utils.logger import get_logger

logger = get_logger(__name__)

CONCLUSION_PROMPT = """
你是结论生成 agent。请根据以下数据生成 2~3 句中文叙述，简洁、克制、可读。

命题：{label}
概率：{probability:.3f}
置信区间：[{low:.3f}, {high:.3f}]
支持事件：
{supporting}

只输出自然语言，不要 JSON。
""".strip()


class ConclusionAgent:
    def __init__(self, budget: LLMBudget | None = None) -> None:
        self.settings = get_settings()
        self._budget = budget
        self._client = OpenRouterClient()

    async def generate(
        self,
        label: str,
        probability: float,
        confidence_band: tuple[float, float],
        supporting_nodes: list[str],
        model: str | None = None,
    ) -> str:
        low, high = confidence_band
        if not self._client.enabled:
            return self._fallback(label, probability, confidence_band)

        prompt = CONCLUSION_PROMPT.format(
            label=label,
            probability=probability,
            low=low,
            high=high,
            supporting="\n".join(f"- {node}" for node in supporting_nodes) or "- 无",
        )

        for attempt in range(3):
            try:
                if self._budget is not None and not await self._budget.try_consume():
                    logger.warning("LLM budget exhausted in ConclusionAgent")
                    return self._fallback(label, probability, confidence_band)
                text = await asyncio.wait_for(
                    self._client.complete(
                        prompt,
                        model=model,
                        max_tokens=240,
                        temperature=0,
                    ),
                    timeout=self.settings.llm_timeout_seconds,
                )
                text = text.strip()
                return text or self._fallback(label, probability, confidence_band)
            except Exception as exc:
                logger.warning("Conclusion agent failed (attempt %s): %s", attempt + 1, exc)
                await asyncio.sleep(0.3)

        return self._fallback(label, probability, confidence_band)

    def _fallback(self, label: str, probability: float, band: tuple[float, float]) -> str:
        return f"{label} 的当前估计概率为 {probability:.3f}，置信区间约为 [{band[0]:.3f}, {band[1]:.3f}]。请结合后续信号持续更新判断。"

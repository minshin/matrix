from __future__ import annotations

import re

from backend.llm import OpenRouterClient
from backend.utils.logger import get_logger

logger = get_logger(__name__)

BOT_QUERY_TEMPLATES = [
    "{topic} latest news",
    "{topic} market analysis",
    "{topic} one month outlook",
    "{topic} expert views",
    "{topic} risk factors",
    "{topic} macro impact",
    "{topic} institutional forecast",
    "{topic} technical analysis",
    "{topic} fundamental analysis",
    "{topic} industry updates",
]

CJK_RE = re.compile(r"[\u3400-\u9FFF]")


async def build_bot_queries(
    topic: str,
    bot_count: int = 5,
    force_english: bool = True,
) -> list[str]:
    bot_count = max(1, min(bot_count, 10))
    normalized_topic = topic.strip()
    if force_english:
        normalized_topic = await _topic_to_english(normalized_topic)

    queries: list[str] = []
    for i in range(bot_count):
        if i < len(BOT_QUERY_TEMPLATES):
            queries.append(BOT_QUERY_TEMPLATES[i].format(topic=normalized_topic))
        else:
            queries.append(f"{normalized_topic} search bot {i + 1}")
    return queries


async def _topic_to_english(topic: str) -> str:
    if not topic:
        return topic
    if not CJK_RE.search(topic):
        return topic

    client = OpenRouterClient()
    if not client.enabled:
        return topic

    prompt = (
        "Translate the following prediction topic into concise English for web search. "
        "Return only the translated phrase, no explanation.\n\n"
        f"Topic: {topic}"
    )
    try:
        translated = (await client.complete(prompt, max_tokens=80, temperature=0)).strip()
        if not translated:
            return topic
        cleaned = translated.replace("\n", " ").strip(' "\'')
        return cleaned or topic
    except Exception as exc:
        logger.warning("topic english translation failed: %s", exc)
        return topic

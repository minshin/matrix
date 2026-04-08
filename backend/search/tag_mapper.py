from __future__ import annotations

import re

KEYWORD_TO_TAGS: dict[str, list[str]] = {
    "military": ["military", "navy", "troop", "missile", "drone", "军事", "海军", "冲突", "袭击"],
    "iran": ["iran", "iranian", "伊朗"],
    "hormuz": ["hormuz", "strait of hormuz", "霍尔木兹"],
    "shipping": ["shipping", "tanker", "vessel", "航运", "油轮", "船运", "通行"],
    "energy": ["energy", "oil", "gas", "能源", "石油", "天然气", "原油"],
    "oil": ["oil", "crude", "wti", "brent", "原油", "石油", "布伦特"],
    "diplomacy": ["diplomacy", "talks", "negotiation", "外交", "会谈", "谈判", "斡旋"],
    "gold": ["gold", "xauusd", "黄金", "贵金属"],
    "macro": ["inflation", "cpi", "fed", "fomc", "通胀", "利率", "美联储"],
}

TOKEN_RE = re.compile(r"[a-zA-Z0-9_\-\u4e00-\u9fff]+")


def _normalize(text: str) -> str:
    return text.strip().lower()


def build_observation_tags(
    topic: str,
    query: str,
    title: str,
    content: str,
    raw_tags: list[str] | None = None,
    domain: str | None = None,
) -> list[str]:
    raw_tags = raw_tags or []
    text = " ".join([topic, query, title, content[:600], " ".join(raw_tags)]).lower()

    tags: set[str] = set()

    for canonical, keywords in KEYWORD_TO_TAGS.items():
        if any(keyword.lower() in text for keyword in keywords):
            tags.add(canonical)

    for item in raw_tags:
        token = _normalize(item)
        if token:
            tags.add(token)

    if domain:
        host = _normalize(domain)
        if host.startswith("www."):
            host = host[4:]
        if host:
            tags.add(host)
            tags.update(TOKEN_RE.findall(host))

    topic_tokens = TOKEN_RE.findall(_normalize(topic))[:4]
    for token in topic_tokens:
        tags.add(token)

    return sorted(tags)[:16]

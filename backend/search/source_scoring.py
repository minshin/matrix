from __future__ import annotations

from urllib.parse import urlparse

from backend.engine.probability import clamp

DOMAIN_PROBABILITY = {
    "reuters.com": 0.86,
    "bloomberg.com": 0.84,
    "wsj.com": 0.83,
    "ft.com": 0.82,
    "cnbc.com": 0.78,
    "marketwatch.com": 0.76,
    "investing.com": 0.72,
    "tradingeconomics.com": 0.74,
    "gold.org": 0.8,
    "kitco.com": 0.75,
    "yahoo.com": 0.68,
    "seekingalpha.com": 0.66,
    "washingtonpost.com": 0.79,
    "nikkei.com": 0.8,
}

SOURCE_ALIAS_TO_DOMAIN = {
    "reuters": "reuters.com",
    "路透社": "reuters.com",
    "ft": "ft.com",
    "financial times": "ft.com",
    "华尔街日报": "wsj.com",
    "wsj": "wsj.com",
    "washington post": "washingtonpost.com",
    "华盛顿邮报": "washingtonpost.com",
    "nikkei": "nikkei.com",
    "日经": "nikkei.com",
    "bloomberg": "bloomberg.com",
    "彭博": "bloomberg.com",
}


def source_probability_from_url(url: str) -> float:
    host = (urlparse(url).hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]

    if not host:
        return 0.6

    if host in DOMAIN_PROBABILITY:
        return DOMAIN_PROBABILITY[host]

    for domain, score in DOMAIN_PROBABILITY.items():
        if host.endswith(f".{domain}"):
            return score

    return 0.6


def merge_probabilities(parse_probability: float, source_probability: float) -> float:
    # 信源质量和文本抽取置信度各占 50%。
    score = (parse_probability * 0.5) + (source_probability * 0.5)
    return round(clamp(score), 3)


def normalize_source_constraints(items: list[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()

    for raw in items:
        value = raw.strip().lower()
        if not value:
            continue

        mapped = SOURCE_ALIAS_TO_DOMAIN.get(value, value)
        mapped = mapped.removeprefix("https://").removeprefix("http://")
        mapped = mapped.removeprefix("www.")
        mapped = mapped.split("/")[0]

        if not mapped or mapped in seen:
            continue
        seen.add(mapped)
        normalized.append(mapped)

    return normalized


def source_allowed(hostname: str, constraints: list[str]) -> bool:
    host = hostname.lower().removeprefix("www.")
    if not constraints:
        return True
    return any(host == domain or host.endswith(f".{domain}") for domain in constraints)

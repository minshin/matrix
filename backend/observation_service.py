from __future__ import annotations

import asyncio
import calendar
from datetime import datetime, timezone
import re
from typing import Any
from urllib.parse import urlparse

from backend.agents.parse_agent import ParseAgent
from backend.config import get_settings
from backend.crawl.crawler_router import fetch
from backend.db.client import insert_rows, update_rows
from backend.db.observations import create_observations
from backend.search import (
    SearchResult,
    build_observation_tags,
    build_bot_queries,
    merge_probabilities,
    normalize_source_constraints,
    search_web,
    source_allowed,
    source_probability_from_url,
)
from backend.utils.id_gen import gen_record_id, gen_run_id
from backend.utils.llm_budget import LLMBudget
from backend.utils.logger import get_logger

logger = get_logger(__name__)

DATE_PATTERNS = [
    re.compile(r"(?P<y>20\d{2})[-/.](?P<m>0?[1-9]|1[0-2])[-/.](?P<d>0?[1-9]|[12]\d|3[01])"),
    re.compile(r"(?P<y>20\d{2})年(?P<m>0?[1-9]|1[0-2])月(?P<d>0?[1-9]|[12]\d|3[01])日"),
]
URL_DATE_PATTERN = re.compile(r"/(?P<y>20\d{2})/(?P<m>0?[1-9]|1[0-2])/(?P<d>0?[1-9]|[12]\d|3[01])(?:/|$)")
MONTH_NAME_PATTERN = re.compile(
    r"(?P<month>Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
    r"\s+(?P<day>[0-3]?\d),\s*(?P<year>20\d{2})",
    flags=re.IGNORECASE,
)


class ObservationService:
    def __init__(self) -> None:
        self.settings = get_settings()
        budget = LLMBudget(max_calls=50)
        self.parse_agent = ParseAgent(budget=budget)
        self.item_timeout_seconds = max(8.0, min(self.settings.request_timeout_seconds, 20.0))
        self.extract_semaphore = asyncio.Semaphore(8)

    async def run(
        self,
        topic: str,
        bot_count: int = 5,
        results_per_bot: int = 5,
        months_back: int = 1,
        source_constraints: list[str] | None = None,
        ai_model: str | None = None,
    ) -> dict[str, Any]:
        topic = topic.strip()
        if not topic:
            raise ValueError("topic is required")

        bot_count = max(1, min(bot_count, 10))
        results_per_bot = max(1, min(results_per_bot, 10))
        months_back = max(1, min(months_back, 24))
        source_constraints = source_constraints or []

        run_id = gen_run_id()
        self._mark_run_started(run_id)

        try:
            collected = await self.collect_for_run(
                topic=topic,
                run_id=run_id,
                bot_count=bot_count,
                results_per_bot=results_per_bot,
                months_back=months_back,
                source_constraints=source_constraints,
                ai_model=ai_model,
                persist=True,
            )
            search_hits_count = collected["searched_links"]
            observations = collected["observations"]
            status_logs = collected["status_logs"]
            normalized_constraints = collected["source_constraints"]

            self._mark_run_finished(run_id, "done")
            return {
                "run_id": run_id,
                "topic": topic,
                "bot_count": bot_count,
                "results_per_bot": results_per_bot,
                "months_back": months_back,
                "source_constraints": normalized_constraints,
                "searched_links": search_hits_count,
                "observations_count": len(observations),
                "status_logs": status_logs,
                "observations": [
                    {
                        "id": row["id"],
                        "content": row["content"],
                        "probability": row["confidence"],
                        "url": row["url"],
                        "source": row["source"],
                        "tags": row["tags"],
                        "meta": row.get("meta", {}),
                    }
                    for row in observations
                ],
            }
        except Exception:
            self._mark_run_finished(run_id, "failed")
            raise

    async def collect_for_run(
        self,
        topic: str,
        run_id: str,
        bot_count: int = 5,
        results_per_bot: int = 5,
        months_back: int = 1,
        source_constraints: list[str] | None = None,
        ai_model: str | None = None,
        persist: bool = True,
    ) -> dict[str, Any]:
        topic = topic.strip()
        if not topic:
            raise ValueError("topic is required")

        bot_count = max(1, min(bot_count, 10))
        results_per_bot = max(1, min(results_per_bot, 10))
        months_back = max(1, min(months_back, 24))
        normalized_constraints = normalize_source_constraints(source_constraints or [])

        bot_queries = await build_bot_queries(topic, bot_count, force_english=True)
        observations, searched_links, status_logs = await self._collect_observations_by_bot(
            topic=topic,
            run_id=run_id,
            bot_queries=bot_queries,
            results_per_bot=results_per_bot,
            months_back=months_back,
            source_constraints=normalized_constraints,
            ai_model=ai_model,
        )

        if persist and observations:
            create_observations(
                [
                    {
                        "id": row["id"],
                        "run_id": row["run_id"],
                        "source": row["source"],
                        "content": row["content"],
                        "url": row["url"],
                        "confidence": row["confidence"],
                        "tags": row["tags"],
                    }
                    for row in observations
                ]
            )

        return {
            "searched_links": searched_links,
            "observations": observations,
            "status_logs": status_logs,
            "source_constraints": normalized_constraints,
        }

    async def _collect_observations_by_bot(
        self,
        topic: str,
        run_id: str,
        bot_queries: list[str],
        results_per_bot: int,
        months_back: int,
        source_constraints: list[str],
        ai_model: str | None,
    ) -> tuple[list[dict[str, Any]], int, list[str]]:
        grouped = await asyncio.gather(
            *[
                self._collect_observations_for_single_bot(
                    idx=idx,
                    query=query,
                    topic=topic,
                    run_id=run_id,
                    results_per_bot=results_per_bot,
                    months_back=months_back,
                    source_constraints=source_constraints,
                    ai_model=ai_model,
                )
                for idx, query in enumerate(bot_queries, start=1)
            ]
        )

        all_rows: list[dict[str, Any]] = []
        status_logs: list[str] = []
        searched_links = 0
        for rows, searched_count, logs in grouped:
            all_rows.extend(rows)
            searched_links += searched_count
            status_logs.extend(logs)

        deduped_rows: list[dict[str, Any]] = []
        seen_urls: set[str] = set()
        for row in all_rows:
            url = str(row.get("url", ""))
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)
            deduped_rows.append(row)

        deduped_rows.sort(
            key=lambda item: str(item.get("meta", {}).get("published_at") or item.get("id")),
            reverse=True,
        )
        return deduped_rows, searched_links, status_logs

    async def _collect_observations_for_single_bot(
        self,
        idx: int,
        query: str,
        topic: str,
        run_id: str,
        results_per_bot: int,
        months_back: int,
        source_constraints: list[str],
        ai_model: str | None,
    ) -> tuple[list[dict[str, Any]], int, list[str]]:
        effective_query = _query_with_constraints(query, source_constraints)
        logs: list[str] = [f"Query #{idx}: {query}", f"Effective Query #{idx}: {effective_query}"]

        try:
            max_candidates = min(max(results_per_bot * 6, 12), 40)
            raw_hits = await search_web(effective_query, max_results=max_candidates)
        except Exception as exc:
            logger.warning("search bot failed: %s | %s", query, exc)
            logs.append(f"[bot {idx}] search failed: {exc}")
            return [], 0, logs

        deduped_hits: list[SearchResult] = []
        seen: set[str] = set()
        for hit in raw_hits:
            if not hit.url or hit.url in seen:
                continue
            seen.add(hit.url)
            deduped_hits.append(hit)

        logs.append(f"[bot {idx}] candidates: {len(deduped_hits)}")

        async def _worker(order: int, hit: SearchResult) -> tuple[int, SearchResult, dict[str, Any] | None, str]:
            try:
                async with self.extract_semaphore:
                    row, reason = await asyncio.wait_for(
                        self._build_single_observation(
                            topic=topic,
                            run_id=run_id,
                            hit=hit,
                            months_back=months_back,
                            source_constraints=source_constraints,
                            ai_model=ai_model,
                        ),
                        timeout=self.item_timeout_seconds,
                    )
                return order, hit, row, reason
            except asyncio.TimeoutError:
                return order, hit, None, f"timeout>{self.item_timeout_seconds:.0f}s"
            except Exception as exc:
                logger.warning("observation worker failed: %s | %s", hit.url, exc)
                return order, hit, None, "worker_failed"

        processed = await asyncio.gather(
            *[_worker(order, hit) for order, hit in enumerate(deduped_hits)],
            return_exceptions=False,
        )
        processed.sort(key=lambda item: item[0])

        accepted_rows: list[dict[str, Any]] = []
        for _, hit, row, reason in processed:
            if row is None:
                logs.append(f"[bot {idx}] skip: {reason} | {hit.url}")
                continue
            if len(accepted_rows) >= results_per_bot:
                continue

            accepted_rows.append(row)
            published_at = row.get("meta", {}).get("published_at") or "unknown_time"
            logs.append(
                f"[bot {idx}] accepted ({len(accepted_rows)}/{results_per_bot}) [{published_at}] {hit.url}"
            )

        if len(accepted_rows) < results_per_bot:
            logs.append(
                f"[bot {idx}] done with {len(accepted_rows)}/{results_per_bot} accepted (insufficient valid sources)"
            )
        else:
            logs.append(f"[bot {idx}] done with {len(accepted_rows)}/{results_per_bot} accepted")

        return accepted_rows, len(deduped_hits), logs

    async def _build_single_observation(
        self,
        topic: str,
        run_id: str,
        hit: SearchResult,
        months_back: int,
        source_constraints: list[str],
        ai_model: str | None,
    ) -> tuple[dict[str, Any] | None, str]:
        domain = (urlparse(hit.url).hostname or "").lower().removeprefix("www.")
        if source_constraints and not source_allowed(domain, source_constraints):
            return None, f"source_not_allowed({domain or 'unknown'})"

        source_score = source_probability_from_url(hit.url)
        try:
            text = await fetch(
                hit.url,
                {
                    "method": "auto",
                    "tags": [topic, domain],
                    "disable_playwright": True,
                    "httpx_timeout_seconds": 8.0,
                    "jina_timeout_seconds": 10.0,
                },
            )
        except Exception as exc:
            logger.warning("observation fetch failed: %s | %s", hit.url, exc)
            return None, "fetch_failed"

        published_at = _extract_published_at(hit=hit, text=text)
        if not published_at:
            return None, "missing_timestamp"
        if not _within_recent_months(published_at, months_back):
            return None, f"outdated({published_at.date().isoformat()})"

        try:
            parsed = await self.parse_agent.parse(text, topic=topic, default_tags=[topic, domain], model=ai_model)
        except Exception as exc:
            logger.warning("parse failed: %s | %s", hit.url, exc)
            parsed = []

        if parsed:
            best = parsed[0]
            parse_score = float(best.get("confidence", 0.5))
            content = str(best.get("content", "")).strip()
            raw_tags = [str(tag) for tag in best.get("tags", [])][:8]
        else:
            parse_score = 0.45
            content = hit.title.strip()
            raw_tags = [topic, domain]

        if not content:
            return None, "empty_content"

        tags = build_observation_tags(
            topic=topic,
            query=hit.query,
            title=hit.title,
            content=content,
            raw_tags=raw_tags,
            domain=domain,
        )
        final_probability = merge_probabilities(parse_score, source_score)
        row = {
            "id": gen_record_id("obs"),
            "run_id": run_id,
            "source": domain or hit.engine,
            "content": content[:500],
            "url": hit.url,
            "confidence": final_probability,
            "tags": tags,
            "meta": {
                "query": hit.query,
                "engine": hit.engine,
                "title": hit.title,
                "parse_probability": round(parse_score, 3),
                "source_probability": round(source_score, 3),
                "published_at": published_at.isoformat(),
            },
        }
        return row, "ok"

    def _mark_run_started(self, run_id: str) -> None:
        insert_rows(
            "runs",
            [
                {
                    "id": run_id,
                    "graph_id": None,
                    "status": "running",
                    "started_at": datetime.now(timezone.utc).isoformat(),
                }
            ],
        )

    def _mark_run_finished(self, run_id: str, status: str) -> None:
        update_rows(
            "runs",
            match={"id": run_id},
            payload={
                "status": status,
                "finished_at": datetime.now(timezone.utc).isoformat(),
            },
        )


def _extract_published_at(hit: SearchResult, text: str) -> datetime | None:
    raw_hint = (hit.published_at or "").strip()
    if raw_hint:
        parsed = _parse_datetime(raw_hint)
        if parsed:
            return parsed

    snippet = " ".join(text.split())[:2000]
    for pattern in DATE_PATTERNS:
        matched = pattern.search(snippet)
        if not matched:
            continue
        candidate = f"{matched.group('y')}-{matched.group('m')}-{matched.group('d')}"
        parsed = _parse_datetime(candidate)
        if parsed:
            return parsed

    english = MONTH_NAME_PATTERN.search(snippet)
    if english:
        month = english.group("month")
        day = english.group("day")
        year = english.group("year")
        for fmt in ("%b %d %Y", "%B %d %Y"):
            try:
                dt = datetime.strptime(f"{month} {day} {year}", fmt)
                return dt.replace(tzinfo=timezone.utc)
            except ValueError:
                continue

    matched = URL_DATE_PATTERN.search(hit.url)
    if matched:
        candidate = f"{matched.group('y')}-{matched.group('m')}-{matched.group('d')}"
        parsed = _parse_datetime(candidate)
        if parsed:
            return parsed

    return None


def _parse_datetime(value: str) -> datetime | None:
    value = value.strip()
    if not value:
        return None

    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except ValueError:
        pass

    for pattern in DATE_PATTERNS:
        matched = pattern.search(value)
        if not matched:
            continue
        year = int(matched.group("y"))
        month = int(matched.group("m"))
        day = int(matched.group("d"))
        try:
            return datetime(year, month, day, tzinfo=timezone.utc)
        except ValueError:
            continue

    return None


def _within_recent_months(dt: datetime, months_back: int) -> bool:
    now = datetime.now(timezone.utc)
    cutoff = _subtract_months(now, months_back)
    return dt >= cutoff


def _subtract_months(dt: datetime, months: int) -> datetime:
    year = dt.year
    month = dt.month - months
    while month <= 0:
        year -= 1
        month += 12
    day = min(dt.day, calendar.monthrange(year, month)[1])
    return dt.replace(year=year, month=month, day=day)


def _query_with_constraints(query: str, source_constraints: list[str]) -> str:
    if not source_constraints:
        return query
    domains = [domain.strip() for domain in source_constraints if domain.strip()][:5]
    if not domains:
        return query
    suffix = " OR ".join(f"site:{domain}" for domain in domains)
    return f"{query} ({suffix})"

from __future__ import annotations

from functools import lru_cache
from typing import Any

from backend.config import get_settings
from backend.utils.logger import get_logger

logger = get_logger(__name__)

try:
    from supabase import Client, create_client
except Exception:  # pragma: no cover
    Client = Any
    create_client = None


@lru_cache(maxsize=1)
def get_supabase_client() -> Client | None:
    settings = get_settings()
    if not settings.supabase_url or not settings.supabase_service_key or create_client is None:
        logger.warning("Supabase disabled: missing credentials or SDK")
        return None

    try:
        return create_client(settings.supabase_url, settings.supabase_service_key)
    except Exception as exc:  # pragma: no cover
        logger.exception("Failed to initialize Supabase client: %s", exc)
        return None


def insert_rows(table: str, rows: list[dict[str, Any]]) -> int:
    if not rows:
        return 0
    client = get_supabase_client()
    if client is None:
        return 0
    client.table(table).insert(rows).execute()
    return len(rows)


def upsert_rows(table: str, rows: list[dict[str, Any]], on_conflict: str | None = None) -> int:
    if not rows:
        return 0
    client = get_supabase_client()
    if client is None:
        return 0
    kwargs: dict[str, Any] = {}
    if on_conflict:
        kwargs["on_conflict"] = on_conflict
    client.table(table).upsert(rows, **kwargs).execute()
    return len(rows)


def update_rows(table: str, match: dict[str, Any], payload: dict[str, Any]) -> None:
    client = get_supabase_client()
    if client is None:
        return

    query = client.table(table).update(payload)
    for key, value in match.items():
        query = query.eq(key, value)
    query.execute()

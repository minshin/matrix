from __future__ import annotations

from typing import Any

from backend.db.client import upsert_rows


def upsert_event_nodes(rows: list[dict[str, Any]]) -> int:
    return upsert_rows("event_nodes", rows, on_conflict="id,run_id")
